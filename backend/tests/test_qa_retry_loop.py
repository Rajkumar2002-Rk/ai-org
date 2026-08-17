"""Step-2 verification: exercise the retry-and-escalate loop under FIXED code.

The real pipeline runs only ever produced retries under PRE-fix code, so the
loop's *usefulness* properties were unproven. This drives the real
`qa.orchestrator.run()` against synthetic projects written straight into the
database, so we can observe the loop end to end with real assembly, real HTTP
tests and real qa_results rows.

ZERO LLM SPEND — three seams are patched:
  * codegen.generate        -> never calls a provider
  * dev_agents.build_ticket -> returns a SCRIPTED repair (deterministic)
  * reviewer.review_subset  -> no Opus re-review

Everything else is the production code path: assembly, venv, temp Postgres,
uvicorn, Level 1 / Level 2, root-cause tracing, retry accounting, persistence.

Run: docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
         backend python tests/test_qa_retry_loop.py
"""
import asyncio
import json
import sys

from sqlalchemy import delete, select

import app.codegen as codegen
import app.developers.agents as dev_agents
import app.reviewer.orchestrator as reviewer_orch
from app.database import async_session
from app.models import Blueprint, GeneratedFile, PipelineStatus, Project, QAResult

MARKER = "SYNTHETIC-STEP2"
_failures: list[str] = []
_build_calls: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"   ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


# ---------------------------------------------------------------- no-spend seams
async def _no_codegen(*a, **k):
    return None, "patched-no-llm"


async def _no_review_subset(project_id, blueprint, file_ids):
    return {"passed": True, "issues_found": 0, "issues_fixed": 0,
            "files_reviewed": len(file_ids)}


def install_seams(repairs: dict[str, str]):
    """`repairs` maps filepath -> the content the 'Developer' returns on retry."""
    _build_calls.clear()

    async def _scripted_build_ticket(ticket, model, existing, contract="", repair=""):
        tid = ticket.get("id", "?")
        _build_calls.append(tid)
        title = ticket.get("title", "")
        # Find which repair applies by matching the filepath in the ticket text.
        for path, content in repairs.items():
            if path in title or path in ticket.get("description", ""):
                return {"filename": path.split("/")[-1], "filepath": path,
                        "content": content, "agent_type": "backend",
                        "ticket_id": tid, "status": "generated"}
        return {"filename": "noop.py", "filepath": "backend/app/noop.py",
                "content": "# no repair scripted\n", "agent_type": "backend",
                "ticket_id": tid, "status": "generated"}

    codegen.generate = _no_codegen
    dev_agents.build_ticket = _scripted_build_ticket
    reviewer_orch.review_subset = _no_review_subset


# ---------------------------------------------------------------- fixtures
GOOD_MAIN = '''
from fastapi import FastAPI
from backend.app.items import router as items_router

app = FastAPI()
app.include_router(items_router)

@app.get("/health")
def health():
    return {"status": "ok"}
'''

BROKEN_MAIN = '''
from fastapi import FastAPI
from backend.app.items import router as items_router

app = FastAPI()
app.include_router(items_router)

# Boom: undefined name at import time (valid syntax, fails on import).
CONFIG = UNDEFINED_SETTINGS_NAME

@app.get("/health")
def health():
    return {"status": "ok"}
'''

MAIN_MISSING_ROUTER = '''
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
'''

ITEMS = '''
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/items")
def list_items():
    return []
'''

NO_APP_AT_ALL = '''
VALUE = 1
'''


