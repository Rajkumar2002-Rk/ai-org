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
from app.config import settings

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

# The Architect flags Stripe Connect files (PAY-* tickets — POST-REVIEW
# DECISION 3). When one reaches the security pass, tell the auditor exactly what
# to verify on the payment feature.
_PAYMENT_SECURITY_FOCUS = (
    "\n\nThis file is part of the Stripe Connect payment feature. Verify "
    "SPECIFICALLY, and mark any failure critical: (1) the OAuth access/refresh "
    "token is stored ENCRYPTED at rest — flag any plaintext token storage; "
    "(2) the Stripe Connect OAuth flow is correct — a signed `state` param "
    "guards against CSRF and the code exchange happens server-side; (3) NO "
    "credential leakage — no tokens or secrets in logs, API responses, or "
    "client-side code, and no Stripe credential is sent to any platform."
)

_PAYMENT_TICKET_PREFIXES = ("PAY-",)
_PAYMENT_PATH_HINTS = ("stripe", "oauth", "connect", "payment", "webhook")


def _is_payment_sensitive(file: dict) -> bool:
    """A file the Architect flagged (or that clearly implements the payment
    feature) so the security pass gets the Stripe Connect focus checklist."""
    if str(file.get("ticket_id", "")).startswith(_PAYMENT_TICKET_PREFIXES):
        return True
    path = (file.get("filepath") or file.get("filename") or "").lower()
    return any(hint in path for hint in _PAYMENT_PATH_HINTS)


# Menu PDF upload/extraction files process user-UPLOADED files — a common source
# of bugs (malformed PDFs, oversized files, filename injection). They get extra
# scrutiny in the GENERAL review pass (per the menu-onboarding feature spec).
_MENU_EXTRACTION_FOCUS = (
    "\n\nThis file is part of the menu PDF upload/extraction feature, which "
    "processes user-UPLOADED files. Scrutinize SPECIFICALLY and flag any failure: "
    "(1) malformed or corrupt PDFs are handled gracefully — the server returns a "
    "clear error and NEVER crashes; (2) upload limits are enforced — oversized "
    "files and non-PDF content types are rejected BEFORE processing; (3) no "
    "injection via a crafted filename — the client-supplied filename is never used "
    "in a filesystem path or shell command; (4) extracted items are NEVER "
    "auto-published — they must be stored as pending review and only go live after "
    "explicit owner confirmation."
)

_MENU_EXTRACTION_TICKETS = ("MENU-3", "MENU-4")
_MENU_EXTRACTION_PATH_HINTS = ("menu_upload", "menu/review")


def _is_menu_extraction(file: dict) -> bool:
    """A menu PDF upload/extraction or review file — extra scrutiny in the general
    pass, since it processes user-uploaded files."""
    if str(file.get("ticket_id", "")) in _MENU_EXTRACTION_TICKETS:
        return True
    path = (file.get("filepath") or file.get("filename") or "").lower()
    return any(hint in path for hint in _MENU_EXTRACTION_PATH_HINTS)


# FRONTEND (fix #53) — a generated Next.js app file. The reviewer REVIEWS and REPORTS
# these but NEVER mutates them (see `review_file`). These mirror devops.manifest._is_frontend
# (path prefix first, extension fallback) without importing it — that module pulls in the
# heavy QA assembler.
_FRONTEND_EXT = (".tsx", ".ts", ".jsx", ".js", ".css", ".json")


def _is_frontend_path(path: str) -> bool:
    """Path-only frontend test (no agent_type). Used where only a filepath is known."""
    p = (path or "").lower()
    if p.startswith("frontend/"):
        return True
    if p.startswith("backend/"):
        return False
    return p.endswith(_FRONTEND_EXT)


def _is_frontend(file: dict) -> bool:
    """True for a generated frontend file, which the reviewer must not auto-fix (fix #53)."""
    path = (file.get("filepath") or file.get("filename") or "").lower()
    if path.startswith("frontend/"):
        return True
    if path.startswith("backend/"):
        return False
    if path.endswith(_FRONTEND_EXT):
        return "backend" not in (file.get("agent_type") or "")
    return False


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

# Fix #55b — a frontend file is only ever rewritten to remove a CONFIRMED security
# critical, so the repair prompt is security-specific AND guards the two ways an Opus
# frontend rewrite historically broke the deploy build (truncation/unclosed JSX, and a
# type error like a Set/Map spread or a type-arg on an untyped call).
_FRONTEND_SECURITY_FIX_SYS = (
    "You are fixing a CONFIRMED security vulnerability in a Next.js/React (.tsx/.ts) "
    "file. Remove the vulnerability while preserving every existing behaviour and export. "
    "NEVER place a token, secret, or credential in a URL or query string — attach a bearer "
    "token via an Authorization header (or read it from secure storage); never weaken or "
    "remove authentication. Return the COMPLETE, valid file: every JSX tag closed, all "
    "braces/parens balanced, no unterminated string. Do NOT introduce TypeScript that fails "
    "`next build`: no `[...new Set(x)]`/iterable spreads over Sets or Maps, and no type "
    "arguments on an untyped call (`reduce<T>()`). Return ONLY JSON "
    '{"content": "<the full corrected file as one string>"}. No prose, no fences.'
)


