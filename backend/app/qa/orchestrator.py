"""QA agent orchestrator (Week 6).

Owns the whole QA pass:

    assemble a throwaway instance -> Level 1 (user interaction) + Level 2
    (security attacks) -> Level 3 (root cause tracing) -> send developer-level
    failures back to the Developer agent -> re-test -> record qa_results.

LOOP CONTROL: at most `settings.qa_max_retries` (3) attempts per issue. An issue
that still fails after that is marked escalated, logged, and the run CONTINUES.
There is no unbounded loop anywhere: the round counter is the only driver.

The QA agent never talks to the user — the API layer exposes counts only.
"""
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app import usage
from app.config import settings
from app.database import async_session
from app.developers import agents as dev_agents
from app.developers.orchestrator import _contract_text
from app.models import Blueprint, GeneratedFile, PipelineStatus, Project, QAResult
from app.qa import assembly, level1, level2, root_cause
from app.qa.outcome import TestOutcome
from app.redis_client import redis_client
from app.reviewer import orchestrator as reviewer_orchestrator

logger = logging.getLogger("qa.orchestrator")

# Every failure that is NOT going to be retried must say so. A finding that sits
# at retry_count=0 with no marker is indistinguishable from one that was simply
# never looked at — that silent no-op is what Step 2 verification caught.
ESCALATED_PREFIX = "[escalated after retries] "
ESCALATED_TIER_PREFIX = "[escalated — needs Architect/BA, not auto-fixable] "
ESCALATED_ENV_PREFIX = "[escalated — QA's own test environment is at fault, the generated code is not] "
ESCALATED_UNTRACED_PREFIX = "[escalated — could not be traced to a specific file] "
# No agent can fix a certificate that is missing — it is an operational problem
# (Redis lost it, or it expired), not a defect in anyone's output. It still needs
# a marker: a failure sitting at retry_count=0 with no stated reason is exactly
# the silent no-op Step 2 closed.
ESCALATED_CERT_PREFIX = "[escalated — no security certificate, this build cannot be certified] "
CERT_MISSING_TEST = "security: certificate is missing"


# ------------------------------------------------------------------ helpers
def _key(outcome: TestOutcome) -> str:
    return outcome.name


_TRACEBACK_FILE_RE = re.compile(r'File "(?:/tmp/qa-build-[^/]+/)([^"]+\.py)"')


def _file_from_traceback(reason: str, files: list[dict]) -> dict | None:
    """Pull the culprit out of a startup traceback.

    Assembly failures name the exact file that blew up. Using that beats
    guessing, and it is the difference between regenerating the broken module
    and regenerating something arbitrary.
    """
    hits = _TRACEBACK_FILE_RE.findall(reason or "")
    for rel in reversed(hits):        # deepest frame first
        for f in files:
            if f.get("filepath") == rel or (f.get("filepath") or "").endswith("/" + rel):
                return f
    return None


def _file_for_target(target: str, files: list[dict], reason: str = "") -> dict | None:
    """Find the generated file responsible for a failing test.

    `target` is a filepath (frontend/static checks) or "METHOD /path" (API
    tests). Assembly-level failures have no single owning file, so they are
    resolved from the traceback instead of guessed — the old substring fallback
    picked whichever shortest file merely CONTAINED the text (for target "app"
    that was effectively random, and it regenerated innocent files).
    """
    if not target:
        return None

    for f in files:
        if f.get("filepath") == target or f.get("filename") == target:
            return f

    if target == "app":
        return _file_from_traceback(reason, files)

    parts = target.split(" ", 1)
    if len(parts) != 2:
        return None
    literal = parts[1].split("{")[0].rstrip("/")
    if len(literal) < 2:
        return None

    # Require the route as a QUOTED string — that is how a route is declared,
    # so it is a real match rather than an incidental substring.
    best = None
    for f in files:
        content = f.get("content") or ""
        if f'"{literal}' in content or f"'{literal}" in content:
            if best is None or len(content) < len(best.get("content") or ""):
                best = f
    return best


def _entrypoint_file(files: list[dict]) -> dict | None:
    """The file that creates the app and registers routers (APP-1 / main.py)."""
    for f in files:
        if (f.get("ticket_id") or "").upper() == "APP-1":
            return f
    for f in files:
        if (f.get("filepath") or "").endswith(("app/main.py", "/main.py")):
            return f
    for f in files:
        if "FastAPI(" in (f.get("content") or ""):
            return f
    return None


