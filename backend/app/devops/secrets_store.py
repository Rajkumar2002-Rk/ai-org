"""STEP 5 — inject the user's connected API keys, keep them out of logs.

Three structural guarantees (not "we're careful"):

1. **Encrypted at rest.** Values are Fernet-encrypted before they touch the
   `secrets` table. Without `SECRETS_ENC_KEY` this module REFUSES to store or read
   — it never silently downgrades to plaintext.

2. **Injected only as environment, never as CLI args or image layers.** Secrets
   go into a `--env-file` written with `0600` permissions and deleted in a
   `finally` (see the drivers). They are never passed as `docker run -e k=v` (which
   would surface in `ps` and shell history) and never `COPY`d/`ARG`d into an image
   (whose layers persist and are exportable).

3. **Redacted at the log sink.** `SecretRedactingFilter` replaces any live secret
   VALUE with `***REDACTED***` on every record passing through the handler it is
   attached to — so even a stray `logger.info(some_dict_with_a_secret)` cannot
   emit the value. `test_devops_offline` proves this BOTH ways: the sentinel is
   absent with the filter on, and — the check that makes the first mean anything —
   present with it off, so a no-op redactor is caught.

Secret VALUES never appear in any API/dashboard payload: the deployments row and
status responses carry key NAMES and a count only.

⚠️ KNOWN GAP (logged, not a blocker): no onboarding stage writes REAL user
secrets here yet — a "connect your API keys" UI is scoped future work. The store
is real and read by DevOps today; seed it directly until that UI exists.
"""
import logging
import os
import threading

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Secret

logger = logging.getLogger("devops.secrets")

_REDACTION = "***REDACTED***"
# Values shorter than this are not registered for redaction — redacting a 2-char
# string would corrupt unrelated log lines, and a real credential is never that
# short.
_MIN_REDACT_LEN = 4


# ------------------------------------------------------------------ encryption
def _fernet():
    """Build the Fernet cipher, or fail loudly. Never returns a no-op cipher —
    a secrets store that silently holds plaintext is worse than one that errors."""
    key = settings.secrets_enc_key
    if not key:
        raise RuntimeError(
            "SECRETS_ENC_KEY is not set — the secrets store will not hold "
            "plaintext. Set a Fernet key before storing or reading secrets."
        )
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    return _fernet().encrypt((value or "").encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt((token or "").encode()).decode()


# ------------------------------------------------------------------ persistence
async def set_secret(project_id: int, key_name: str, value: str) -> None:
    """Upsert one encrypted secret for a project (a re-connect updates in place)."""
    enc = encrypt(value)
    async with async_session() as db:
        row = (await db.execute(
            select(Secret).where(
                Secret.project_id == project_id, Secret.key_name == key_name
            )
        )).scalar_one_or_none()
        if row is None:
            db.add(Secret(project_id=project_id, key_name=key_name,
                          value_encrypted=enc))
        else:
            row.value_encrypted = enc
        await db.commit()


async def get_secrets(project_id: int) -> dict[str, str]:
    """Decrypt all secrets for a project into memory. The plaintext lives only in
    the returned dict; register it with `guard()` before doing anything that
    logs."""
    async with async_session() as db:
        rows = (await db.execute(
            select(Secret.key_name, Secret.value_encrypted)
            .where(Secret.project_id == project_id)
        )).all()
    out: dict[str, str] = {}
    for key_name, enc in rows:
        try:
            out[key_name] = decrypt(enc)
        except Exception:
            # A value we cannot decrypt (wrong key) is skipped loudly rather than
            # injected as garbage — but we never log the ciphertext or the name's
            # value.
            logger.error("Could not decrypt secret %r for project %s — skipped.",
                         key_name, project_id)
    return out


async def secret_names(project_id: int) -> list[str]:
    """Key NAMES only — safe to surface (never the values)."""
    async with async_session() as db:
        rows = (await db.execute(
            select(Secret.key_name).where(Secret.project_id == project_id)
        )).all()
    return [r[0] for r in rows]


# --------------------------------------------------------------- log redaction
class SecretRedactingFilter(logging.Filter):
    """Redacts registered secret values from every record passing through the
    handler it is attached to. Attach to a HANDLER (not just a logger) so it
    applies to records propagated from child loggers too."""

    def __init__(self):
        super().__init__()
        self._values: set[str] = set()
        self._lock = threading.Lock()

    def add(self, values) -> None:
        with self._lock:
            for v in values:
                if v and len(v) >= _MIN_REDACT_LEN:
                    self._values.add(v)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()

    def filter(self, record: logging.LogRecord) -> bool:
        with self._lock:
            values = tuple(self._values)
        if not values:
            return True
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - malformed record
            msg = str(record.msg)
        redacted = msg
        for v in values:
            if v in redacted:
                redacted = redacted.replace(v, _REDACTION)
        if redacted != msg:
            # Flatten args into the already-formatted, redacted message so the
            # unredacted values in `args` can never be re-formatted downstream.
            record.msg = redacted
            record.args = ()
        return True


# A single shared redactor. Attached to the root logger's handlers in production
# and to the capture handler in tests.
redactor = SecretRedactingFilter()


def guard(values) -> None:
    """Register secret values so they are redacted from logs from now on."""
    redactor.add(values)


def unguard() -> None:
    """Forget all registered secret values (call in a `finally` after a deploy)."""
    redactor.clear()


def protect_root_handlers() -> None:
    """Best-effort: attach the shared redactor to every root handler so any log
    line emitted during a deploy is filtered at the sink. Idempotent."""
    root = logging.getLogger()
    for h in root.handlers:
        if redactor not in h.filters:
            h.addFilter(redactor)


# ------------------------------------------------------------------ env file
def write_env_file(directory: str, mapping: dict[str, str],
                   filename: str = ".deploy.env") -> str:
    """Write KEY=VALUE lines to a 0600 file the docker CLI reads via --env-file.

    Returns the path. The CALLER must delete it in a `finally` — secrets should
    exist on disk for as short a time as possible.
    """
    path = os.path.join(directory, filename)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for k, v in mapping.items():
            # env-file values are literal to end-of-line; no quoting needed and
            # newlines in a value would corrupt the file, so strip them.
            fh.write(f"{k}={str(v).replace(chr(10), ' ').replace(chr(13), ' ')}\n")
    return path