async def _fix(model: str, file: dict, content: str, issues: list[dict], bypass: bool,
               system: str = _FIX_SYS, extra: str = "") -> str | None:
    listed = "\n".join(f"- [{i.get('severity')}] {i.get('type')}: {i.get('detail')}" for i in issues)
    prompt = (f"File {file.get('filepath', file.get('filename'))}. Fix these issues:\n"
              f"{listed}\n")
    if extra:
        prompt += f"\n{extra}\n"
    prompt += f"\nCurrent file:\n{content[:12000]}"
    text, _ = await codegen.generate(
        model, system, prompt, temperature=0.1, bypass_cheap=bypass,
    )
    res = _extract_json(text)
    new = res.get("content") if isinstance(res, dict) else None
    return new if new and len(new) > 20 else None


# --------------------------------------------------------- confirmed-critical quorum (fix #55a)
# Words too generic to identify WHICH vulnerability a critical is — dropped so a signature
# keys on the distinctive security noun(s) ("token", "url", "sql", "auth", "idor", …) rather
# than on filler that every finding shares.
_SIG_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "to", "is", "via", "and", "or", "with", "for", "by",
    "issue", "vulnerability", "security", "potential", "possible", "insecure", "unsafe",
    "risk", "attack", "error", "bug", "flaw", "problem",
}


def _issue_signature(issue: dict) -> str:
    """A normalized signature for one issue, keyed on its `type` (the stable, short
    categorical field). Lowercased, punctuation-stripped, stopwords removed, tokens
    sorted+deduped — so 'Token in URL' and 'token in the url' collapse to the same
    signature while two genuinely different findings do not. Falls back to a generic
    'critical' bucket when the type carries no distinctive word, so two type-less criticals
    still confirm EACH OTHER (the conservative, block-leaning choice)."""
    toks = [w for w in re.findall(r"[a-z0-9]+", (issue.get("type") or "").lower())
            if w not in _SIG_STOPWORDS]
    return " ".join(sorted(set(toks))) or "critical"


def _critical_signatures(issues: list[dict]) -> set[str]:
    return {_issue_signature(i) for i in issues if i.get("severity") == "critical"}


async def _confirmed_critical_issues(system: str, file: dict, content: str,
                                     first_issues: list[dict] | None = None) -> list[dict]:
    """The CONFIRMED critical issues on `content`, by a QUORUM (fix #55a): the SAME issue
    signature must RECUR across ≥2 of 3 independent Opus passes. Empty list if nothing is
    confirmed.

    The security reviewer is an LLM and therefore STOCHASTIC even at temperature 0: a single
    pass can surface a transient 'critical' on reproducibly-clean code (run 2080's
    `tip/page.tsx` returned ZERO issues on a fresh pass over the identical bytes, yet the old
    guard fail-closed the whole deploy). That guard only asked 'did SOME critical appear on
    two passes?', so two DIFFERENT one-off flakes could 'confirm' each other. Requiring the
    SAME signature to recur keys the verdict on reproducibility: a real vulnerability shows up
    as the same finding every pass; independent flakes usually do not. At most three passes,
    and only ever the extra passes when a critical is first seen (`first_issues` seeds pass 1
    from a review the caller already ran, so a clean file spends nothing here)."""
    p1_issues = first_issues if first_issues is not None else \
        await _review(SECURITY_MODEL, system, file, content, bypass=True)
    p1 = _critical_signatures(p1_issues)
    if not p1:
        return []                                    # no critical at all -> nothing to confirm
    p2_issues = await _review(SECURITY_MODEL, system, file, content, bypass=True)
    p2 = _critical_signatures(p2_issues)
    confirmed = p1 & p2
    pool = list(p1_issues) + list(p2_issues)
    if not confirmed:
        # Pass 1 and pass 2 disagreed — a third pass breaks the tie: a signature seen in
        # pass 3 that ALSO appeared in pass 1 or pass 2 has now recurred across 2 of 3.
        p3_issues = await _review(SECURITY_MODEL, system, file, content, bypass=True)
        confirmed = _critical_signatures(p3_issues) & (p1 | p2)
        pool += list(p3_issues)
    if not confirmed:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for i in pool:
        if i.get("severity") != "critical":
            continue
        sig = _issue_signature(i)
        if sig in confirmed and sig not in seen:
            seen.add(sig)
            out.append(i)
    return out


