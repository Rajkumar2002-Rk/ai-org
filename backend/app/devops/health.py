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

# Backend-liveness paths. Caddy routes each of these to `backend:8000` (its `@api`
# matcher), so a `< 500` answer on ANY of them proves the BACKEND process is actually
# up — a crash-looping backend makes Caddy return 502/503/504 on all of them. A live
# frontend edge (e.g. a 404 homepage) must NEVER be enough to call a deploy healthy;
# that was the run-1105 false-"live". `/openapi.json` is always present in a FastAPI app.
_BACKEND_LIVENESS_PATHS = ("/openapi.json", "/health", "/healthz")

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
    # WHICH layer of the stack failed, when not healthy: 'edge' (Caddy / the URL is
    # unreachable at all), 'backend' (the edge answers but the backend does not — the
    # run-1105 crash-loop that a live frontend edge used to mask), or 'frontend' (the
    # frontend process is not answering). None when healthy.
    failed_layer: str | None = None


@dataclass
class Fault:
    kind: str
    reason: str

    @property
    def autofixable(self) -> bool:
        return self.kind == TRANSIENT_INFRA


async def probe(url: str, verify_tls: bool, interval: int, timeout: int, *,
                has_frontend: bool = True,
                backend_paths: tuple = _BACKEND_LIVENESS_PATHS) -> ProbeResult:
    """LAYERED health probe (edge → backend → frontend). Retries until healthy or
    `timeout`. A deploy is healthy ONLY when the BACKEND actually answers; a live
    frontend edge must never mask a crash-looping backend (the run-1105 false-"live").

    Per round, checked most-fundamental first, so `failed_layer` names the real cause:
      * EDGE     — no HTTP response at all (Caddy/the URL is unreachable);
      * BACKEND  — the edge answers but every backend-liveness path is 5xx (502/503/504
                   from Caddy = the backend is down; a 200 or even a 404 = it answered);
      * FRONTEND — (only when `has_frontend`) `/` does not answer < 500 (a 404 homepage
                   still counts as up — gap #4's missing homepage must not false-fail).
    """
    import asyncio

    attempts = 0
    last_status: int | None = None
    last_error: str | None = None
    failed_layer = "edge"
    deadline = asyncio.get_event_loop().time() + timeout

    async with httpx.AsyncClient(verify=verify_tls, timeout=5,
                                 follow_redirects=True) as client:
        while True:
            attempts += 1
            edge_up = False
            backend_up = False
            # BACKEND: a < 500 answer on any backend-routed path proves the process is up.
            for path in backend_paths:
                try:
                    r = await client.get(f"{url}{path}")
                    edge_up = True                       # got an HTTP response -> Caddy is up
                    last_status = r.status_code
                    if r.status_code < 500:
                        backend_up = True
                        break
                except Exception as exc:                 # connection refused / timeout
                    last_error = str(exc)[:200]
            # FRONTEND: a non-5xx from `/` proves the frontend process answered.
            frontend_up = True
            if has_frontend:
                try:
                    r = await client.get(f"{url}/")
                    edge_up = True
                    last_status = r.status_code
                    frontend_up = r.status_code < 500
                except Exception as exc:
                    last_error = str(exc)[:200]
                    frontend_up = False

            if edge_up and backend_up and frontend_up:
                return ProbeResult(True, attempts, last_status, None, None)
            failed_layer = ("edge" if not edge_up
                            else "backend" if not backend_up
                            else "frontend")
            if asyncio.get_event_loop().time() >= deadline:
                return ProbeResult(False, attempts, last_status, last_error, failed_layer)
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