async def seed(name: str, files: list[tuple[str, str, str]],
               endpoints: list[str]) -> int:
    """Create a synthetic project + blueprint + generated_files. Returns id."""
    async with async_session() as db:
        project = Project(prompt=f"{MARKER}: {name}", status="secured",
                          summary_json=json.dumps({"build": name}))
        db.add(project)
        await db.commit()
        await db.refresh(project)
        pid = project.id

        blueprint = {
            "tech_stack": {"backend": "FastAPI"},
            "database_schema": [],
            "api_endpoints": [{"method": "GET", "path": p, "purpose": "x"}
                              for p in endpoints],
            "third_party_apis": [],
            "sprint_tickets": [
                {"id": t, "title": f"ticket {t} for {fp}", "assigned_to": "backend",
                 "description": f"Build {fp}", "dependencies": []}
                for t, fp, _ in files
            ],
            "security": {"review_model": "claude-opus-4-8", "measures": []},
            "llm_routing": {"backend_developer": "gpt-4o", "code_reviewer": "gpt-4o-mini"},
            "cloud_config": {"tier": "small"},
        }
        db.add(Blueprint(project_id=pid, blueprint_json=json.dumps(blueprint)))
        for ticket_id, filepath, content in files:
            db.add(GeneratedFile(
                project_id=pid, ticket_id=ticket_id,
                filename=filepath.split("/")[-1], filepath=filepath,
                content=content, agent_type="backend", status="generated",
            ))
        await db.commit()
    return pid


async def rows_for(pid: int) -> list[QAResult]:
    async with async_session() as db:
        res = await db.execute(
            select(QAResult).where(QAResult.project_id == pid).order_by(QAResult.id))
        return list(res.scalars().all())


async def cleanup():
    async with async_session() as db:
        res = await db.execute(select(Project.id).where(Project.prompt.like(f"{MARKER}%")))
        ids = [r[0] for r in res.all()]
        for pid in ids:
            await db.execute(delete(QAResult).where(QAResult.project_id == pid))
            await db.execute(delete(GeneratedFile).where(GeneratedFile.project_id == pid))
            await db.execute(delete(Blueprint).where(Blueprint.project_id == pid))
            await db.execute(delete(PipelineStatus).where(PipelineStatus.project_id == pid))
            await db.execute(delete(Project).where(Project.id == pid))
        await db.commit()
    return len(ids)


def show(rows) -> None:
    for r in rows:
        mark = "PASS" if r.passed else "FAIL"
        rc = r.root_cause_agent or "-"
        print(f"       {mark}  rt={r.retry_count}  {rc:<17} {r.test_name[:62]}")
        if not r.passed and r.failure_reason:
            print(f"             reason: {r.failure_reason[:110]}")


# ================================================== S1: productive retry + clearing
async def scenario_1():
    print("\n=== S1: broken app -> Developer repairs it -> failure must CLEAR ===")
    from app.qa import orchestrator as qo

    pid = await seed("s1 productive retry",
                     [("APP-1", "backend/app/main.py", BROKEN_MAIN),
                      ("BE-1", "backend/app/items.py", ITEMS)],
                     ["/api/items"])
    install_seams({"backend/app/main.py": GOOD_MAIN})
    report = await qo.run(pid)
    rows = await rows_for(pid)
    show(rows)

    boot = [r for r in rows if "did not start" in r.test_name]
    check("the boot failure was retried (retry_count > 0)",
          bool(boot) and boot[0].retry_count > 0,
          f"rows={[(r.test_name, r.retry_count) for r in boot]}")
    check("Developer was actually invoked", len(_build_calls) > 0, str(_build_calls))
    check("retry was PRODUCTIVE — the app booted afterwards",
          any(r.passed and ("happy path" in r.test_name or "/api/items" in r.test_name)
              for r in rows),
          str([r.test_name for r in rows if r.passed])[:200])
    check("resolved failure now reads PASSED, not stuck failed",
          bool(boot) and boot[0].passed is True,
          f"passed={boot[0].passed if boot else None}")
    check("resolution is recorded as such",
          bool(boot) and "resolved after" in (boot[0].failure_reason or ""),
          (boot[0].failure_reason or "")[:90] if boot else "")
    check("every row carries the same run_id",
          len({r.run_id for r in rows}) == 1 and rows[0].run_id is not None,
          str({r.run_id for r in rows}))
    check("run_id returned in the report", bool(report.get("run_id")))
    return pid


