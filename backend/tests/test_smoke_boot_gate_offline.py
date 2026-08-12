"""Offline proof: the smoke-boot gate runs AFTER the Developer agents and BEFORE the
Opus security review. A build that cannot boot must NEVER reach the security review —
it fails fast and routes back to the Developer stage, saving the Opus spend.

Reproduces last night's pattern: three runs each paid for a full security review on
code that then failed to boot at QA. No LLM, no real assembly/boot, no reviewer spend
— every expensive seam is patched.

Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
    backend python tests/test_smoke_boot_gate_offline.py
"""
import asyncio
import json
import sys

import app.main as main
from app.qa import assembly as qa_assembly
from app.database import async_session
from app.models import Blueprint, GeneratedFile, PipelineStatus, Project
from app.redis_client import redis_client
from sqlalchemy import delete, select

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {label}")
    else:
        FAIL += 1
        print(f"[FAIL] {label}  {detail}")


class _Fail:
    def __init__(self, name, reason=""):
        self.test_name = name
        self.reason = reason


class _Env:
    """Stand-in for qa.assembly.TestEnv — only .ok and .failures are read."""
    def __init__(self, ok, failures=None):
        self.ok = ok
        self.failures = failures or []


reviewer_calls = {"n": 0}


async def _seed_project() -> int:
    async with async_session() as db:
        p = Project(prompt="SMOKE-BOOT-GATE-TEST", status="built")
        db.add(p)
        await db.commit()
        await db.refresh(p)
        db.add(Blueprint(project_id=p.id, blueprint_json=json.dumps({
            "sprint_tickets": [{"id": "BE-1"}],
            "api_endpoints": [{"path": "/health"}],
        })))
        db.add(GeneratedFile(
            project_id=p.id, ticket_id="BE-1", filename="main.py",
            filepath="backend/app/main.py", content="x", agent_type="backend",
            status="done"))
        await db.commit()
        return p.id


async def _cleanup(pid: int) -> None:
    async with async_session() as db:
        await db.execute(delete(Project).where(Project.id == pid))
        await db.commit()
    await redis_client.delete(main._build_key(pid))
    await redis_client.delete(main._secure_key(pid))


async def _smoke_stage(pid: int):
    async with async_session() as db:
        row = (await db.execute(
            select(PipelineStatus.status, PipelineStatus.error_message)
            .where(PipelineStatus.project_id == pid,
                   PipelineStatus.stage == "smoke_boot")
            .order_by(PipelineStatus.id.desc()).limit(1))).first()
    return (row[0], row[1]) if row else (None, None)


async def _security_stage_exists(pid: int) -> bool:
    async with async_session() as db:
        row = (await db.execute(
            select(PipelineStatus.id)
            .where(PipelineStatus.project_id == pid,
                   PipelineStatus.stage == "security_review").limit(1))).first()
    return row is not None


async def main_test() -> None:
    # Patch the expensive seams: Developers report "built" (no LLM); the reviewer is
    # a spy; assembly.teardown is a no-op. assemble() is swapped per scenario below.
    async def fake_build_run(pid, bp):
        return {"status": "built", "total": 1, "stubbed": []}

    async def fake_reviewer_run(pid, bp):
        reviewer_calls["n"] += 1
        return {"passed": True, "files": []}

    async def fake_teardown(env):
        return None

    main.orchestrator.run = fake_build_run
    main.reviewer_orchestrator.run = fake_reviewer_run
    qa_assembly.teardown = fake_teardown

    # This suite tests the smoke-boot gate -> security-review flow, so the review
    # must be ON regardless of the ambient SECURITY_REVIEW_ENABLED debug flag (which
    # is set to false during local codegen debugging).
    from app.config import settings as _settings
    _orig_sre = _settings.security_review_enabled
    _settings.security_review_enabled = True

    # ---------------- BROKEN build: the app does not boot ----------------
    _FAKE_TB = (
        "Traceback (most recent call last):\n  ... fastapi/utils.py line 98 ...\n"
        "fastapi.exceptions.FastAPIError: Invalid args for response field! check "
        "that <class 'backend.app.models.Order'> is a valid Pydantic field type")

    async def assemble_broken(files, expected=None):
        return _Env(False, [_Fail("assembly: app did not start", _FAKE_TB)])

    qa_assembly.assemble = assemble_broken
    pid = await _seed_project()
    reviewer_calls["n"] = 0
    await main._run_build(pid)

    check("broken build -> build status is 'boot_failed', not 'done' (fails fast)",
          (await redis_client.get(main._build_key(pid))) == "boot_failed",
          str(await redis_client.get(main._build_key(pid))))
    _status, _err = await _smoke_stage(pid)
    check("broken build -> smoke_boot stage recorded as error", _status == "error")
    check("broken build -> smoke_boot stage CAPTURES the boot traceback (diagnosable)",
          "Invalid args for response field" in (_err or ""), str(_err)[:160])

    # The security review must REFUSE — never call the (expensive) reviewer.
    await main._run_review(pid)
    check("broken build -> Opus security review REFUSED (reviewer NEVER ran)",
          reviewer_calls["n"] == 0)
    check("broken build -> secure status is error",
          (await redis_client.get(main._secure_key(pid))) == "error")
    check("broken build -> NO security_review stage was ever created",
          (await _security_stage_exists(pid)) is False)
    await _cleanup(pid)

    # ---------------- GOOD build: the app boots ----------------
    async def assemble_good(files, expected=None):
        return _Env(True, [])

    qa_assembly.assemble = assemble_good
    pid2 = await _seed_project()
    reviewer_calls["n"] = 0
    await main._run_build(pid2)

    check("bootable build -> build status 'done'",
          (await redis_client.get(main._build_key(pid2))) == "done")
    _status2, _ = await _smoke_stage(pid2)
    check("bootable build -> smoke_boot stage recorded as done", _status2 == "done")
    await main._run_review(pid2)
    check("bootable build -> Opus security review RUNS (reviewer called once)",
          reviewer_calls["n"] == 1)
    await _cleanup(pid2)

    _settings.security_review_enabled = _orig_sre
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("RESULT: ALL CHECKS PASSED ✓")
        sys.exit(0)
    print("RESULT: FAILURES ✗")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main_test())
