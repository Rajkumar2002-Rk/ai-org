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


async def scenario_stub_recovers_on_retry():
    print("\n=== S3: a stub that succeeds on the RETRY pass -> built ===")
    pid = await _make_project()

    calls: dict[str, int] = {}

    async def _bt(ticket, model, existing, contract=""):
        # BE-1 flakes on the FIRST attempt (transient), succeeds on the retry.
        if ticket["id"] == "BE-1":
            calls["BE-1"] = calls.get("BE-1", 0) + 1
            if calls["BE-1"] == 1:
                stub = agents._pin_path(agents._stub(ticket["assigned_to"], ticket), ticket)
                return {**stub, "agent_type": ticket["assigned_to"],
                        "ticket_id": ticket["id"], "status": agents.STUB_STATUS}
        return _good(ticket)

    agents.build_ticket = _bt
    summary = await orch.run(pid, BP)
    print(f"    summary={summary}   build_ticket(BE-1) calls={calls.get('BE-1')}")
    check("BE-1 was retried (called twice)", calls.get("BE-1") == 2, str(calls))
    check("a transient stub self-heals -> status 'built'",
          summary["status"] == "built", str(summary))
    check("no surviving stubs in the summary", summary["stubbed"] == [], str(summary))
    check("build stage marked done", await _build_stage_status(pid) == "done")
    check("project marked built", await _project_status(pid) == "built")

    # The stub row was OVERWRITTEN with real code, not left as placeholder.
    async with async_session() as db:
        row = (await db.execute(select(GeneratedFile.status, GeneratedFile.content)
               .where(GeneratedFile.project_id == pid,
                      GeneratedFile.ticket_id == "BE-1"))).first()
    check("BE-1's stub row was replaced with generated code",
          row is not None and row[0] == "generated" and "TODO" not in (row[1] or ""),
          str(row))


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


def test_auth_symbol_contract():
    """Regression: projects 435 ('Auth0Config') and 513 ('verify_token') both died
    at boot because a backend file imported a name auth.py never exported. The auth
    symbol contract must now pin the exact export names into every backend importer's
    prompt (the symbol-level twin of module-path pinning)."""
    from app.architect import builder

    check("auth exports pinned to the real dependency names",
          builder.AUTH_EXPORTS == ("get_current_user", "get_current_admin_user"))
    at = builder._auth_ticket({"provider": "TestIDP", "tier": "basic",
                               "mfa_required": False, "passkeys": "optional",
                               "triggers": {}})
    check("auth ticket exposes exactly those names",
          all(n in at["description"] for n in builder.AUTH_EXPORTS), at["description"])

    # menu_upload.py was the 513 culprit's import chain — it must now get the exact
    # names AND be told not to invent the guessed one that broke boot.
    p = agents._base_prompt(
        {"id": "MENU-3", "assigned_to": "backend",
         "filepath": "backend/app/routes/menu_upload.py",
         "title": "menu upload", "description": "admin upload"}, [])
    check("importer prompt pins the exact auth export names",
          all(n in p for n in builder.AUTH_EXPORTS), p[:300])
    check("importer prompt forbids the guessed name that broke 513 (verify_token)",
          "verify_token" in p and "Do NOT invent" in p)
    ps = agents._base_prompt(
        {"id": "SEC-1", "assigned_to": "backend",
         "filepath": "backend/app/security.py", "title": "security",
         "description": "authorization"}, [])
    check("security.py (the 513 file that guessed) gets the contract",
          "AUTH CONTRACT" in ps)
    pa = agents._base_prompt(
        {"id": "AUTH-1", "assigned_to": "backend", "filepath": "backend/app/auth.py",
         "title": "auth", "description": "x"}, [])
    check("auth.py itself is NOT told to import from itself", "AUTH CONTRACT" not in pa)
    pf = agents._base_prompt(
        {"id": "FE-1", "assigned_to": "frontend", "filepath": "frontend/app/page.tsx",
         "title": "ui", "description": "x"}, [])
    check("frontend files are excluded", "AUTH CONTRACT" not in pf)


def test_response_model_rule():
    """Regression: projects 342 and 573 both died at startup with 'Invalid args for
    response field' because a route used a SQLAlchemy ORM model as its response_model
    / return annotation. The Backend Developer system prompt must forbid that."""
    from app.developers import agents

    sys_be = agents._system("backend")
    check("backend prompt: response_model must be a Pydantic schema, never an ORM model",
          "response_model" in sys_be and "Pydantic" in sys_be and "ORM" in sys_be, sys_be)
    check("backend prompt: names the exact FastAPI startup failure",
          "Invalid args for response field" in sys_be)
    check("backend prompt: offers response_model=None as the escape hatch",
          "response_model=None" in sys_be)
    check("frontend prompt does NOT carry the backend FastAPI rule",
          "response_model" not in agents._system("frontend"))


