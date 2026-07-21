"""Step-4 verification: prove teardown DIRECTLY, with real listings.

"Zero temp dirs before, zero after" proves nothing by itself — a QA run that
silently did nothing would pass that check too. So every scenario here samples
three points and shows the actual output:

    BEFORE  ->  DURING (resources must genuinely EXIST)  ->  AFTER (gone)

Resources tracked: the temp assembly directory, the throwaway Postgres database,
and the uvicorn child process.

Also covers the paths where teardown is easiest to get wrong: an app that never
boots, and an exception thrown mid-test (the orchestrator's `finally`).

Zero LLM spend. Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tests/test_qa_teardown.py
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile

from sqlalchemy import delete, select, text

import app.codegen as codegen
import app.developers.agents as dev_agents
import app.reviewer.orchestrator as reviewer_orch
from app.database import async_session
from app.models import Blueprint, GeneratedFile, PipelineStatus, Project, QAResult
from app.qa import assembly

MARKER = "SYNTHETIC-STEP4"
_failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"   ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


# ---------------------------------------------------------------- real listings
TEMP_GLOB = os.path.join(tempfile.gettempdir(), "qa-build-*")


def list_temp_dirs() -> list[str]:
    """gettempdir(), never a hardcoded /tmp: assembly uses mkdtemp, which honours
    TMPDIR. A listing that quietly matches nothing is the precise failure mode
    this whole file exists to catch — it must not be reintroduced here."""
    out = subprocess.run(f"ls -d {TEMP_GLOB} 2>/dev/null || true",
                         shell=True, capture_output=True, text=True).stdout
    return [l for l in out.strip().splitlines() if l.strip()]


async def list_test_dbs() -> list[str]:
    async with async_session() as db:
        rows = (await db.execute(text(
            "SELECT datname FROM pg_database WHERE datname LIKE 'qa_test_%' ORDER BY datname"
        ))).all()
    return [r[0] for r in rows]


def list_uvicorn() -> list[str]:
    """Every uvicorn process visible to this container, read from /proc.

    Two earlier versions of this were quietly useless and both printed "(none)"
    forever: the first excluded 'app.main' to skip the platform's own server, but
    the generated app launches as `backend.app.main:app` and matched that filter;
    the second shelled out to `ps`, which is not installed in python:3.12-slim,
    and `|| true` swallowed the missing binary. /proc needs no packages and
    cannot silently no-op.

    No exclusion filter is needed: this one-off container runs only the test
    process tree, so anything listed here IS a spawned test instance.
    """
    found = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\x00", b" ").decode(errors="replace").strip()
        except OSError:
            continue        # process exited between listdir and open
        if "uvicorn" in cmd:
            found.append(f"{pid} {cmd}")
    return sorted(found)


async def snapshot(tag: str) -> dict:
    dirs, dbs, procs = list_temp_dirs(), await list_test_dbs(), list_uvicorn()
    print(f"\n    ---------- {tag} ----------")
    print(f"    $ ls -d {TEMP_GLOB}")
    print("      " + ("\n      ".join(dirs) if dirs else "(none)"))
    print(f"    $ SELECT datname FROM pg_database WHERE datname LIKE 'qa_test_%'")
    print("      " + ("\n      ".join(dbs) if dbs else "(none)"))
    print(f"    /proc scan for uvicorn processes")
    print("      " + ("\n      ".join(p[:90] for p in procs) if procs else "(none)"))
    return {"dirs": dirs, "dbs": dbs, "procs": procs}


# ---------------------------------------------------------------- fixtures
GOOD_MAIN = '''
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/items")
def items():
    return []
'''

NEVER_BOOTS = '''
from fastapi import FastAPI
app = FastAPI()
raise RuntimeError("this app refuses to come up")
'''


def gf(ticket, path, content):
    return {"id": abs(hash(path)) % 100000, "ticket_id": ticket,
            "filename": path.split("/")[-1], "filepath": path,
            "content": content, "agent_type": "backend"}


# ================================================== S1: full lifecycle
async def s1_lifecycle():
    print("\n=== S1: assemble -> resources EXIST -> teardown -> gone ===")
    before = await snapshot("BEFORE")

    env = await assembly.assemble([gf("APP-1", "backend/app/main.py", GOOD_MAIN)],
                                  ["/api/items"])
    try:
        during = await snapshot("DURING (instance running)")

        check("assembly actually booted (otherwise this proves nothing)", env.ok,
              "; ".join(f.reason[:100] for f in env.failures))
        check("temp directory EXISTS mid-run",
              env.root in during["dirs"], f"root={env.root}")
        check("throwaway database EXISTS mid-run",
              env.db_name in during["dbs"], f"db={env.db_name}")
        check("uvicorn child process is ALIVE mid-run",
              env.process is not None and env.process.poll() is None)
        check("the running instance is visible in ps mid-run",
              len(during["procs"]) > len(before["procs"]),
              f"before={len(before['procs'])} during={len(during['procs'])}")
        check("a new temp dir appeared vs BEFORE",
              len(during["dirs"]) > len(before["dirs"]))
    finally:
        await assembly.teardown(env)

    after = await snapshot("AFTER teardown")
    check("temp directory REMOVED", env.root not in after["dirs"], str(env.root))
    check("directory really gone from disk", not os.path.isdir(env.root or ""))
    check("throwaway database DROPPED", env.db_name not in after["dbs"],
          str(env.db_name))
    check("child process terminated", env.process.poll() is not None,
          f"poll={env.process.poll()}")
    check("no temp dirs leaked vs BEFORE", after["dirs"] == before["dirs"])
    check("no databases leaked vs BEFORE", after["dbs"] == before["dbs"])
    check("no uvicorn processes leaked", after["procs"] == before["procs"])


# ================================================== S2: app never boots
async def s2_failed_assembly():
    print("\n=== S2: app never boots — resources must STILL be cleaned ===")
    before = await snapshot("BEFORE")
    env = await assembly.assemble([gf("APP-1", "backend/app/main.py", NEVER_BOOTS)],
                                  ["/api/items"])
    root, db_name = env.root, env.db_name
    check("assembly correctly reported failure", env.ok is False)
    check("but it still created a workspace to fail in", bool(root))

    # D3: assembly provisions the database (assembly.py:532) BEFORE launching
    # uvicorn (:553), so a never-booting app still leaves both resources behind.
    # Sample them while they exist — "gone afterwards" proves nothing on its own,
    # because an assembly that created nothing would satisfy it too.
    during = await snapshot("DURING (assembly failed, pre-teardown)")
    check("temp directory EXISTS before teardown", root in during["dirs"],
          f"root={root}")
    check("throwaway database EXISTS before teardown",
          bool(db_name) and db_name in during["dbs"], f"db={db_name}")

    await assembly.teardown(env)
    after = await snapshot("AFTER teardown")
    check("temp dir cleaned despite failure", root not in after["dirs"])
    # D2: must have BEEN created and now be gone. `db_name is None or ...` would
    # pass when nothing was ever provisioned.
    check("database cleaned despite failure",
          bool(db_name) and db_name not in after["dbs"], f"db={db_name}")
    check("nothing leaked vs BEFORE",
          after["dirs"] == before["dirs"] and after["dbs"] == before["dbs"])


# ================================================== S3: crash mid-test
async def s3_crash_during_testing():
    print("\n=== S3: exception thrown mid-test — the `finally` must still fire ===")
    from app.qa import level1, orchestrator as qo

    before = await snapshot("BEFORE")

    original = level1.run

    async def _boom(env):
        raise RuntimeError("simulated crash inside Level 1")

    level1.run = _boom
    try:
        outcomes, env = await qo._run_round(
            [gf("APP-1", "backend/app/main.py", GOOD_MAIN)], ["/api/items"])
    finally:
        level1.run = original

    after = await snapshot("AFTER (crash + teardown)")
    # D4: strictly the crash outcome. `or not o.passed` made this pass on ANY
    # failing outcome for any reason — including one where the crash was
    # swallowed and something unrelated happened to fail.
    check("the crash was recorded as a finding, not swallowed",
          any("unexpected error" in o.name for o in outcomes),
          str([o.name for o in outcomes])[:160])
    check("QA did not propagate the crash", isinstance(outcomes, list))

    # D2: teardown() deliberately does not null these fields (assembly.py:589),
    # so each resource can be proven CREATED and then proven GONE. Accepting
    # None as success would let a run that built nothing report a clean teardown.
    check("a workspace was actually created before the crash", bool(env.root))
    check("temp dir still cleaned after a crash",
          env.root not in after["dirs"], str(env.root))
    check("a throwaway database was actually created before the crash",
          bool(env.db_name), f"db={env.db_name}")
    check("database still dropped after a crash",
          bool(env.db_name) and env.db_name not in after["dbs"],
          f"db={env.db_name}")
    check("a uvicorn child process was actually started before the crash",
          env.process is not None)
    check("process still killed after a crash",
          env.process is not None and env.process.poll() is not None,
          f"poll={env.process.poll() if env.process else 'no process'}")
    check("nothing leaked vs BEFORE",
          after["dirs"] == before["dirs"] and after["dbs"] == before["dbs"]
          and after["procs"] == before["procs"])


# ================================================== S4: full orchestrator run
async def s4_full_run():
    print("\n=== S4: full orchestrator pass (incl. retries) — no accumulation ===")
    from app.qa import orchestrator as qo

    # D1: a retry has to be COUNTED, not inferred. The original check here
    # asserted report["total"] > 0, but total is len(final) (orchestrator.py:437)
    # — the number of distinct test NAMES — which is > 0 for any pass that
    # produced a single outcome, including one that assembled exactly once and
    # never retried. This is the only scenario covering accumulation ACROSS
    # cycles, so it has to prove the cycles actually happened.
    calls = {"assemble": 0, "build_ticket": 0}

    async def _no_codegen(*a, **k):
        return None, "patched"

    async def _no_review(project_id, blueprint, file_ids):
        return {"passed": True, "issues_found": 0, "issues_fixed": 0,
                "files_reviewed": len(file_ids)}

    async def _scripted(ticket, model, existing, contract=""):
        calls["build_ticket"] += 1
        return {"filename": "main.py", "filepath": "backend/app/main.py",
                "content": GOOD_MAIN, "agent_type": "backend",
                "ticket_id": ticket.get("id", "APP-1"), "status": "generated"}

    real_assemble = assembly.assemble

    async def _counting_assemble(files, expected_endpoints=None):
        calls["assemble"] += 1
        return await real_assemble(files, expected_endpoints)

    originals = (codegen.generate, reviewer_orch.review_subset,
                 dev_agents.build_ticket, assembly.assemble)
    codegen.generate = _no_codegen
    reviewer_orch.review_subset = _no_review
    dev_agents.build_ticket = _scripted
    assembly.assemble = _counting_assemble

    try:
        before = await snapshot("BEFORE")

        # Broken app -> forces at least one retry -> at least two assemble cycles.
        async with async_session() as db:
            p = Project(prompt=f"{MARKER}: teardown across retries", status="secured",
                        summary_json=json.dumps({"build": "x"}))
            db.add(p)
            await db.commit()
            await db.refresh(p)
            pid = p.id
            db.add(Blueprint(project_id=pid, blueprint_json=json.dumps({
                "api_endpoints": [{"method": "GET", "path": "/api/items"}],
                "sprint_tickets": [{"id": "APP-1",
                                    "title": "entrypoint backend/app/main.py",
                                    "assigned_to": "backend",
                                    "description": "Build backend/app/main.py",
                                    "dependencies": []}],
                "llm_routing": {"backend_developer": "gpt-4o"},
                "security": {}, "database_schema": [],
            })))
            db.add(GeneratedFile(project_id=pid, ticket_id="APP-1", filename="main.py",
                                 filepath="backend/app/main.py", content=NEVER_BOOTS,
                                 agent_type="backend", status="generated"))
            await db.commit()

        report = await qo.run(pid)
        after = await snapshot("AFTER full run")
    finally:
        # Restore, so any scenario added after this one is not silently poisoned
        # by patches left in place.
        (codegen.generate, reviewer_orch.review_subset,
         dev_agents.build_ticket, assembly.assemble) = originals

    # Retry evidence read back from the rows QA actually persisted — independent
    # of the in-process counters above.
    async with async_session() as db:
        rows = (await db.execute(
            select(QAResult.test_name, QAResult.retry_count)
            .where(QAResult.project_id == pid).order_by(QAResult.id)
        )).all()
    max_retry = max([r[1] or 0 for r in rows], default=0)

    print(f"    report: rounds produced {report['total']} test(s), "
          f"{report['passed']} passed")
    print(f"    assemble() calls={calls['assemble']}   "
          f"build_ticket() calls={calls['build_ticket']}   "
          f"max retry_count in qa_results={max_retry}")
    for name, rc in rows:
        print(f"      retry_count={rc}  {name[:66]}")

    check("assembly really ran more than once (a retry cycle happened)",
          calls["assemble"] >= 2, f"assemble calls={calls['assemble']}")
    check("the Developer was actually invoked to repair the app",
          calls["build_ticket"] >= 1, f"build_ticket calls={calls['build_ticket']}")
    check("the retry is recorded in qa_results (retry_count >= 1)",
          max_retry >= 1, f"max retry_count={max_retry}")
    check("no temp dirs accumulated across rounds", after["dirs"] == before["dirs"],
          f"before={before['dirs']} after={after['dirs']}")
    check("no databases accumulated across rounds", after["dbs"] == before["dbs"],
          f"before={before['dbs']} after={after['dbs']}")
    check("no uvicorn processes accumulated", after["procs"] == before["procs"])


async def cleanup():
    async with async_session() as db:
        ids = [r[0] for r in (await db.execute(
            select(Project.id).where(Project.prompt.like(f"{MARKER}%")))).all()]
        for pid in ids:
            for model in (QAResult, GeneratedFile, Blueprint, PipelineStatus):
                await db.execute(delete(model).where(model.project_id == pid))
            await db.execute(delete(Project).where(Project.id == pid))
        await db.commit()
    return len(ids)


async def main():
    removed = await cleanup()
    if removed:
        print(f"(cleaned {removed} previous synthetic project(s))")
    await s1_lifecycle()
    await s2_failed_assembly()
    await s3_crash_during_testing()
    await s4_full_run()
    await cleanup()

    print("\n" + "=" * 64)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
