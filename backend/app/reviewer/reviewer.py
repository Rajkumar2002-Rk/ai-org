"""Code Reviewer agent (Week 5) — two separate passes per file.

PASS 1 — general review (mid-tier model from the blueprint's llm_routing):
    correctness, error handling, performance, scalability, readability.
PASS 2 — SECURITY review (ALWAYS claude-opus-4-8, hardcoded, bypasses the
    cheap-mode override — core rule: security is never done on a cheaper model).

Severity routing:
    minor  -> fix automatically, continue
    medium -> fix, log it against the file
    critical (security) -> STOP, fix with Opus, re-run the security review,
             only pass once no critical issues remain.
The Code Reviewer never talks to the user.
"""
import json
import logging
import re

from app import codegen

logger = logging.getLogger("reviewer")

# Hardcoded — NEVER changes, NEVER a cheaper model (core rule).
SECURITY_MODEL = "claude-opus-4-8"
_MAX_SECURITY_RETRIES = 2


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


_GENERAL_SYS = (
    "You are a senior code reviewer. Review the file for: correctness (does it "
    "do what the ticket asked?), error handling (empty inputs, network "
    "failures), performance (obvious bottlenecks), scalability (works under "
    "load?), and readability. Do NOT report security issues (a separate pass "
    "handles those). Return JSON "
    '{"issues": [{"type": string, "severity": "minor"|"medium", "detail": string}]}. '
    "Report only real issues; empty list if the file is fine."
)

_SECURITY_SYS = (
    "You are a strict application security auditor. Review the file ONLY for "
    "security vulnerabilities: authentication bypass; SQL or code injection via "
    "inputs; data exposure (can user A read user B's data?); payment "
    "manipulation; exposed API keys or secrets in code; missing encryption on "
    "sensitive data; missing authorization checks on endpoints. Return JSON "
    '{"issues": [{"type": string, "severity": "minor"|"medium"|"critical", '
    '"detail": string}]}. Empty list if secure. Mark anything exploitable as '
    '"critical".'
)


async def _review(model: str, system: str, file: dict, content: str, bypass: bool) -> list[dict]:
    text, _ = await codegen.generate(
        model, system,
        f"Ticket: {file.get('ticket_id')} — file {file.get('filepath', file.get('filename'))}\n\n"
        f"{content[:12000]}",
        temperature=0.0, bypass_cheap=bypass,
    )
    res = _extract_json(text)
    issues = res.get("issues", []) if isinstance(res, dict) else []
    return [i for i in issues if isinstance(i, dict)]


_FIX_SYS = (
    "You are fixing specific issues in a code file. Apply the fixes while "
    "preserving everything else that works. Return ONLY JSON "
    '{"content": "<the full corrected file as one string>"}. No prose, no fences.'
)


async def _fix(model: str, file: dict, content: str, issues: list[dict], bypass: bool) -> str | None:
    listed = "\n".join(f"- [{i.get('severity')}] {i.get('type')}: {i.get('detail')}" for i in issues)
    text, _ = await codegen.generate(
        model, _FIX_SYS,
        f"File {file.get('filepath', file.get('filename'))}. Fix these issues:\n"
        f"{listed}\n\nCurrent file:\n{content[:12000]}",
        temperature=0.1, bypass_cheap=bypass,
    )
    res = _extract_json(text)
    new = res.get("content") if isinstance(res, dict) else None
    return new if new and len(new) > 20 else None


async def review_file(file: dict, general_model: str) -> dict:
    """Run both passes on one file. Returns a summary dict."""
    content = file["content"]
    found = fixed = 0

    # --- PASS 1: general review (respects cheap mode) ---
    g_issues = await _review(general_model, _GENERAL_SYS, file, content, bypass=False)
    found += len(g_issues)
    g_fixable = [i for i in g_issues if i.get("severity") in ("minor", "medium")]
    if g_fixable:
        new = await _fix(general_model, file, content, g_fixable, bypass=False)
        if new:
            content, fixed = new, fixed + len(g_fixable)

    # --- PASS 2: SECURITY review (ALWAYS Opus, bypass cheap) ---
    s_issues = await _review(SECURITY_MODEL, _SECURITY_SYS, file, content, bypass=True)
    found += len(s_issues)
    security_passed = True
    if s_issues:
        new = await _fix(SECURITY_MODEL, file, content, s_issues, bypass=True)
        if new:
            content, fixed = new, fixed + len(s_issues)
        had_critical = any(i.get("severity") == "critical" for i in s_issues)
        if had_critical:
            # STOP-and-verify: re-run the security review on the fix.
            security_passed = False
            for _ in range(_MAX_SECURITY_RETRIES):
                recheck = await _review(SECURITY_MODEL, _SECURITY_SYS, file, content, bypass=True)
                crit = [i for i in recheck if i.get("severity") == "critical"]
                if not crit:
                    security_passed = True
                    break
                # Re-review turned up more issues — count them as found too so
                # issues_fixed can never exceed issues_found.
                found += len(crit)
                new = await _fix(SECURITY_MODEL, file, content, crit, bypass=True)
                if new:
                    content, fixed = new, fixed + len(crit)

    return {
        "file_id": file["id"],
        "issues_found": found,
        # A fix can address at most what was found — clamp for honest reporting.
        "issues_fixed": min(fixed, found),
        "security_passed": security_passed,
        "reviewed_by_model": f"{general_model} + {SECURITY_MODEL}",
        "new_content": content if content != file["content"] else None,
    }