def _resolve_owner(outcome: TestOutcome, files: list[dict]) -> dict | None:
    """Which generated file should be re-generated to fix this failure?

    Routes that the Architect designed but that are absent from the running app
    almost always mean the ENTRYPOINT failed to register their router — there is
    no traceback to attribute, so without this the finding was classified
    auto-fixable and then never retried (retry_count stayed 0 forever).
    """
    if "designed features are missing" in outcome.name:
        row = _entrypoint_file(files)
        if row is not None:
            return row
    return _file_for_target(
        outcome.target, files, (outcome.reason or "") + "\n" + (outcome.evidence or "")
    )


def _ticket_for(blueprint: dict, ticket_id: str) -> dict | None:
    for t in blueprint.get("sprint_tickets", []) or []:
        if t.get("id") == ticket_id:
            return t
    return None


async def _regenerate(file_row: dict, ticket: dict, blueprint: dict,
                      failures: list[TestOutcome], repair: str = "") -> str | None:
    """Send a failing file back to the Developer agent with the QA evidence.

    `repair` (optional) is a structured code-integrity finding from the QA-regen gate
    (fix #16/#17) — a targeted SYNTAX_ERROR / IMPORT_RESOLUTION_FAILURE — threaded into
    the Developer's bounded retry so a rewrite that broke the file is repaired precisely
    (see `_regenerate_validated`)."""
    routing = blueprint.get("llm_routing", {})
    model = routing.get(f"{ticket.get('assigned_to', 'backend')}_developer", "gpt-4o")

    evidence = "\n".join(
        f"- {f.name}: {f.reason}" for f in failures[:8]
    )
    repair_ticket = {
        **ticket,
        "description": (
            f"{ticket.get('description', '')}\n\n"
            f"QA TESTING FOUND THESE FAILURES IN YOUR PREVIOUS VERSION OF "
            f"{file_row.get('filepath')} — fix ALL of them while keeping "
            f"everything that already works:\n{evidence}\n"
            f"Validate all inputs, never return a 500 for bad input (return a "
            f"4xx), enforce authorization on protected routes, reject negative "
            f"amounts, and use parameterised queries only.\n"
            f"CRITICAL — do NOT make a test pass by weakening security. Never "
            f"hardcode, mock, default or invent credentials or secrets; never "
            f"set environment variables in code; never remove a fail-fast check "
            f"on missing configuration; never widen CORS; never drop an "
            f"authorization check. If the code is correct and the environment is "
            f"simply missing configuration, LEAVE IT AS IS — a refusal to start "
            f"without required secrets is correct behaviour, not a bug."
        ),
    }
    try:
        result = await dev_agents.build_ticket(
            repair_ticket, model, [], _contract_text(blueprint), repair
        )
        return result.get("content")
    except Exception as exc:  # pragma: no cover - never kill the QA run
        logger.warning("Developer re-run failed for %s: %s", file_row.get("filepath"), exc)
        return None


# ---- Code-integrity gate on QA's OWN regeneration (fix: close the ungated QA loop) ----
# Run 1105 proved the decisive hole: QA's repair loop regenerates a file through the
# Developer agent and ACCEPTED the result with NO deterministic validation, so it
# re-introduced the exact classes the BUILD gate already closes — a param-ordering
# SyntaxError in order_be_3.py (fix #17) and `from backend.app.models import
# StripeOAuthState`, a symbol models.py never exported (fix #16). Both then broke the
# app at boot. So QA's regeneration path gets the SAME deterministic gates as the build
# gate, plus a BOUNDED, re-validated repair — and a rewrite that still fails the gate is
# REJECTED (the previous file content is kept) rather than allowed to become canonical.
_QA_REGEN_MAX_REVALIDATE = 2