async def _confirmed_critical(system: str, file: dict, content: str,
                              first_issues: list[dict] | None = None) -> bool:
    """True iff a CRITICAL security issue is CONFIRMED on `content` by the fix-#55a quorum —
    see `_confirmed_critical_issues`. Short-circuits on a clean first pass (no extra calls)."""
    return bool(await _confirmed_critical_issues(system, file, content, first_issues))


# --------------------------------------------------- bounded frontend security repair (fix #55b)
async def _repair_frontend_security(file: dict, content: str, confirmed_issues: list[dict],
                                    files: list[dict] | None, schema: list | None,
                                    security_sys: str) -> str | None:
    """Fix #55b — ONE bounded, re-validated repair for a CONFIRMED frontend security critical.

    Fix #53 made the reviewer read-only on frontend, which killed the stochastic breakage
    loop but left a confirmed frontend critical (run 2080's REAL JWT-in-URL in
    `integrate/page.tsx`) with NO remediation path — the deploy simply fail-closed. This gives
    exactly one narrow, safe way back: ask Opus to fix THE confirmed issue, and accept the
    rewrite ONLY if it (a) passes the deterministic frontend build gate — completeness,
    no CSS leak, and a real esbuild parse (`rewrite_integrity_gate`) — AND (b) a security
    re-review no longer CONFIRMS a critical (the fix-#55a quorum). Otherwise keep the
    certified-clean original and return None so the caller fails the cert closed (blocking the
    deploy + flagging for a human). This CANNOT loop like the pre-#53 reviewer: it is bounded
    to `settings.reviewer_frontend_repair_attempts`, every candidate must pass the full gate
    before acceptance, and it triggers ONLY on a confirmed critical — never stochastically on
    every re-cert. The authoritative whole-app TYPE check stays QA's real `next build`
    (fix #51) downstream; #54's emitted tsconfig keeps the ES3 iteration class from arising."""
    from app.developers import agents as dev_agents   # local import: avoid an import cycle

    fp = file.get("filepath") or file.get("filename") or ""
    note = ""
    for _ in range(max(0, settings.reviewer_frontend_repair_attempts)):
        candidate = await _fix(SECURITY_MODEL, file, content, confirmed_issues, bypass=True,
                               system=_FRONTEND_SECURITY_FIX_SYS, extra=note)
        if not candidate:
            break
        gate = dev_agents.rewrite_integrity_gate(
            candidate, fp, files or [], schema, file_id=file.get("id"))
        if gate:
            # The fix broke the file structurally — feed the precise defect back and retry.
            note = dev_agents.repair_instructions(gate)
            continue
        if await _confirmed_critical(security_sys, file, candidate):
            note = ("The previous rewrite did NOT remove the security vulnerability — it is "
                    "still present. Remove it without weakening authentication.")
            continue
        return candidate                 # parse-clean AND security-clean -> accept
    return None                          # no safe candidate within the bound -> fail closed


async def _review_frontend_readonly(file: dict, general_model: str, general_sys: str,
                                    security_sys: str, files: list[dict] | None = None,
                                    schema: list | None = None) -> dict:
    """Fix #53 — review + report a FRONTEND file WITHOUT stochastically mutating it; fix #55b
    — but repair it (once, bounded, re-validated) when a critical is CONFIRMED.

    The Opus security reviewer is stochastic and kept rewriting generated `.tsx`/`.ts` files
    into states that failed the deploy's real `next build` on every re-cert (run 1950: an
    unclosed `<p>`, then a `[...Set]` spread, then a bad `reduce<T>()` type-arg — a *new* type
    error each pass). No cheap gate catches a type error, so each 'fix' drifted the
    certificate's fingerprint and forced another paid pass without ever converging (fix #53).
    So we run BOTH passes to report issues and form an HONEST verdict on the file AS WRITTEN.
    On a CONFIRMED critical (fix #55a quorum — a lone flake like run 2080's `tip/page.tsx` no
    longer fails a clean deploy) we hand the file ONE bounded, gate-and-re-review-validated
    repair (fix #55b); if that yields a safe rewrite it is applied, otherwise the cert fails
    closed (blocking the deploy) — never auto-broken-then-shipped, and never looping."""
    content = file["content"]
    g_issues = await _review(general_model, general_sys, file, content, bypass=False)
    s_issues = await _review(SECURITY_MODEL, security_sys, file, content, bypass=True)
    found = len(g_issues) + len(s_issues)
    security_passed = True
    fixed = 0
    new_content = None
    if any(i.get("severity") == "critical" for i in s_issues):
        # Confirm on the ORIGINAL content before acting — a reproducible vuln recurs as the
        # same finding, a one-off flake does not (fix #55a). Reuse s_issues as pass 1.
        confirmed = await _confirmed_critical_issues(
            security_sys, file, content, first_issues=s_issues)
        if confirmed:
            repaired = await _repair_frontend_security(
                file, content, confirmed, files, schema, security_sys)
            if repaired is not None:
                # Clamp for honest reporting — a repair can address at most what was found.
                new_content, fixed, security_passed = repaired, min(len(confirmed), found), True
            else:
                security_passed = False        # no safe repair -> fail closed (block + flag)
                logger.warning(
                    "Reviewer: a CONFIRMED frontend security critical in %s could not be "
                    "safely repaired within the bound — FAILING the certificate (blocking the "
                    "deploy) and flagging for human review.",
                    file.get("filepath") or file.get("filename"))
        # else: an unconfirmed (stochastic) critical no longer fails a clean deploy (fix #55a).
    return {
        "file_id": file["id"],
        "issues_found": found,
        "issues_fixed": fixed,
        "security_passed": security_passed,
        "reviewed_by_model": f"{general_model} + {SECURITY_MODEL}",
        "new_content": new_content,
    }