# ================================================== S2: architect_rework skips loop
async def scenario_2():
    print("\n=== S2: no app at all -> architect_rework must NOT enter the retry loop ===")
    from app.qa import orchestrator as qo

    pid = await seed("s2 architect rework",
                     [("FND-1", "backend/app/models.py", NO_APP_AT_ALL)],
                     ["/api/items"])
    install_seams({})
    await qo.run(pid)
    rows = await rows_for(pid)
    show(rows)

    row = next((r for r in rows if "no runnable app" in r.test_name), None)
    check("classified architect_rework",
          bool(row) and row.root_cause_agent == "architect_rework",
          str(row.root_cause_agent if row else None))
    check("retry_count is 0 — never sent to the Developer",
          bool(row) and row.retry_count == 0, str(row.retry_count if row else None))
    check("Developer was NEVER invoked", _build_calls == [], str(_build_calls))
    check("escalated honestly (not a silent no-op)",
          bool(row) and "escalated" in (row.failure_reason or "").lower(),
          (row.failure_reason or "")[:110] if row else "")
    return pid


# ================================================== S3: cap enforced under fixed code
async def scenario_3():
    print("\n=== S3: unfixable-by-Developer -> cap at 3, escalate, stop ===")
    from app.qa import orchestrator as qo

    pid = await seed("s3 escalation cap",
                     [("APP-1", "backend/app/main.py", BROKEN_MAIN),
                      ("BE-1", "backend/app/items.py", ITEMS)],
                     ["/api/items"])
    # The "repair" returns the SAME broken file every time.
    install_seams({"backend/app/main.py": BROKEN_MAIN})
    await qo.run(pid)
    rows = await rows_for(pid)
    show(rows)

    boot = next((r for r in rows if "did not start" in r.test_name), None)
    check("retry_count reached exactly 3",
          bool(boot) and boot.retry_count == 3, str(boot.retry_count if boot else None))
    check("never exceeds the cap", all(r.retry_count <= 3 for r in rows),
          str([r.retry_count for r in rows]))
    check("marked escalated after retries",
          bool(boot) and "escalated after retries" in (boot.failure_reason or ""),
          (boot.failure_reason or "")[:110] if boot else "")
    check("Developer called exactly 3 times, then stopped",
          len(_build_calls) == 3, f"{len(_build_calls)} calls: {_build_calls}")
    return pid


# ================================================== S4: gap 5 — missing routes
async def scenario_4():
    print("\n=== S4: designed routes missing -> must attribute to entrypoint, not no-op ===")
    from app.qa import orchestrator as qo

    pid = await seed("s4 missing routes",
                     [("APP-1", "backend/app/main.py", MAIN_MISSING_ROUTER),
                      ("BE-1", "backend/app/items.py", ITEMS)],
                     ["/api/items"])
    install_seams({"backend/app/main.py": GOOD_MAIN})
    await qo.run(pid)
    rows = await rows_for(pid)
    show(rows)

    miss = next((r for r in rows if "designed features are missing" in r.test_name), None)
    check("the missing-routes finding was RETRIED (gap 5 fixed)",
          miss is None or miss.retry_count > 0,
          f"retry_count={miss.retry_count}" if miss else "finding resolved away")
    check("Developer was invoked for it", len(_build_calls) > 0, str(_build_calls))
    check("after repair the designed route is present and tested",
          any(r.passed and "/api/items" in r.test_name for r in rows),
          str([r.test_name for r in rows])[:220])
    check("no silent retry_count=0 failure left behind",
          all(r.passed or r.retry_count > 0 or "escalated" in (r.failure_reason or "").lower()
              for r in rows),
          str([(r.test_name[:40], r.passed, r.retry_count) for r in rows if not r.passed]))
    return pid


async def main():
    removed = await cleanup()
    if removed:
        print(f"(cleaned {removed} previous synthetic project(s))")
    try:
        await scenario_1()
        await scenario_2()
        await scenario_3()
        await scenario_4()
    finally:
        pass  # leave rows in place for inspection; `cleanup()` runs next time

    print("\n" + "=" * 62)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