def _gate_regenerated(candidate: str, filepath: str, files: list[dict],
                      file_id) -> dict:
    """Deterministic code-integrity gate on a QA-regenerated backend `.py`: it MUST
    parse (fix #17) AND every in-project `from ... import ...` must resolve to a real
    exported symbol (fix #16) AND no `get_db`-style dependency generator swallows a
    framework HTTPException into a 500 (fix #24). Returns a gate-result dict shaped for
    `agents.repair_instructions` (`syntax_error` / `symbol_repairs` / `http_swallow_repairs`),
    or {} if clean.
    Backend `.py` only; anything else (frontend, non-`.py`) is a no-op. Symbols are
    resolved against the CURRENT file set with the candidate swapped in, so the check
    reflects exactly what would ship."""
    if not (filepath or "").endswith(".py"):
        return {}
    syn = dev_agents.python_syntax_error(candidate, filepath)
    if syn:
        return {"syntax_error": syn}      # syntax first — an unparseable file blocks the rest
    swapped = [{**f, "content": candidate} if f.get("id") == file_id else f for f in files]
    index = dev_agents.build_symbol_index(swapped)
    sym = dev_agents.import_symbol_mismatches(candidate, filepath, index)
    if sym:
        return {"symbol_repairs": sym}
    attr = dev_agents.attribute_access_mismatches(candidate, filepath, index)
    if attr:
        return {"attribute_repairs": attr}
    hx = dev_agents.http_exception_swallow(candidate, filepath)
    if hx:
        return {"http_swallow_repairs": hx}
    return {}


async def _regenerate_validated(file_row: dict, ticket: dict, blueprint: dict,
                                failures: list[TestOutcome],
                                files: list[dict]) -> str | None:
    """QA regeneration, gated by the build gate's own deterministic checks (fix #16/#17)
    with a BOUNDED, re-validated repair. Returns accepted content, or None to REJECT the
    rewrite (caller keeps the previous file — never ships a gate-failing regeneration,
    which is exactly what the QA loop did on run 1105). At most `_QA_REGEN_MAX_REVALIDATE`
    extra repair attempts; a still-failing rewrite is a non-convergent failure, logged."""
    filepath = file_row.get("filepath") or file_row.get("filename") or ""
    repair = ""
    for attempt in range(_QA_REGEN_MAX_REVALIDATE + 1):
        candidate = await _regenerate(file_row, ticket, blueprint, failures, repair)
        if not candidate:
            return None
        gate = _gate_regenerated(candidate, filepath, files, file_row.get("id"))
        if not gate:
            return candidate                                   # clean — accept
        repair = dev_agents.repair_instructions(gate)
        logger.warning(
            "QA regenerated %s but it FAILED the code-integrity gate (attempt %d/%d): "
            "%s — re-requesting a targeted repair, not accepting the broken rewrite.",
            filepath, attempt + 1, _QA_REGEN_MAX_REVALIDATE + 1,
            "; ".join(k for k in gate),
        )
    logger.error(
        "QA regeneration of %s did not pass the code-integrity gate after %d attempts "
        "— REJECTING the rewrite and keeping the previous content (non-convergent).",
        filepath, _QA_REGEN_MAX_REVALIDATE + 1,
    )
    return None