def test_pydantic_v2_rule():
    """Regression (project 829): the generated order.py used the Pydantic v1
    spelling `conlist(OrderItem, min_items=1)`, which raises TypeError at import
    under Pydantic v2 and stopped the whole app from booting. The Backend Developer
    system prompt must pin the v2 argument names so no backend file emits v1."""
    from app.developers import agents

    sys_be = agents._system("backend")
    check("backend prompt: pins Pydantic v2 (min_length/max_length)",
          "min_length" in sys_be and "max_length" in sys_be, sys_be)
    check("backend prompt: forbids the v1 names that broke 829 (min_items/max_items)",
          "min_items" in sys_be and "max_items" in sys_be, sys_be)
    check("backend prompt: names conlist explicitly (the 829 call site)",
          "conlist" in sys_be)
    check("frontend prompt does NOT carry the backend Pydantic rule",
          "min_items" not in agents._system("frontend"))


def test_stub_function_detection():
    """Regression (project 888): the generated menu_upload.py looked complete but its
    core `parse_menu_items` was a placeholder `return []`, so extraction pulled 0
    items from every menu while endpoints answered 200. The deterministic detector
    must catch a work-named function whose whole body is a stub."""
    stubs = {
        "return []": "def parse_menu_items(t):\n    return []\n",
        "return None": "def extract_items(x):\n    return None\n",
        "bare return": "def parse_data(x):\n    return\n",
        "pass": "def process_thing(x):\n    pass\n",
        "NotImplementedError": "def extract_text(x):\n    raise NotImplementedError\n",
        "docstring only": 'def parse_all(x):\n    """does it"""\n',
        "docstring + return []": 'def parse_x(t):\n    """p"""\n    return []\n',
        "return {}": "def build_map(x):\n    return {}\n",
    }
    for label, src in stubs.items():
        check(f"stub caught: {label}", len(agents.stub_functions(src)) == 1, str(agents.stub_functions(src)))

    real = ("def parse_menu_items(t):\n"
            "    items = []\n"
            "    for line in t.splitlines():\n"
            "        items.append(line)\n"
            "    return items\n")
    check("real parse function is NOT flagged", agents.stub_functions(real) == [])
    cond = ("def extract(t):\n"
            "    if not t:\n"
            "        return []\n"
            "    return do_parse(t)\n")
    check("empty-return as a GUARD (not sole body) is NOT flagged", agents.stub_functions(cond) == [])
    helper = "def default_settings():\n    return {}\n"
    check("trivial NON-work-named helper is not flagged by default",
          agents.stub_functions(helper) == [])
    check("...but IS flagged when only_work_named=False",
          agents.stub_functions(helper, only_work_named=False) == ["default_settings"])
    check("syntax error yields no false stub (it's a separate finding)",
          agents.stub_functions("def broken(:\n  return []") == [])


def test_build_gate():
    """The build-stage gate rejects a real-looking file that (a) stubbed a core work
    function, (b) uses Depends(async_session) instead of Depends(get_db), or (c)
    renamed a contract column in its model — retried, then fails the build. Same 'a
    stub is not built' mechanism, extended to the real-code-but-wrong bugs found in 888."""
    from app.developers import orchestrator as orch
    bp = {"database_schema": [{"table": "menu_items", "columns": [
        {"name": "id", "type": "int"}, {"name": "name", "type": "str"},
        {"name": "source", "type": "str"}]}]}
    built = [
        {"ticket_id": "MENU-3", "content": "def parse_menu_items(t):\n    return []\n", "status": "generated"},
        {"ticket_id": "MENU-1", "content": "d: X = Depends(async_session)\n", "status": "generated"},
        {"ticket_id": "FND-1", "content": ("class MenuItem(Base):\n"
            "    __tablename__ = 'menu_items'\n"
            "    id = Column(Integer)\n    name = Column(String)\n"
            "    source_name = Column(String)\n"), "status": "generated"},  # renamed source->source_name
        {"ticket_id": "BE-1", "content": "def handle_order():\n    return {'ok': True}\n", "status": "generated"},
    ]
    stubbed = orch._collect_stubs(built, bp, 1)
    flagged = sorted(s["ticket_id"] for s in stubbed)
    check("gate flags stub-fn, bad-session-dep, and schema-rename tickets",
          flagged == ["FND-1", "MENU-1", "MENU-3"], str(flagged))
    check("the clean ticket is left untouched", built[3]["status"] == "generated")
    check("schema-rename problem names the missing contract column",
          any("menu_items.source" in p for r in stubbed if r["ticket_id"] == "FND-1"
              for p in r.get("gate_problems", [])), str(stubbed))


