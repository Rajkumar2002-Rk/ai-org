"""LEVEL 3 — root cause tracing (Week 6).

When a test fails, trace it back to where it actually started and label it:

    developer_fix      — bug inside one function/file
    developer_rework   — the feature was implemented wrongly / is missing
    architect_rework   — wrong technical decision (schema, endpoint, paradigm)
    ba_rework          — the requirement itself was misunderstood
    environment_fault  — the code is fine; QA's own test harness is broken

Deterministic signals decide first (they are free and reliable); the QA model
(Gemini 2.5 Flash-Lite @ 0.1) is consulted when they are ambiguous — including
whenever a failure carries architect-level evidence, which must never be
pattern-matched down to developer_fix on a surface string.

ROUTING POLICY (confirmed with the user): only developer_* is sent back
automatically. architect_rework / ba_rework are classified, logged and escalated
for a human, because re-running the Architect regenerates the whole blueprint
(invalidating the built code and the Week-5 security certificate), and BA rework
needs the user — and QA must never talk to the user. environment_fault also
escalates: no agent can fix it, because nothing is wrong with their output.
"""
import json
import logging
import re

from app import codegen
from app.config import settings
from app.qa.outcome import TestOutcome

logger = logging.getLogger("qa.root_cause")

DEVELOPER_FIX = "developer_fix"
DEVELOPER_REWORK = "developer_rework"
ARCHITECT_REWORK = "architect_rework"
BA_REWORK = "ba_rework"
# Fifth category: the failure is in the TEST HARNESS, not in the generated code.
ENVIRONMENT_FAULT = "environment_fault"

VALID_CAUSES = {DEVELOPER_FIX, DEVELOPER_REWORK, ARCHITECT_REWORK, BA_REWORK,
                ENVIRONMENT_FAULT}

# Only these are auto-routed back to an agent. Everything else escalates to a
# human — including environment_fault, which no agent can fix.
AUTO_FIX_CAUSES = {DEVELOPER_FIX, DEVELOPER_REWORK}


# Evidence that a failure is the harness's own fault. Blaming the Developer for
# these is not harmless: it caused a real security regression during Week 6
# verification — the generated app correctly refused to boot without Auth0
# config, QA called that a bug, and the "repair" hardcoded fake credentials to
# satisfy it. Kept deliberately high-precision: a false environment_fault would
# hide a genuine bug, which is worse than an over-eager Developer label.
_ENV_NAME_SIGNALS = (
    "could not create test database",
    "could not create test environment",
    "could not write file",
    "unexpected error",
)
_ENV_REASON_SIGNALS = (
    # The app's own fail-fast firing because config is absent — correct
    # behaviour by the code, missing setup by the harness.
    "refusing to start",
    # One module imported under two names: a harness sys.path problem, not the
    # generated code's fault.
    "is already defined for this metadata",
    # QA's own container has no Node toolchain, so the interface cannot be built
    # here. Blaming the generated frontend for that would send a perfectly good
    # file back to the Developer three times — the same mistake that made QA
    # "fix" correct fail-fast auth by hardcoding credentials.
    "no node toolchain",
)

# Architect-level evidence. When any of these appear the failure must NOT be
# short-circuited to developer_fix on a surface string — it needs real judgment.
_ARCHITECT_SIGNALS = ("blueprint", "schema", "designed", "not defined")

# The generated project's own top-level packages — these always exist on disk.
_PROJECT_PACKAGES = ("backend", "app", "frontend", "mobile")


def _is_environment_fault(name: str, reason: str) -> bool:
    if any(s in name for s in _ENV_NAME_SIGNALS):
        return True
    if any(s in reason for s in _ENV_REASON_SIGNALS):
        return True

    # "No module named 'backend'" — that package IS on disk (the harness wrote
    # it), so failing to import it means sys.path was set up wrongly by the test
    # runner. Deliberately requires the EXACT top-level package name: a dotted
    # miss like "backend.app.payments" means a file was never generated, which
    # is the Developer's problem, and a third-party name is a dependency
    # problem. Neither should be excused as an environment fault.
    m = re.search(r"no module named ['\"]([a-z0-9_]+)['\"]", reason)
    if m and m.group(1) in _PROJECT_PACKAGES:
        return True
    # "missing required ... environment variable": the app is right and the test
    # environment simply did not supply configuration.
    if "environment variable" in reason and any(
            w in reason for w in ("missing", "required", "not set")):
        return True
    return False