async def _recertify(project_id: int, blueprint: dict, file_ids: set[int]) -> dict:
    """Re-run the Opus security review over code that changed since certification.

    THE INVARIANT: the security certificate must never describe code that no
    longer exists on disk. QA's repair loop runs AFTER certification, so without
    this the certificate would attest to code that has since been replaced —
    which is exactly how an insecure change slipped past the Week-5 gate during
    verification.

    The authoritative signal is the certificate's own content fingerprint, not
    QA's bookkeeping: comparing hashes catches drift from ANY source, including
    a stage that never declared it changed anything. QA's tracked edits are
    unioned in so a certificate predating fingerprints still recertifies.

    FAILS CLOSED ON A MISSING CERTIFICATE TOO. `drifted_files` returns [] when
    there is no certificate at all — correctly, since drift is meaningless
    without a baseline — but that used to flow through here as an empty dict and
    land on `certified = True`. A build with NO security certificate would then
    be marked `tested`. Same failure as defect #6 with a different trigger: that
    one was a certificate that no longer matched disk, this one is a certificate
    that is not there at all, e.g. after Redis loses it (no persistence volume,
    plus a 24h TTL on the key). "We can't tell" must never resolve to "it's fine".
    """
    raw = await redis_client.get(f"security_cert:{project_id}")
    cert = json.loads(raw) if raw else {}

    if not cert:
        logger.error(
            "No security certificate for project %s — QA cannot certify this "
            "build. Blocking rather than defaulting to certified.", project_id,
        )
        return {
            "passed": False,
            "certificate_missing": True,
            "reason": (
                "No security certificate exists for this build, so it cannot be "
                "shown to have passed security review. The code was not "
                "re-reviewed here on purpose: silently spending an Opus review "
                "to paper over a lost certificate would hide why it went missing."
            ),
        }

    drifted = set(await reviewer_orchestrator.drifted_files(project_id, cert))
    targets = drifted | set(file_ids)
    if not targets:
        return cert

    result = await reviewer_orchestrator.review_subset(
        project_id, blueprint, sorted(targets)
    )
    now = datetime.now(timezone.utc).isoformat()
    cert["passed"] = bool(cert.get("passed", True)) and result["passed"]
    cert["issues_found"] = cert.get("issues_found", 0) + result["issues_found"]
    cert["issues_fixed"] = cert.get("issues_fixed", 0) + result["issues_fixed"]
    cert["model_used"] = reviewer_orchestrator.reviewer.SECURITY_MODEL
    cert["recertified_after_qa"] = {
        "files_rechecked": result["files_reviewed"],
        "drifted_from_certificate": sorted(drifted),
        "rewritten_by_qa": sorted(file_ids),
        "passed": result["passed"],
        "issues_found": result["issues_found"],
        "issues_fixed": result["issues_fixed"],
        "timestamp": now,
    }
    # Re-fingerprint so the certificate again describes what is on disk.
    cert["file_hashes"] = await reviewer_orchestrator.file_hashes(project_id)
    cert["timestamp"] = now
    await redis_client.set(f"security_cert:{project_id}", json.dumps(cert), ex=86400)
    return cert


# ------------------------------------------------------------------ one round
async def _run_round(files: list[dict],
                     expected_endpoints: list[str]) -> tuple[list[TestOutcome], assembly.TestEnv]:
    """Assemble, test, tear down. Returns outcomes (assembly problems included)."""
    env = await assembly.assemble(files, expected_endpoints)
    outcomes: list[TestOutcome] = []
    try:
        # Assembly problems ARE Level 1 findings, not crashes. The reason shown
        # to a human is truncated, so carry the FULL startup log alongside it —
        # the frame naming the culprit file is often above the truncation point,
        # and without it an assembly failure can't be attributed or retried.
        for f in env.failures:
            o = TestOutcome(f.test_name, 1, False, f.reason, "app")
            o.evidence = env.logs
            outcomes.append(o)

        # File-level checks first, ALWAYS. They need the generated files, not a
        # running backend — chaining them to env.ok meant a backend that failed
        # to boot silently cost the frontend all of its coverage.
        outcomes.extend(await level1.run_static(env))

        if env.ok:
            outcomes.extend(await level1.run(env))
            outcomes.extend(await level2.run(env))
    except Exception as exc:  # pragma: no cover - QA never crashes the pipeline
        logger.exception("QA testing errored")
        outcomes.append(TestOutcome("testing — unexpected error", 1, False,
                                    str(exc)[:400], "app"))
    finally:
        await assembly.teardown(env)
    return outcomes, env


