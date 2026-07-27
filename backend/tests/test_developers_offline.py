"""Build-stage guard: a stub means the build did NOT succeed.

A stub is what build_ticket returns when generation produced nothing usable —
the LLM was unavailable or returned nothing on every attempt. On the first real
baseline run an OpenAI quota outage did exactly this to all 8 backend tickets,
and the build still reported "done": Opus then certified 8 TODO-text files and
only QA caught it, via syntax errors. A build that is partly placeholder text has
not been built, and must not flow into the security review as if it had.

Drives the REAL developers.orchestrator.run() against a temp Postgres — only
agents.build_ticket is patched, so the wave scheduler, DB writes and the
stub-detection gate are all exercised for real. Zero LLM spend.

Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tests/test_developers_offline.py
"""
import asyncio
import json
import sys

from sqlalchemy import delete, select

import app.developers.agents as agents
import app.developers.orchestrator as orch
from app.database import async_session
from app.models import Blueprint, GeneratedFile, PipelineStatus, Project

MARKER = "SYNTHETIC-DEVSTUB"
_failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"   ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


BP = {
    "sprint_tickets": [
        {"id": "FND-1", "title": "models", "assigned_to": "backend",
         "filepath": "backend/app/models.py", "description": "x", "dependencies": []},
        {"id": "BE-1", "title": "routes", "assigned_to": "backend",
         "filepath": "backend/app/routes/menu.py", "description": "x", "dependencies": []},
        {"id": "APP-1", "title": "entrypoint", "assigned_to": "backend",
         "filepath": "backend/app/main.py", "description": "x", "dependencies": ["FND-1"]},
    ],
    "llm_routing": {}, "security": {}, "database_schema": [], "api_endpoints": [],
}


async def _make_project() -> int:
    async with async_session() as db:
        p = Project(prompt=f"{MARKER}: build gate", status="secured",
                    summary_json=json.dumps({"build": "x"}))
        db.add(p)
        await db.commit()
        await db.refresh(p)
        pid = p.id
        db.add(Blueprint(project_id=pid, blueprint_json=json.dumps(BP)))
        await db.commit()
    return pid


async def _project_status(pid: int) -> str:
    async with async_session() as db:
        return (await db.get(Project, pid)).status


async def _build_stage_status(pid: int) -> str | None:
    async with async_session() as db:
        row = (await db.execute(
            select(PipelineStatus.status).where(PipelineStatus.project_id == pid,
                                                PipelineStatus.stage == "building")
            .order_by(PipelineStatus.id.desc()).limit(1))).first()
        return row[0] if row else None


def _good(ticket, *a, **k):
    return {"filename": ticket["filepath"].rpartition("/")[2],
            "filepath": ticket["filepath"], "content": "x = 1\n",
            "agent_type": ticket.get("assigned_to", "backend"),
            "ticket_id": ticket["id"], "status": "generated"}


async def scenario_all_good():
    print("\n=== S1: every ticket generates real code -> built ===")
    pid = await _make_project()

    async def _bt(ticket, model, existing, contract=""):
        return _good(ticket)

    agents.build_ticket = _bt
    summary = await orch.run(pid, BP)
    print(f"    summary={summary}")
    check("returns status 'built'", summary["status"] == "built", str(summary))
    check("no tickets stubbed", summary["stubbed"] == [])
    check("build stage marked done", await _build_stage_status(pid) == "done")
    check("project marked built", await _project_status(pid) == "built")


async def scenario_one_stub():
    print("\n=== S2: ONE ticket produces only a stub -> build_failed ===")
    pid = await _make_project()

    async def _bt(ticket, model, existing, contract=""):
        # BE-1 is the ticket the 'provider' failed on: real build_ticket returns
        # the STUB_STATUS placeholder in exactly this case (last is None).
        if ticket["id"] == "BE-1":
            stub = agents._pin_path(agents._stub(ticket["assigned_to"], ticket), ticket)
            return {**stub, "agent_type": ticket["assigned_to"],
                    "ticket_id": ticket["id"], "status": agents.STUB_STATUS}
        return _good(ticket)

    agents.build_ticket = _bt
    summary = await orch.run(pid, BP)
    print(f"    summary={summary}")
    check("returns status 'build_failed' (NOT built)",
          summary["status"] == "build_failed", str(summary))
    check("names the stubbed ticket", summary["stubbed"] == ["BE-1"], str(summary["stubbed"]))
    check("build stage marked ERROR, not done",
          await _build_stage_status(pid) == "error")
    check("project marked build_failed, never built",
          await _project_status(pid) == "build_failed")

    # All three files still persisted (nothing lost) — but one is a stub.
    async with async_session() as db:
        rows = (await db.execute(select(GeneratedFile.ticket_id, GeneratedFile.status)
                                 .where(GeneratedFile.project_id == pid))).all()
    check("all 3 files were still written to disk", len(rows) == 3, str(rows))
    check("the stub is recorded with STUB_STATUS, distinct from needs_review",
          any(s == agents.STUB_STATUS for _, s in rows), str(rows))


async def cleanup():
    async with async_session() as db:
        ids = [r[0] for r in (await db.execute(
            select(Project.id).where(Project.prompt.like(f"{MARKER}%")))).all()]
        for pid in ids:
            for model in (GeneratedFile, Blueprint, PipelineStatus):
                await db.execute(delete(model).where(model.project_id == pid))
            await db.execute(delete(Project).where(Project.id == pid))
        await db.commit()
    return len(ids)


async def main():
    original = agents.build_ticket
    removed = await cleanup()
    if removed:
        print(f"(cleaned {removed} previous synthetic project(s))")
    try:
        await scenario_all_good()
        await scenario_one_stub()
    finally:
        agents.build_ticket = original
        await cleanup()

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