async def review_file(file: dict, general_model: str, files: list[dict] | None = None,
                      schema: list | None = None) -> dict:
    """Run both passes on one file. Returns a summary dict.

    FRONTEND files are reviewed + reported but not stochastically mutated — see
    `_review_frontend_readonly` (fix #53); a CONFIRMED critical gets one bounded, re-validated
    repair (fix #55b), for which `files`/`schema` feed the deterministic re-validation gate."""
    content = file["content"]
    found = fixed = 0

    # Menu upload/extraction files get an extra file-handling checklist in the general
    # pass; Stripe Connect (PAY-*) files get the payment-security checklist in the Opus
    # pass so it specifically verifies encrypted tokens / OAuth / no leakage.
    general_sys = _GENERAL_SYS + (
        _MENU_EXTRACTION_FOCUS if _is_menu_extraction(file) else ""
    )
    security_sys = _SECURITY_SYS + (
        _PAYMENT_SECURITY_FOCUS if _is_payment_sensitive(file) else ""
    )

    if _is_frontend(file):
        return await _review_frontend_readonly(
            file, general_model, general_sys, security_sys, files=files, schema=schema)

    # --- PASS 1: general review (respects cheap mode) ---
    g_issues = await _review(general_model, general_sys, file, content, bypass=False)
    found += len(g_issues)
    g_fixable = [i for i in g_issues if i.get("severity") in ("minor", "medium")]
    if g_fixable:
        new = await _fix(general_model, file, content, g_fixable, bypass=False)
        if new:
            content, fixed = new, fixed + len(g_fixable)

    # --- PASS 2: SECURITY review (ALWAYS Opus, bypass cheap) ---
    s_issues = await _review(SECURITY_MODEL, security_sys, file, content, bypass=True)
    found += len(s_issues)
    security_passed = True
    if s_issues:
        new = await _fix(SECURITY_MODEL, file, content, s_issues, bypass=True)
        if new:
            content, fixed = new, fixed + len(s_issues)
        if any(i.get("severity") == "critical" for i in s_issues):
            # Keep FIXING criticals as they surface (bounded) ...
            for _ in range(_MAX_SECURITY_RETRIES):
                recheck = await _review(SECURITY_MODEL, security_sys, file, content, bypass=True)
                crit = [i for i in recheck if i.get("severity") == "critical"]
                if not crit:
                    break
                # Re-review turned up more issues — count them as found too so
                # issues_fixed can never exceed issues_found.
                found += len(crit)
                new = await _fix(SECURITY_MODEL, file, content, crit, bypass=True)
                if new:
                    content, fixed = new, fixed + len(crit)
            # ... then decide pass/fail on the FINAL content, not on whether the
            # stochastic fix-loop happened to converge within N tries. A file fails ONLY
            # if a critical is CONFIRMED on the final content (two passes) — this removes
            # the run-1289 false-negative (cert failing on reproducibly-clean code) while
            # a genuine, reproducible vulnerability still blocks the deploy.
            security_passed = not await _confirmed_critical(security_sys, file, content)

    return {
        "file_id": file["id"],
        "issues_found": found,
        # A fix can address at most what was found — clamp for honest reporting.
        "issues_fixed": min(fixed, found),
        "security_passed": security_passed,
        "reviewed_by_model": f"{general_model} + {SECURITY_MODEL}",
        "new_content": content if content != file["content"] else None,
    }
