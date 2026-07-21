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
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.developers import agents as dev_agents
from app.developers.orchestrator import _contract_text
from app.models import Blueprint, GeneratedFile, PipelineStatus, Project, QAResult
from app.qa import assembly, level1, level2, root_cause
from app.qa.outcome import TestOutcome

logger = logging.getLogger("qa.orchestrator")

ESCALATED_PREFIX = "[escalated after retries] "


# ------------------------------------------------------------------ helpers
def _key(outcome: TestOutcome) -> str:
    return outcome.name


def _file_for_target(target: str, files: list[dict]) -> dict | None:
    """Find the generated file most likely responsible for a failing test.

    `target` is either a filepath (frontend checks) or "METHOD /path" (API
    tests); for the latter we look for the route string in the file contents.
    """
    if not target:
        return None
    for f in files:
        if f.get("filepath") == target or f.get("filename") == target:
            return f

    parts = target.split(" ", 1)
    path = parts[1] if len(parts) == 2 else target
    # Match the most specific literal segment of the route.
    literal = path.split("{")[0].rstrip("/") or path
    best = None
    for f in files:
        content = f.get("content") or ""
        if literal and literal in content:
            if best is None or len(content) < len(best.get("content") or ""):
                best = f
    return best


def _ticket_for(blueprint: dict, ticket_id: str) -> dict | None:
    for t in blueprint.get("sprint_tickets", []) or []:
        if t.get("id") == ticket_id:
            return t
    return None


async def _regenerate(file_row: dict, ticket: dict, blueprint: dict,
                      failures: list[TestOutcome]) -> str | None:
    """Send a failing file back to the Developer agent with the QA evidence."""
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
            f"amounts, and use parameterised queries only."
        ),
    }
    try:
        result = await dev_agents.build_ticket(
            repair_ticket, model, [], _contract_text(blueprint)
        )
        return result.get("content")
    except Exception as exc:  # pragma: no cover - never kill the QA run
        logger.warning("Developer re-run failed for %s: %s", file_row.get("filepath"), exc)
        return None


# ------------------------------------------------------------------ one round
async def _run_round(files: list[dict]) -> tuple[list[TestOutcome], assembly.TestEnv]:
    """Assemble, test, tear down. Returns outcomes (assembly problems included)."""
    env = await assembly.assemble(files)
    outcomes: list[TestOutcome] = []
    try:
        # Assembly problems ARE Level 1 findings, not crashes.
        for f in env.failures:
            outcomes.append(TestOutcome(f.test_name, 1, False, f.reason, "app"))

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

    # Final state per test name, plus how many times we retried each issue.
    final: dict[str, TestOutcome] = {}
    retries: dict[str, int] = {}

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

            outcomes, _env = await _run_round(files)

            for o in outcomes:
                o.retry_count = retries.get(_key(o), 0)
                final[_key(o)] = o

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
                row = _file_for_target(f.target, files)
                if row is None:
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
                new_content = await _regenerate(row, ticket, blueprint, group)
                if new_content:
                    async with async_session() as db:
                        gf = await db.get(GeneratedFile, file_id)
                        if gf is not None:
                            gf.content = new_content
                            await db.commit()
                for f in group:
                    retries[_key(f)] = retries.get(_key(f), 0) + 1

        # ---- persist final results -------------------------------------
        escalated = 0
        async with async_session() as db:
            for name, o in final.items():
                reason = o.reason or None
                is_escalated = (
                    not o.passed and retries.get(name, 0) >= settings.qa_max_retries
                )
                if is_escalated:
                    escalated += 1
                    reason = f"{ESCALATED_PREFIX}{reason or 'still failing'}"
                db.add(QAResult(
                    project_id=project_id,
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
            all_passed = passed == total and total > 0

            st = await db.get(PipelineStatus, stage_id)
            if st is not None:
                st.status = "done" if all_passed else "error"
                st.completed_at = datetime.now(timezone.utc)
                if not all_passed:
                    st.error_message = f"{total - passed} test(s) failed"
            project = await db.get(Project, project_id)
            if project is not None:
                project.status = "tested" if all_passed else "qa_failed"
            await db.commit()

        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "escalated": escalated,
            "all_passed": all_passed,
            "blueprint_id": blueprint_id,
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
