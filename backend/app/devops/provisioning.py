"""Platform-side provisioning for deploy — the "problem #3" trio.

A generated app fail-fasts at startup on config it legitimately needs but that no
human owns: cryptographic keys (any random value works), a Redis service, and a
handful of config vars with obvious deploy-time answers. Unlike owner secrets
(Auth0/Stripe accounts — "problem #1"), the platform can supply all of these
itself. This module does exactly that, deterministically and only for the vars an
app actually references.

Split of responsibilities:
  * `required_env(files)`      — which env vars the generated backend reads.
  * `ensure_crypto_keys(...)`  — mint + PERSIST the crypto keys (Fix A). Persistence
                                 is essential: a redeploy MUST reuse the same key or
                                 already-encrypted rows become unreadable.
  * `config_defaults(...)`     — non-secret config vars with sane defaults (Fix C,
                                 minus ALLOWED_ORIGINS which is driver-level because
                                 the deploy port is chosen dynamically).
  * `needs_redis(files)`       — whether to add a redis service (Fix B; the compose
                                 wiring itself lives in manifest.py).
Nothing here fakes an OWNER secret; those still fail-fast honestly (Fix #20).
"""
import logging
import re
import secrets as _secrets

from cryptography.fernet import Fernet

from app.devops import secrets_store

logger = logging.getLogger("devops.provisioning")

# `os.getenv("X")`, `os.getenv('X', default)`, `os.environ["X"]`, `os.environ.get("X")`.
_ENV_RE = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*['"]([A-Z][A-Z0-9_]*)['"]"""
    r"""|os\.environ\[\s*['"]([A-Z][A-Z0-9_]*)['"]\s*\]"""
)


def required_env(files: list[dict]) -> set[str]:
    """The set of environment variable NAMES the generated BACKEND code reads. Scans
    only backend `.py` files (frontend `NEXT_PUBLIC_*` is handled by the deploy wiring
    separately). Deterministic — a plain source scan, no execution."""
    from app.devops import manifest  # local import: avoid a cycle at module load
    names: set[str] = set()
    for f in files:
        if manifest._is_frontend(f):
            continue
        path = f.get("filepath") or f.get("filename") or ""
        if not path.endswith(".py"):
            continue
        for m in _ENV_RE.finditer(f.get("content") or ""):
            names.add(m.group(1) or m.group(2))
    return names


# ------------------------------------------------------------------ Fix A: crypto keys
# Each entry: env var name -> how to mint it. Fernet keys must be valid
# base64(32 bytes) because the generated code does `Fernet(THE_KEY)`; the session
# secret is just an unguessable random string. ONLY these platform-mintable keys are
# ever generated — an owner secret (STRIPE_SECRET_KEY, AUTH0_*) is never fabricated.
def _fernet_key() -> str:
    return Fernet.generate_key().decode()


def _random_secret() -> str:
    return _secrets.token_urlsafe(48)


_CRYPTO_KEYS: dict[str, callable] = {
    "FERNET_KEY": _fernet_key,
    "TOKEN_ENCRYPTION_KEY": _fernet_key,
    "STRIPE_TOKEN_ENC_KEY": _fernet_key,
    "SESSION_SECRET_KEY": _random_secret,
}


async def ensure_crypto_keys(project_id: int, needed: set[str],
                             existing: dict[str, str]) -> dict[str, str]:
    """For every platform-mintable crypto key the app NEEDS but does not yet have,
    mint one and PERSIST it (so redeploys reuse it). Returns only the newly minted
    {name: value} (already-present keys are left to `existing`). Never overwrites an
    existing value. If the secrets store is unavailable, keys are minted for THIS
    deploy but a warning notes they are not persisted (a redeploy would rotate them)."""
    minted: dict[str, str] = {}
    for name, make in _CRYPTO_KEYS.items():
        if name not in needed or name in existing:
            continue
        value = make()
        try:
            await secrets_store.set_secret(project_id, name, value)
        except Exception:
            logger.warning("Minted %s for project %s but could NOT persist it — a "
                           "redeploy will rotate it (encrypted data may then be "
                           "unreadable).", name, project_id)
        minted[name] = value
    return minted


