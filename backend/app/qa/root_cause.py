"""LEVEL 3 — root cause tracing (Week 6).

When a test fails, trace it back to where it actually started and label it:

    developer_fix      — bug inside one function/file
    developer_rework   — the feature was implemented wrongly / is missing
    architect_rework   — wrong technical decision (schema, endpoint, paradigm)
    ba_rework          — the requirement itself was misunderstood

Deterministic signals decide first (they are free and reliable); the QA model
(Gemini 2.5 Flash-Lite @ 0.1) is only consulted when the signals are ambiguous.

ROUTING POLICY (confirmed with the user): only developer_* is sent back
automatically. architect_rework / ba_rework are classified, logged and escalated
for a human, because re-running the Architect regenerates the whole blueprint
(invalidating the built code and the Week-5 security certificate), and BA rework
needs the user — and QA must never talk to the user.
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

VALID_CAUSES = {DEVELOPER_FIX, DEVELOPER_REWORK, ARCHITECT_REWORK, BA_REWORK}

# Only these are auto-routed back to an agent. The rest are escalated.
AUTO_FIX_CAUSES = {DEVELOPER_FIX, DEVELOPER_REWORK}


# ------------------------------------------------------------------ heuristics
def _deterministic(outcome: TestOutcome) -> str | None:
    """Cheap, reliable signals — no model call needed."""
    reason = (outcome.reason or "").lower()
    name = (outcome.name or "").lower()

    # A syntax error or an unresolvable import is a bug in one file.
    if "syntax error" in name or "syntax error" in reason:
        return DEVELOPER_FIX
    if "imports point at files that were never generated" in reason:
        return DEVELOPER_FIX
    if "dependency install failed" in name or "package that does not exist" in reason:
        return DEVELOPER_FIX
    if "no default export" in reason:
        return DEVELOPER_FIX

    # The app exposes nothing / won't boot: the code as a whole doesn't fulfil
    # the tickets, which is a rework rather than a one-line fix.
    if "no runnable app found" in name or "app did not start" in name:
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
    if "server error" in reason and outcome.level == 1:
        return DEVELOPER_FIX
    return None


_SYS = (
    "You trace software test failures to their ROOT CAUSE and label who must "
    "fix it. Reply ONLY with JSON "
    '{"root_cause": "developer_fix"|"developer_rework"|"architect_rework"|"ba_rework", '
    '"why": "one short sentence"}.\n'
    "developer_fix = a bug inside one function or file.\n"
    "developer_rework = the feature was built wrongly or is missing entirely.\n"
    "architect_rework = the technical design is wrong (wrong database schema, "
    "wrong endpoint design, wrong approach) — code changes cannot fix it.\n"
    "ba_rework = the requirement itself was misunderstood; the app is building "
    "the wrong thing.\n"
    "Prefer developer_fix unless the evidence clearly points higher up."
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
