"""STEP 7 — probe the live URL, and decide whether a failure is DevOps's to fix.

Two parts:

* `probe()` — ping the live URL every `interval` seconds for up to `timeout`
  seconds (the spec's 10s / 2min). Healthy = any tried path answers < 500.

* `classify()` — decide WHY it did not come up, deterministically (like QA's
  root_cause). This is where the defect-#6 lesson lives: DevOps auto-fix is
  allowed ONLY for transient infrastructure faults. An app 5xx, a missing
  credential, or a security control refusing to start is NEVER auto-fixed —
  DevOps must never make a deploy come up by weakening the app. Those escalate.

The only auto-fixable class is `transient_infra`, and the only remedy is
`driver.restart()` (cycle the processes) — an action that structurally cannot
edit code or security config.
"""
import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger("devops.health")

_PROBE_PATHS = ("/openapi.json", "/health", "/healthz", "/")

# Fault kinds.
TRANSIENT_INFRA = "transient_infra"    # the ONLY auto-fixable class
MISSING_CONFIG = "missing_config"      # app needs a secret/config we won't fake
APP_ERROR = "app_error"                # generated code is broken -> QA/Developers
SECURITY_REFUSAL = "security_refusal"  # a control is refusing -> never weaken it
UNKNOWN = "unknown"


@dataclass
class ProbeResult:
    healthy: bool
    attempts: int
    last_status: int | None = None
    last_error: str | None = None


@dataclass
class Fault:
    kind: str
    reason: str

    @property
    def autofixable(self) -> bool:
        return self.kind == TRANSIENT_INFRA


async def probe(url: str, verify_tls: bool, interval: int, timeout: int) -> ProbeResult:
    """Ping `url` until it answers < 500 or `timeout` elapses."""
    import asyncio

    attempts = 0
    last_status: int | None = None
    last_error: str | None = None
    deadline = asyncio.get_event_loop().time() + timeout

    async with httpx.AsyncClient(verify=verify_tls, timeout=5,
                                 follow_redirects=True) as client:
        while True:
            attempts += 1
            for path in _PROBE_PATHS:
                try:
                    r = await client.get(f"{url}{path}")
                    last_status = r.status_code
                    if r.status_code < 500:
                        return ProbeResult(True, attempts, last_status, None)
                except Exception as exc:            # not up yet
                    last_error = str(exc)[:200]
            if asyncio.get_event_loop().time() >= deadline:
                return ProbeResult(False, attempts, last_status, last_error)
            await asyncio.sleep(interval)


# Deterministic signals, most-specific first. Each returns a Fault or None.
_SECURITY_RES = [
    re.compile(r"allow_origins.*\*", re.I),
    re.compile(r"\bCORS\b.*credential", re.I),
    re.compile(r"authoriz|authentic", re.I),
]
_MISSING_CONFIG_RES = [
    re.compile(r"refus\w* to start", re.I),
    re.compile(r"missing required .*environment", re.I),
    re.compile(r"environment variable .* (?:not set|is required|missing)", re.I),
    re.compile(r"\bKeyError\b.*(?:KEY|SECRET|TOKEN|PASSWORD)", re.I),
]
_APP_ERROR_RES = [
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"\b(ImportError|ModuleNotFoundError|NameError|AttributeError|"
               r"SyntaxError|TypeError)\b"),
    re.compile(r"Application startup failed"),
    re.compile(r"pydantic.*Invalid args for response field", re.I),
]
_TRANSIENT_RES = [
    re.compile(r"could not connect to server", re.I),
    re.compile(r"connection refused", re.I),
    re.compile(r"the database system is starting up", re.I),
    re.compile(r"could not translate host name", re.I),
    re.compile(r"timed out", re.I),
    re.compile(r"Temporary failure in name resolution", re.I),
]


def classify(diagnostics: str, probe_result: ProbeResult | None = None) -> Fault:
    """Classify a failed bring-up/health from container output.

    Order matters: a security refusal or a missing credential must win over the
    generic "connection refused" that a not-yet-ready dependency also produces —
    otherwise a legitimately-refusing security control would be mislabelled
    transient and auto-restarted (a milder replay of defect #6). So the unsafe
    classes are checked BEFORE the transient one.
    """
    text = diagnostics or ""

    for rx in _SECURITY_RES:
        if rx.search(text):
            return Fault(SECURITY_REFUSAL,
                         "A security control is refusing to start (e.g. missing "
                         "auth config or an insecure-CORS guard). DevOps will not "
                         "weaken it to force a boot — escalating.")
    for rx in _MISSING_CONFIG_RES:
        if rx.search(text):
            return Fault(MISSING_CONFIG,
                         "The app requires configuration/credentials that were "
                         "not provided. DevOps never fabricates a secret to make "
                         "it boot — escalating so the missing key can be connected.")
    for rx in _APP_ERROR_RES:
        if rx.search(text):
            return Fault(APP_ERROR,
                         "The generated application code failed at startup. This "
                         "is not an infrastructure fault — escalating to QA / the "
                         "Developer agents rather than 'fixing' it in deployment.")
    for rx in _TRANSIENT_RES:
        if rx.search(text):
            return Fault(TRANSIENT_INFRA,
                         "A dependency (most likely the database) was not ready in "
                         "time. Retrying the bring-up once.")

    return Fault(UNKNOWN,
                 "The app did not become healthy and the cause is not a known "
                 "infrastructure fault. Escalating rather than guessing.")