# ------------------------------------------------------------------ heuristics
def _deterministic(outcome: TestOutcome) -> str | None:
    """Cheap, reliable signals — no model call needed."""
    reason = (outcome.reason or "").lower()
    name = (outcome.name or "").lower()

    # FIRST: is this QA's own fault? Checked before anything else, because
    # harness faults masquerade as generated-code failures (they surface as
    # "app did not start") and would otherwise be blamed on the Developer.
    if _is_environment_fault(name, reason):
        return ENVIRONMENT_FAULT

    # A syntax error or an unresolvable import is a bug in one file.
    if "syntax error" in name or "syntax error" in reason:
        return DEVELOPER_FIX
    if "imports point at files that were never generated" in reason:
        return DEVELOPER_FIX
    if "dependency install failed" in name or "package that does not exist" in reason:
        return DEVELOPER_FIX
    if "no default export" in reason:
        return DEVELOPER_FIX

    # Nothing in the entire build creates an application. That is not something
    # a Developer can fix by rewriting a router — the BLUEPRINT never
    # commissioned an entrypoint. Sending it back to the Developer burns all
    # three retries on a structurally unfixable task (observed in verification),
    # so it goes to the Architect and escalates immediately.
    if "no runnable app found" in name:
        return ARCHITECT_REWORK

    # The app exists but crashes on startup: that IS the Developer's code.
    if "app did not start" in name:
        return DEVELOPER_REWORK
    if "has endpoints" in name or "discoverable" in name:
        return DEVELOPER_REWORK

    # Security failures are implementation defects: the endpoint exists but does
    # not guard itself.
    if outcome.level == 2:
        if "blocks access" in name or "rejects invalid credentials" in name:
            return DEVELOPER_FIX
        if "sql injection" in name or "negative amounts" in name or \
                "dangerous file names" in name:
            return DEVELOPER_FIX

    # Crash on hostile-but-ordinary input = missing validation in that handler.
    #
    # NARROWED: every Level-1 endpoint failure message contains "Server error",
    # so this rule used to swallow the entire most-common failure class and label
    # it developer_fix without any reasoning — even when the same text said the
    # column was "not present in the blueprint's database schema". Architect-level
    # evidence now falls through to the model instead of being pattern-matched
    # away.
    if "server error" in reason and outcome.level == 1:
        if not any(s in reason for s in _ARCHITECT_SIGNALS):
            return DEVELOPER_FIX
    return None


_SYS = (
    "You trace software test failures to their ROOT CAUSE and label who must "
    "fix it. Reply ONLY with JSON "
    '{"root_cause": "developer_fix"|"developer_rework"|"architect_rework"|'
    '"ba_rework"|"environment_fault", "why": "one short sentence"}.\n'
    "developer_fix = a bug inside one function or file.\n"
    "developer_rework = the feature was built wrongly or is missing entirely.\n"
    "architect_rework = the technical design is wrong (wrong database schema, "
    "wrong endpoint design, wrong approach) — code changes cannot fix it.\n"
    "ba_rework = the requirement itself was misunderstood; the app is building "
    "the wrong thing.\n"
    "environment_fault = the application code is CORRECT and the test harness is "
    "at fault — missing configuration or secrets in the test environment, import "
    "paths set up wrongly by the test runner, or the harness failing to build its "
    "own sandbox. An app that refuses to start because required configuration is "
    "absent is behaving CORRECTLY; that is environment_fault, never a code bug.\n"
    "Prefer developer_fix unless the evidence clearly points elsewhere."
)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


async def classify(outcome: TestOutcome, blueprint: dict, summary: dict) -> str:
    """Return the root-cause label for a failed test."""
    guess = _deterministic(outcome)
    if guess:
        return guess

    endpoints = [f"{e.get('method')} {e.get('path')}"
                 for e in (blueprint.get("api_endpoints") or [])][:25]
    context = {
        "failed_test": outcome.name,
        "what_happened": outcome.reason[:600],
        "target": outcome.target,
        "designed_endpoints": endpoints,
        "what_the_user_asked_for": (summary or {}).get("build", "")[:300],
    }
    try:
        text, _ = await codegen.generate(
            settings.qa_model, _SYS, f"Failure: {json.dumps(context)}",
            temperature=settings.qa_temperature,
        )
        res = _extract_json(text) or {}
        cause = str(res.get("root_cause", "")).strip()
        if cause in VALID_CAUSES:
            return cause
    except Exception as exc:  # pragma: no cover - never block QA on the model
        logger.warning("Root-cause model call failed: %s", exc)
    # Safest default: treat it as a code-level bug the Developer can fix.
    return DEVELOPER_FIX


async def trace(failures: list[TestOutcome], blueprint: dict,
                summary: dict) -> list[TestOutcome]:
    """Attach a root_cause_agent to every failed test."""
    for outcome in failures:
        if outcome.root_cause_agent is None:
            outcome.root_cause_agent = await classify(outcome, blueprint, summary)
    return failures


def is_auto_fixable(outcome: TestOutcome) -> bool:
    """Developer-level causes go back to the Developer agent automatically;
    Architect/BA-level causes are escalated to a human instead."""
    return outcome.root_cause_agent in AUTO_FIX_CAUSES