# ------------------------------------------------------------------ entrypoint
async def run(project_id: int) -> dict:
    """Full QA pass for a project. Returns a plain summary (no technical detail
    leaves this layer for the user)."""
    # One id for every row this pass writes, so re-runs of the same project stay
    # separable (blueprint_id does not distinguish them).
    run_id = uuid.uuid4().hex
    # Tag every LLM call made anywhere downstream of here with THIS pass's id, so
    # "what did this QA cycle cost" is a join on run_id against llm_usage rather
    # than timestamp-matching. Deliberately reuses the qa_results run_id instead
    # of minting a second identifier for the same thing.
    usage_token = usage.set_run_context(run_id=run_id, project_id=project_id,
                                        stage="qa")

    async with async_session() as db:
        stage = PipelineStatus(project_id=project_id, stage="qa", status="running")
        db.add(stage)
        bp_row = (await db.execute(
            select(Blueprint.id, Blueprint.blueprint_json)
            .where(Blueprint.project_id == project_id)
            .order_by(Blueprint.id.desc()).limit(1)
        )).first()
        project = await db.get(Project, project_id)
        summary = json.loads(project.summary_json) if project and project.summary_json else {}
        await db.commit()
        await db.refresh(stage)
        stage_id = stage.id

    blueprint_id = bp_row[0] if bp_row else None
    blueprint = json.loads(bp_row[1]) if bp_row else {}

    expected_endpoints = [e.get("path") for e in (blueprint.get("api_endpoints") or [])
                          if e.get("path")]

    # Final state per test name, plus how many times we retried each issue.
    final: dict[str, TestOutcome] = {}
    retries: dict[str, int] = {}
    # Every file QA rewrites after the Opus certificate -> must be re-reviewed.
    modified_files: set[int] = set()
    # Auto-fixable failures we could not attribute to any file -> escalated, not
    # silently dropped.
    untraceable: set[str] = set()

    try:
        for round_no in range(settings.qa_max_retries + 1):
            async with async_session() as db:
                rows = (await db.execute(
                    select(GeneratedFile.id, GeneratedFile.ticket_id,
                           GeneratedFile.filename, GeneratedFile.filepath,
                           GeneratedFile.content, GeneratedFile.agent_type)
                    .where(GeneratedFile.project_id == project_id)
                    .order_by(GeneratedFile.id)
                )).all()
            files = [{"id": r[0], "ticket_id": r[1], "filename": r[2], "filepath": r[3],
                      "content": r[4], "agent_type": r[5]} for r in rows]

            outcomes, _env = await _run_round(files, expected_endpoints)

            # This round's results ARE the current state. A test that failed in
            # an earlier round and no longer appears was RESOLVED — carry it
            # forward as passed rather than leaving a stale failure that would
            # mark the whole project failed for a problem QA already fixed.
            current: dict[str, TestOutcome] = {}
            for o in outcomes:
                o.retry_count = retries.get(_key(o), 0)
                current[_key(o)] = o
            for name, prev in final.items():
                if name not in current and not prev.passed:
                    resolved = TestOutcome(
                        name, prev.level, True,
                        f"resolved after {retries.get(name, 0)} repair attempt(s)",
                        prev.target,
                    )
                    resolved.retry_count = retries.get(name, 0)
                    current[name] = resolved
            final = current

            failures = [o for o in outcomes if not o.passed]
            if not failures:
                break

            await root_cause.trace(failures, blueprint, summary)

            # Which failures may we still retry?
            retryable = [
                f for f in failures
                if root_cause.is_auto_fixable(f)
                and retries.get(_key(f), 0) < settings.qa_max_retries
            ]
            if not retryable or round_no == settings.qa_max_retries:
                break

            # Group failures by the file responsible, then re-run the Developer
            # once per file with all of that file's evidence.
            by_file: dict[int, list[TestOutcome]] = {}
            file_by_id = {}
            for f in retryable:
                row = _resolve_owner(f, files)
                if row is None:
                    # Auto-fixable in theory, but we cannot say WHICH file to
                    # regenerate. Record it so it escalates honestly instead of
                    # sitting at retry_count=0 looking like nobody tried.
                    untraceable.add(_key(f))
                    continue
                by_file.setdefault(row["id"], []).append(f)
                file_by_id[row["id"]] = row

            if not by_file:
                break

            for file_id, group in by_file.items():
                row = file_by_id[file_id]
                ticket = _ticket_for(blueprint, row.get("ticket_id") or "") or {
                    "id": row.get("ticket_id") or "QA-FIX",
                    "title": f"Fix {row.get('filepath')}",
                    "assigned_to": row.get("agent_type") or "backend",
                    "description": f"Repair {row.get('filepath')}.",
                    "dependencies": [],
                }
                # Gate QA's OWN regeneration with the build gate's deterministic checks
                # (fix #16/#17) + bounded re-validated repair. A rewrite that does not
                # parse or imports a symbol no in-project module exports is REJECTED
                # (None) — the previous content is kept, never churned into a
                # non-booting state as it was on run 1105.
                new_content = await _regenerate_validated(
                    row, ticket, blueprint, group, files)
                if new_content:
                    async with async_session() as db:
                        gf = await db.get(GeneratedFile, file_id)
                        if gf is not None:
                            gf.content = new_content
                            await db.commit()
                    # Certified code has been replaced -> owes a re-review.
                    modified_files.add(file_id)
                for f in group:
                    retries[_key(f)] = retries.get(_key(f), 0) + 1

        # ---- re-certify anything QA rewrote (MUST happen before we call the
        # project secured/tested — see _recertify) -----------------------
        # Always ask, even when QA believes it changed nothing: the certificate's
        # fingerprint is what decides, not QA's own bookkeeping.
        recert = await _recertify(project_id, blueprint, modified_files)
        if recert.get("certificate_missing"):
            # Surface it as a failing test, not just a status flag, so the
            # reason travels with the results instead of being inferred.
            final[CERT_MISSING_TEST] = TestOutcome(
                CERT_MISSING_TEST, 2, False,
                recert.get("reason") or "No security certificate for this build.",
                "app",
            )
        elif recert.get("recertified_after_qa"):
            if not recert.get("passed", True):
                final["security: re-check after repairs"] = TestOutcome(
                    "security: re-check after repairs", 2, False,
                    "Code changed while fixing test failures did not pass the "
                    "security re-check, so this build is not certified.",
                    "app",
                )

        # ---- persist final results -------------------------------------
        escalated = 0
        async with async_session() as db:
            for name, o in final.items():
                reason = o.reason or None
                if not o.passed:
                    # Say WHY this failure is not (or is no longer) being retried.
                    if name == CERT_MISSING_TEST:
                        prefix = ESCALATED_CERT_PREFIX
                    elif o.root_cause_agent == root_cause.ENVIRONMENT_FAULT:
                        # Never blamed on an agent — nothing is wrong with their
                        # output, so this goes straight to a human.
                        prefix = ESCALATED_ENV_PREFIX
                    elif retries.get(name, 0) >= settings.qa_max_retries:
                        prefix = ESCALATED_PREFIX
                    elif name in untraceable:
                        prefix = ESCALATED_UNTRACED_PREFIX
                    elif o.root_cause_agent and not root_cause.is_auto_fixable(o):
                        prefix = ESCALATED_TIER_PREFIX
                    else:
                        prefix = None
                    if prefix:
                        escalated += 1
                        reason = f"{prefix}{reason or 'still failing'}"
                db.add(QAResult(
                    project_id=project_id,
                    run_id=run_id,
                    blueprint_id=blueprint_id,
                    test_name=name[:255],
                    test_level=o.level,
                    passed=o.passed,
                    failure_reason=reason,
                    root_cause_agent=o.root_cause_agent,
                    retry_count=retries.get(name, 0),
                ))

            total = len(final)
            passed = sum(1 for o in final.values() if o.passed)
            # Still certified? If QA rewrote code, the re-review decides.
            # Defaults are FAIL-CLOSED in both directions: an absent recert dict
            # and an absent `passed` key both mean "not shown to have passed".
            certified = bool(recert.get("passed", False)) if recert else False
            all_passed = passed == total and total > 0 and certified

            st = await db.get(PipelineStatus, stage_id)
            if st is not None:
                st.status = "done" if all_passed else "error"
                st.completed_at = datetime.now(timezone.utc)
                if not all_passed:
                    st.error_message = (
                        f"{total - passed} test(s) failed"
                        if certified else "security re-check failed after repairs"
                    )
            project = await db.get(Project, project_id)
            if project is not None:
                if not certified:
                    project.status = "security_blocked"
                else:
                    project.status = "tested" if all_passed else "qa_failed"
            await db.commit()

        return {
            "run_id": run_id,
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "escalated": escalated,
            "all_passed": all_passed,
            "blueprint_id": blueprint_id,
            "files_rewritten_by_qa": len(modified_files),
            "recertified": recert.get("recertified_after_qa") if recert else None,
            "still_certified": certified,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:  # pragma: no cover
        logger.exception("QA run failed for project %s", project_id)
        async with async_session() as db:
            st = await db.get(PipelineStatus, stage_id)
            if st is not None:
                st.status = "error"
                st.error_message = str(exc)[:500]
                st.completed_at = datetime.now(timezone.utc)
                await db.commit()
        raise
    finally:
        # Untag, so calls made after this pass are not attributed to it.
        usage.reset_run_context(usage_token)