def test_session_dependency_rule():
    """Regression (project 888): Depends(async_session) 422'd every request. Detector
    + Backend-Developer prompt must forbid it in favour of Depends(get_db)."""
    check("bad_session_dependency detects Depends(async_session)",
          agents.bad_session_dependency("db = Depends(async_session)") is True)
    check("Depends(get_db) is NOT flagged",
          agents.bad_session_dependency("db = Depends(get_db)") is False)
    sysp = agents._system("backend")
    check("backend prompt mandates Depends(get_db), forbids Depends(async_session)",
          "Depends(get_db)" in sysp and "Depends(async_session)" in sysp, sysp)


def test_schema_adherence():
    """Regression (project 888): the model renamed contract column `source` to
    `source_name`, 500ing the published GET /menu. Detector catches a missing/renamed
    contract column; the prompt forbids renaming."""
    schema = [{"table": "menu_items", "columns": [
        {"name": "id", "type": "int"}, {"name": "source", "type": "str"}]}]
    renamed = ("class MenuItem(Base):\n    __tablename__ = 'menu_items'\n"
               "    id = Column(Integer)\n    source_name = Column(String)\n")
    check("renamed contract column is caught (menu_items.source missing)",
          agents.model_schema_mismatches(renamed, schema) == ["menu_items.source"])
    correct = ("class MenuItem(Base):\n    __tablename__ = 'menu_items'\n"
               "    id = Column(Integer)\n    source = Column(String)\n")
    check("a model with the exact contract columns is clean",
          agents.model_schema_mismatches(correct, schema) == [])
    check("extra model columns are allowed (only missing contract cols flagged)",
          agents.model_schema_mismatches(correct + "    image_url = Column(String)\n", schema) == [])
    sysp = agents._system("backend")
    check("backend prompt mandates exact contract column names (no rename)",
          "schema-adherence" in sysp.lower() and "source_name" in sysp, sysp)


def test_no_stub_prompt_rule():
    """The Developer system prompt forbids placeholder/stub functions — same
    category as the response_model and Pydantic v2 rules."""
    for at in ("backend", "frontend"):
        sysp = agents._system(at)
        check(f"{at} prompt forbids placeholder stubs (return []/pass/TODO)",
              "placeholder" in sysp.lower() and "return []" in sysp, at)
        check(f"{at} prompt flags a work function returning empty as a bug",
              "silently do nothing" in sysp, at)


def test_frontend_completeness_gate():
    """Regression (project 1007): the generated admin/menu/review/page.tsx was
    TRUNCATED mid-JSX (styles/inputStyle undefined, component unclosed). It passed
    build + QA (whose real next build is opt-in/off) and only died at the deploy's
    next build. The build gate must catch an incomplete/unbalanced frontend file."""
    import os
    from app.developers import orchestrator as orch
    fx = os.path.join(os.path.dirname(__file__), "fixtures", "truncated_review_page_1007.tsx")
    truncated = open(fx, encoding="utf-8").read()

    check("1007's EXACT truncated review page is flagged",
          agents.frontend_incomplete("frontend/app/admin/menu/review/page.tsx", truncated) is not None,
          str(agents.frontend_incomplete("x.tsx", truncated)))
    check("a complete .tsx is NOT flagged", agents.frontend_incomplete(
        "frontend/app/page.tsx",
        "export default function P(){ return <div>{[1,2].map(x=>(<span key={x}/>))}</div>; }") is None)
    check("unterminated string is flagged (truncation)",
          agents.frontend_incomplete("a.tsx", 'const x = "oops') is not None)
    check("unterminated block comment is flagged",
          agents.frontend_incomplete("a.ts", "const x = 1;\n/* not closed") is not None)
    check("a non-JS file (.css) is ignored",
          agents.frontend_incomplete("frontend/app/globals.css", "body {") is None)
    check("a regex with delimiters does NOT false-flag a complete file",
          agents.frontend_incomplete("a.ts", "const r = /[({]/g; const y = (1);") is None)

    built = [
        {"ticket_id": "MENU-4", "filepath": "frontend/app/admin/menu/review/page.tsx",
         "content": truncated, "status": "generated"},
        {"ticket_id": "FE-1", "filepath": "frontend/app/page.tsx",
         "content": "export default function P(){ return <div/>; }", "status": "generated"},
    ]
    stubbed = orch._collect_stubs(built, {}, 1)
    check("build gate flags the truncated frontend ticket (retry -> fail)",
          [s["ticket_id"] for s in stubbed] == ["MENU-4"], str(stubbed))
    check("the complete frontend ticket is left untouched", built[1]["status"] == "generated")


async def main():
    original = agents.build_ticket
    removed = await cleanup()
    if removed:
        print(f"(cleaned {removed} previous synthetic project(s))")
    try:
        test_auth_symbol_contract()
        test_response_model_rule()
        test_pydantic_v2_rule()
        test_stub_function_detection()
        test_build_gate()
        test_no_stub_prompt_rule()
        test_session_dependency_rule()
        test_schema_adherence()
        test_frontend_completeness_gate()
        await scenario_all_good()
        await scenario_one_stub()
        await scenario_stub_recovers_on_retry()
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