# ------------------------------------------------------------------ Fix C: config defaults
# Non-secret, obvious deploy-time answers. Applied only when the app reads the var.
# ALLOWED_ORIGINS is intentionally ABSENT — the deploy origin (host port) is chosen
# by the driver, so it is set there, not here.
_CONFIG_DEFAULTS: dict[str, str] = {
    "ENVIRONMENT": "production",
    "SQL_ECHO": "false",
    "RATE_LIMIT_TIMES": "5",
    "RATE_LIMIT_SECONDS": "60",
}


def config_defaults(needed: set[str], existing: dict[str, str]) -> dict[str, str]:
    """Sane non-secret defaults for referenced config vars the owner has not set.
    Never overrides a value already in `existing` (an owner override wins)."""
    return {k: v for k, v in _CONFIG_DEFAULTS.items()
            if k in needed and k not in existing}


# ------------------------------------------------------------------ Fix B: redis
_REDIS_ENV = "REDIS_URL"
# Internal compose DNS: the redis service is named `redis` on the app's own network.
REDIS_INTERNAL_URL = "redis://redis:6379"


def needs_redis(files: list[dict]) -> bool:
    """True if the generated backend reads REDIS_URL (e.g. FastAPI-Limiter). The
    compose service + REDIS_URL wiring is added by manifest.py; this is the gate."""
    return _REDIS_ENV in required_env(files)


# ------------------------------------------------- platform-held provider secrets (gap #1)
# The "platform-held" half of owner onboarding (PLAN_owner_onboarding.md): provider
# credentials the platform holds ONCE for every app (Stripe Connect client, platform
# email sender, platform Twilio). Each maps an env var the generated code reads to the
# settings attribute that holds it, and whether it is a SECRET (guard/redact) or a
# non-secret identifier (must NOT be redacted — e.g. SMTP_PORT="587"). Auth0
# (AUTH0_DOMAIN/API_AUDIENCE) is deliberately absent here — it is provisioned PER
# PROJECT via the Management API in its own slice, not statically injected. The
# owner's CONNECTED Stripe account is captured by the BA connect flow, also separate.
_PLATFORM_HELD: dict[str, tuple[str, bool]] = {
    # env var name           (settings attr,          is_secret)
    "STRIPE_CLIENT_ID":      ("stripe_client_id",     False),
    "STRIPE_SECRET_KEY":     ("stripe_secret_key",    True),
    "STRIPE_REDIRECT_URI":   ("stripe_redirect_uri",  False),
    "SMTP_HOST":             ("smtp_host",            False),
    "SMTP_PORT":             ("smtp_port",            False),
    "SMTP_USER":             ("smtp_user",            False),
    "SMTP_PASSWORD":         ("smtp_password",        True),
    "SENDER_EMAIL":          ("sender_email",         False),
    "TWILIO_ACCOUNT_SID":    ("twilio_account_sid",   False),
    "TWILIO_AUTH_TOKEN":     ("twilio_auth_token",    True),
    "TWILIO_PHONE_NUMBER":   ("twilio_phone_number",  False),
}


def platform_provided(needed: set[str], existing: dict[str, str]
                      ) -> tuple[dict[str, str], dict[str, str]]:
    """Return (secret_values, nonsecret_values) for the platform-held provider vars the
    app READS and that the platform has configured (settings set) and the owner has not
    already supplied. Split by secrecy so STEP 5 guards only the real secrets (never a
    value like SMTP_PORT). A referenced var whose platform setting is UNSET is simply
    omitted -> the app fail-fasts on it honestly (the feature is genuinely unconfigured).
    Missing settings are logged per-provider so the operator knows what to configure."""
    from app.config import settings
    secret_out: dict[str, str] = {}
    nonsecret_out: dict[str, str] = {}
    missing: list[str] = []
    for env_name, (attr, is_secret) in _PLATFORM_HELD.items():
        if env_name not in needed or env_name in existing:
            continue
        value = getattr(settings, attr, None)
        if not value:
            missing.append(env_name)
            continue
        (secret_out if is_secret else nonsecret_out)[env_name] = str(value)
    if missing:
        logger.warning("Platform provider credentials NOT configured for %s — the "
                       "deployed app will fail-fast on them until the platform sets "
                       "these (PLAN_owner_onboarding.md §7).", ", ".join(sorted(missing)))
    return secret_out, nonsecret_out
