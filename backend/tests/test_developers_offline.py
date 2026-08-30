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

    async def _bt(ticket, model, existing, contract="", repair=""):
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

    async def _bt(ticket, model, existing, contract="", repair=""):
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

    async def _bt(ticket, model, existing, contract="", repair=""):
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


def test_frontend_item_image_rule():
    """Run 1843: menu items got an image_url end-to-end (schema/admin/API), but the
    CUSTOMER-facing pages (public menu, order) are LLM-generated, so whether the photo
    actually shows was left to chance. The frontend developer prompt must MANDATE
    rendering image_url as an <img> wherever items are shown — a build-blocking gate
    would be disproportionate (fail a whole app over a thumbnail), so this is enforced as
    a strong prompt rule, like the API-base and Auth0 rules."""
    from app.developers import agents
    pf = agents._system("frontend")
    check("frontend prompt mandates rendering image_url as an <img>",
          "image_url" in pf and "<img" in pf)
    check("frontend prompt covers the customer-facing pages (menu + order)",
          "menu page" in pf and "order page" in pf)
    check("frontend prompt says to omit the image when image_url is empty (no broken img)",
          "omit" in pf and ("null" in pf or "empty" in pf))
    # It is a FRONTEND-only rule — backend files never get it.
    check("backend prompt does NOT carry the frontend image rule",
          "<img" not in agents._system("backend"))


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


def test_missing_endpoint_attribution():
    """Run 1557: GET /orders/{order_id} was designed but never generated. The
    endpoint-completeness repair attributes a missing endpoint to the route file
    sharing the longest path-prefix with it, so the regeneration lands in the right
    place. Tests the deterministic building blocks (the full repair is exercised live)."""
    from app.developers import orchestrator as orch

    # _routes_in reconstructs full paths including an APIRouter(prefix=...).
    check("_routes_in reads a plain decorator path",
          orch._routes_in("@router.post('/orders')\n") == ["/orders"])
    check("_routes_in normalises a path param",
          orch._routes_in("@router.get('/orders/{order_id}/pay')\n") == ["/orders/{}/pay"])
    check("_routes_in prepends an APIRouter prefix",
          orch._routes_in("router = APIRouter(prefix='/orders')\n@router.get('/{id}')\n")
          == ["/orders/{}"])

    check("_shared_segments counts the common path prefix",
          orch._shared_segments("/orders/{}", "/orders/{}/pay") == 2
          and orch._shared_segments("/orders/{}", "/menu") == 0)

    # Attribution: /orders/{order_id} should map to the file with the longest shared
    # prefix — order_be_2 (/orders/{}/pay, 2 segments) over order (/orders, 1 segment).
    order_py = "router = APIRouter()\n@router.post('/orders')\n"
    order2_py = "router = APIRouter()\n@router.post('/orders/{order_id}/pay')\n"
    menu_py = "router = APIRouter()\n@router.get('/menu')\n"
    files = {"order.py": order_py, "order2.py": order2_py, "menu.py": menu_py}
    from app.qa.assembly import _norm_path
    nmp = _norm_path("/orders/{order_id}")
    scored = {name: max((orch._shared_segments(nmp, r) for r in orch._routes_in(c)), default=0)
              for name, c in files.items()}
    best = max(scored, key=scored.get)
    check("a missing /orders/{order_id} attributes to the deepest /orders route file",
          best == "order2.py" and scored["order2.py"] == 2, str(scored))
    check("an unrelated route file is not a candidate (score 0)", scored["menu.py"] == 0)


def test_missing_in_project_module_gate():
    """Run 1614: order.py did `from backend.app.catalog import get_catalog_prices`, but
    catalog.py was NEVER generated -> ModuleNotFoundError at boot. Fix #16 used to skip a
    module not in the set (treated as third-party); now an in-project-SHAPED module that
    was never generated is flagged. A genuinely third-party module is still skipped."""
    files = [
        {"filepath": "backend/app/models.py", "content": "class Order:\n    pass\n"},
        {"filepath": "backend/app/routes/order.py",
         "content": "from backend.app.catalog import get_catalog_prices\n"
                    "from backend.app.models import Order\n"
                    "from fastapi import APIRouter\nimport sqlalchemy\n"},
    ]
    idx = agents.build_symbol_index(files)
    f = agents.import_symbol_mismatches(files[1]["content"], "backend/app/routes/order.py", idx)
    missing = [(x["module"], x["symbol"]) for x in f if x.get("missing_module")]
    check("a missing in-project module (backend.app.catalog) is flagged",
          ("backend.app.catalog", "get_catalog_prices") in missing, str(f))
    check("a real in-project import (backend.app.models.Order) is NOT flagged",
          all(x["module"] != "backend.app.models" for x in f), str(f))
    check("third-party modules (fastapi, sqlalchemy) are NOT flagged",
          all(x["module"] not in ("fastapi", "sqlalchemy") for x in f), str(f))
    rt = agents.repair_instructions({"symbol_repairs": [x for x in f if x.get("missing_module")]})
    check("repair says the module does not exist",
          "DOES NOT EXIST" in rt and "backend.app.catalog" in rt, rt)


def test_frontend_deps_and_css_gate():
    """Run 1614's TWO frontend `next build` bugs, now gated deterministically (no Node):
    (1) `import from 'lodash.debounce'` not in package.json -> Module not found;
    (2) raw CSS appended after the component (`.container { … }`) -> invalid TSX."""
    import os
    from app.developers import orchestrator as orch
    from app.devops import manifest

    # --- npm dependency completeness ---
    pkg = '{"dependencies":{"next":"14","react":"18"}}'
    files = [
        {"filepath": "frontend/package.json", "content": pkg},
        {"filepath": "frontend/app/payment/page.tsx",
         "content": "import debounce from 'lodash.debounce'\n"
                    "import Link from 'next/link'\nimport {useState} from 'react'\n"
                    "import {api} from '../lib/api'\n"},  # relative -> not a dep
    ]
    miss = agents.frontend_missing_deps(files)
    check("a bare import missing from package.json is flagged (lodash.debounce)",
          miss == ["lodash.debounce"], str(miss))
    check("declared deps (next/react) and relative imports are NOT flagged",
          "next" not in miss and "react" not in miss and not any("/" in m and m.startswith(".") for m in miss))
    # subpath + scoped resolution
    check("a subpath import resolves to its package (lodash/debounce -> lodash)",
          agents._pkg_of_specifier("lodash/debounce") == "lodash"
          and agents._pkg_of_specifier("@scope/pkg/sub") == "@scope/pkg"
          and agents._pkg_of_specifier("@/lib/x") is None
          and agents._pkg_of_specifier("./x") is None)
    # deterministic manifest fix adds the missing dep at "latest"
    fixed = manifest._add_npm_deps(pkg, miss)
    check("the manifest adds the missing dep to package.json (deterministic fix)",
          json.loads(fixed).get("dependencies", {}).get("lodash.debounce") == "latest")
    check("nothing missing -> package.json unchanged",
          manifest._add_npm_deps(pkg, []) == pkg)

    # --- CSS-in-TSX ---
    fx = os.path.join(os.path.dirname(__file__), "fixtures", "css_in_page_tsx_1614.tsx")
    if os.path.isfile(fx):
        check("run 1614's page.tsx (CSS appended after the component) is flagged",
              agents.frontend_css_leak("frontend/app/page.tsx", open(fx, encoding="utf-8").read())
              is not None)
    check("a normal component + method chain is NOT flagged",
          agents.frontend_css_leak("p.tsx",
              "export default function P(){return (<div className='c'>x</div>);}\n"
              "const y = api\n  .get('/x')\n  .then(r=>r);\n") is None)
    check("CSS inside a styled-component template literal is NOT flagged",
          agents.frontend_css_leak("s.tsx", "const S = styled.div`\n.inner{color:red;}\n`;\n") is None)
    check("a top-level JS object/const is NOT flagged",
          agents.frontend_css_leak("o.tsx", "const styles = { color: 'red' };\nexport default styles;\n") is None)
    check("a non-JS file is ignored", agents.frontend_css_leak("a.css", ".x{color:red}") is None)

    # --- build gate wiring: a CSS-leak page is rejected ---
    built = [
        {"ticket_id": "FE-1", "filepath": "frontend/app/page.tsx",
         "content": "export default function P(){return <div/>;}\n.container { color: red; }\n",
         "status": "generated"},
        {"ticket_id": "FE-2", "filepath": "frontend/app/ok/page.tsx",
         "content": "export default function P(){return <div/>;}\n", "status": "generated"},
    ]
    stubbed = orch._collect_stubs(built, {}, 1)
    check("the build gate rejects ONLY the CSS-leak page",
          [s["ticket_id"] for s in stubbed] == ["FE-1"], str([s["ticket_id"] for s in stubbed]))


def test_frontend_missing_login_gate():
    """Run 1614: the app deployed live, the backend correctly 401'd every protected
    endpoint, but the generated frontend implemented NO login flow, so every gated
    feature was an unreachable 401. The whole-app gate flags a gated backend whose
    frontend has no login evidence; a frontend with a real Auth0 flow is NOT flagged,
    and Stripe's OAuth `/authorize` does not count as login."""
    from app.developers import orchestrator as orch
    gated = {"filepath": "backend/app/routes/menu.py",
             "content": "from backend.app.auth import get_current_admin_user\n"
                        "@router.get('/admin/menu', dependencies=[Depends(get_current_admin_user)])\n"
                        "async def x():\n    return []\n"}
    fe_nologin = {"filepath": "frontend/app/admin/menu/page.tsx",
                  "content": "export default function P(){ return <div>manage</div>; }\n"}
    fe_stripe = {"filepath": "frontend/app/order/page.tsx",
                 "content": "const u='https://connect.stripe.com/oauth/authorize';\n"}
    check("a gated backend + a frontend with NO login flow is flagged",
          agents.frontend_missing_login([gated, fe_nologin, fe_stripe]) is not None)
    check("Stripe's /authorize URL does NOT count as a login flow",
          agents.frontend_missing_login([gated, fe_stripe]) is not None)
    # Fix #34 — a WORKING login needs BOTH halves. Each half ALONE is now flagged as
    # partially-wired: a provider with no token attach (user signs in but every fetch is a
    # 401), or a token attach with no provider (SDK hooks throw, login is dead).
    fe_provider = {"filepath": "frontend/app/providers.tsx",
                   "content": "import { Auth0Provider, useAuth0 } from '@auth0/auth0-react';\n"
                              "export function Providers(){ loginWithRedirect(); }\n"}
    check("a provider wrap with NO token attach is flagged (partially wired)",
          agents.frontend_missing_login([gated, fe_nologin, fe_provider]) is not None)
    fe_bearer = {"filepath": "frontend/app/lib/api.ts",
                 "content": "fetch(u, { headers: { Authorization: `Bearer ${token}` } });\n"}
    check("a Bearer token attach with NO Auth0Provider is flagged (partially wired)",
          agents.frontend_missing_login([gated, fe_nologin, fe_bearer]) is not None)
    check("a frontend WITH BOTH a provider wrap AND a token attach is NOT flagged",
          agents.frontend_missing_login([gated, fe_nologin, fe_provider, fe_bearer]) is None)
    fe_full = {"filepath": "frontend/app/lib/api.ts",
               "content": "import { Auth0Provider } from '@auth0/auth0-react';\n"
                          "const t = await getAccessTokenSilently();\n"
                          "fetch(u, { headers: { Authorization: `Bearer ${t}` } });\n"}
    check("a single file wrapping the app AND acquiring+attaching a token is NOT flagged",
          agents.frontend_missing_login([gated, fe_full]) is None)
    check("no gated backend -> not applicable (not flagged)",
          agents.frontend_missing_login([fe_nologin]) is None)
    check("gated backend but NO web frontend -> not applicable",
          agents.frontend_missing_login([gated]) is None)

    # Build-gate wiring: the whole-app gap flags the providers.tsx ticket for repair.
    built = [
        {**gated, "ticket_id": "MENU-1", "status": "generated"},
        {"ticket_id": "FND-7", "filepath": "frontend/app/providers.tsx", "status": "generated",
         "content": "export function Providers(){ return null; }\n"},   # no real login
        {"ticket_id": "FE-1", "filepath": "frontend/app/admin/menu/page.tsx",
         "status": "generated", "content": "export default ()=><div/>;\n"},
    ]
    stubbed = orch._collect_stubs(built, {}, 1)
    check("the login gap is attributed to the providers.tsx (FND-7) ticket",
          "FND-7" in [s["ticket_id"] for s in stubbed], str([s["ticket_id"] for s in stubbed]))


def test_duplicate_endpoint_gate():
    """Run 1614: the order feature was over-split into order.py AND orders.py, both
    defining `POST /orders` -> FastAPI registers it twice and one handler silently
    shadows the other. The gate flags the same (METHOD, PATH) defined in two route
    files, attributes it to the THINNER file (regenerate without the duplicate), and
    never flags a path that has a single owner."""
    from app.developers import orchestrator as orch
    order = {"ticket_id": "BE-1", "status": "generated", "filepath": "backend/app/routes/order.py",
             "content": "router = APIRouter()\n@router.post('/orders')\nasync def a(): pass\n"}
    orders = {"ticket_id": "BE-2", "status": "generated", "filepath": "backend/app/routes/orders.py",
              "content": "router = APIRouter()\n@router.post('/orders')\nasync def b(): pass\n"
                         "@router.get('/orders/{order_id}')\nasync def c(): pass\n"}
    menu = {"ticket_id": "BE-3", "status": "generated", "filepath": "backend/app/routes/menu.py",
            "content": "router = APIRouter()\n@router.get('/menu')\nasync def m(): pass\n"}

    dups = agents.duplicate_endpoints([order, orders, menu])
    check("the same (method, path) in two files is a duplicate finding",
          len(dups) == 1 and dups[0]["method"] == "POST" and dups[0]["path"] == "/orders"
          and dups[0]["files"] == ["backend/app/routes/order.py", "backend/app/routes/orders.py"], str(dups))
    check("a path with a single owner (GET /menu, GET /orders/{}) is NOT flagged",
          all(d["path"] == "/orders" for d in dups))
    # path-param normalisation: /orders/{order_id} == /orders/{id}
    check("route params normalise so {order_id} and {id} are the same shape",
          agents._norm_route("/orders/{order_id}") == agents._norm_route("/orders/{id}"))
    # APIRouter(prefix=...) is included in the full path.
    pref = {"filepath": "backend/app/routes/p.py",
            "content": "router = APIRouter(prefix='/orders')\n@router.post('')\nasync def x(): pass\n"}
    check("APIRouter prefix is part of the endpoint path",
          ("post", "/orders") in agents._endpoints_of(pref["content"]))

    # Gate wiring: the THINNER file (order.py, 1 route) is flagged; the fuller kept.
    built = [dict(order), dict(orders), dict(menu)]
    stubbed = orch._collect_stubs(built, {}, 1)
    flagged = [s["ticket_id"] for s in stubbed if s.get("duplicate_endpoint_repairs")]
    check("the thinner route file (order.py) is flagged, not the fuller orders.py",
          flagged == ["BE-1"], str(flagged))
    victim = next(s for s in built if s["ticket_id"] == "BE-1")
    rt = agents.repair_instructions(victim)
    check("repair is a DUPLICATE_ENDPOINT naming the endpoint + the file to keep it in",
          "DUPLICATE_ENDPOINT" in rt and "POST /orders" in rt and "orders.py" in rt, rt)

    check("a clean app (every endpoint one owner) yields no duplicates",
          agents.duplicate_endpoints([order, menu]) == [])

    # Regression (measurement run 1843, REAL captured files): the SECURITY helper (SEC-1,
    # backend/app/security.py — NOT a route module) carried an ILLUSTRATIVE
    # `@app.post("/orders")` example. The detector scanned it, invented a phantom
    # `POST /orders` duplicate, and told the REAL order.py to drop its route -> BE-1 stubbed
    # -> build error. Only route MODULES may own routes. Loaded from the exact 1843 artifacts.
    import os as _os
    _fxd = _os.path.join(_os.path.dirname(__file__), "fixtures")
    sec_helper = {"ticket_id": "SEC-1", "status": "generated", "filepath": "backend/app/security.py",
                  "content": open(_os.path.join(_fxd, "security_illustrative_endpoint_1843.py"),
                                  encoding="utf-8").read()}
    real_order = {"ticket_id": "BE-1", "status": "generated", "filepath": "backend/app/routes/order.py",
                  "content": open(_os.path.join(_fxd, "order_route_1843.py"),
                                  encoding="utf-8").read()}
    check("1843's REAL security.py DOES carry an illustrative @app.post('/orders')",
          ("post", "/orders") in agents._endpoints_of(sec_helper["content"]))
    check("but as a non-route module it is NOT flagged a duplicate of the real order.py",
          agents.duplicate_endpoints([real_order, sec_helper, menu]) == [])
    check("a non-route .py file contributes no endpoints to the ownership map",
          "backend/app/security.py" not in
          [fp for d in agents.duplicate_endpoints([real_order, sec_helper]) for fp in d["files"]])


def test_hallucinated_package_gate():
    """Run 1869: security.py did `from starlette_limiter import Limiter` — no such PyPI
    package — which failed the whole pip batch and boot-failed the app. The OFFLINE build
    gate (fix #40) catches a KNOWN-hallucinated package right after codegen, BEFORE
    smoke_boot's ground-truth pip check (fix #39). Blocklist-based: a name only matches if
    it is literally on the curated list, so real packages are never flagged."""
    from app.developers import orchestrator as orch
    bad = {"ticket_id": "SEC-1", "status": "generated", "filepath": "backend/app/security.py",
           "content": "from fastapi import Depends\nfrom starlette_limiter import Limiter\n"
                      "def x(): pass\n"}
    finds = agents.hallucinated_package_imports(bad["content"], bad["filepath"])
    check("the hallucinated `starlette_limiter` import is flagged at the build gate",
          len(finds) == 1 and finds[0]["root"] == "starlette_limiter"
          and finds[0]["line"] == 2, str(finds))
    check("the underscore/hyphen spelling both canonicalise onto the blocklist",
          agents._canon_pkg("starlette_limiter") == "starlette-limiter"
          and "starlette-limiter" in agents._HALLUCINATED_PACKAGES)
    check("a REAL package (fastapi/slowapi) is NOT flagged",
          agents.hallucinated_package_imports(
              "from fastapi import Depends\nfrom slowapi import Limiter\n", "backend/app/x.py") == [])
    check("a frontend .tsx is ignored (python-only gate)",
          agents.hallucinated_package_imports(
              "import { X } from 'starlette_limiter'\n", "frontend/app/page.tsx") == [])
    # The repair text tells the agent to drop it and use a real limiter.
    rt = agents.repair_instructions({"missing_package_repairs": finds})
    check("repair is a MISSING_PACKAGE naming the package + slowapi + 'does NOT exist'",
          "MISSING_PACKAGE" in rt and "starlette_limiter" in rt and "slowapi" in rt
          and "does NOT exist" in rt, rt)
    # Build-gate wiring: _collect_stubs rejects the file + attaches the repair.
    built = [dict(bad), {"ticket_id": "BE-1", "status": "generated",
                         "filepath": "backend/app/routes/menu.py",
                         "content": "from fastapi import APIRouter\nrouter = APIRouter()\n"}]
    stubbed = orch._collect_stubs(built, {}, 1)
    flagged = [s["ticket_id"] for s in stubbed if s.get("missing_package_repairs")]
    check("the build gate flags the offending SEC-1 file (not the clean one)",
          flagged == ["SEC-1"], str(flagged))


def test_hallucinated_submodule_gate():
    """Fix #50 (run 1950): the Opus security auto-fix added rate limiting via
    `from starlette.middleware.rate_limit import RateLimitMiddleware` — starlette ships no
    rate-limit middleware, so the app crashed on import. The root package (`starlette`) IS
    real, so the fix-#40 package check can't see it; the REWRITE gate did not re-run the
    import probe, so the crash-on-startup import shipped into the certificate and only QA's
    assembly caught it. The probe now also flags a KNOWN-non-existent dotted submodule, and
    rewrite_integrity_gate re-runs it on backend .py."""
    from app.developers import orchestrator as orch
    rel = "backend/app/main.py"
    bad = ("import os\nfrom starlette.middleware.rate_limit import RateLimitMiddleware\n"
           "app = None\n")
    finds = agents.hallucinated_package_imports(bad, rel)
    check("the invented starlette submodule is flagged (kind=module, real root)",
          len(finds) == 1 and finds[0]["module"] == "starlette.middleware.rate_limit"
          and finds[0]["root"] == "starlette" and finds[0]["kind"] == "module"
          and finds[0]["line"] == 2, str(finds))
    check("the plain `import starlette.middleware.rate_limit` form is flagged too",
          agents.hallucinated_package_imports(
              "import starlette.middleware.rate_limit\n", rel)[:1] != []
          and agents.hallucinated_package_imports(
              "import starlette.middleware.rate_limit\n", rel)[0]["kind"] == "module")
    check("a REAL starlette submodule (cors) is NOT flagged",
          agents.hallucinated_package_imports(
              "from starlette.middleware.cors import CORSMiddleware\n", rel) == [])
    # THE Fix #50 CORE: the REWRITE gate (Opus/QA re-validation) now catches it.
    g = agents.rewrite_integrity_gate(bad, rel, [{"filepath": rel, "content": bad}])
    check("rewrite_integrity_gate catches the reintroduced bad submodule",
          bool(g.get("missing_package_repairs")), str(g))
    rt = agents.repair_instructions(g)
    check("repair says the SUBMODULE does not exist in the installed package + slowapi",
          "MISSING_PACKAGE" in rt and "submodule" in rt and "does NOT exist in the installed"
          in rt and "slowapi" in rt, rt)
    # Build-gate wiring: _collect_stubs rejects the file + attaches the repair.
    built = [{"ticket_id": "FND-1", "status": "generated", "filepath": rel, "content": bad},
             {"ticket_id": "BE-1", "status": "generated", "filepath": "backend/app/routes/menu.py",
              "content": "from fastapi import APIRouter\nrouter = APIRouter()\n"}]
    stubbed = orch._collect_stubs(built, {}, 1)
    flagged = [s["ticket_id"] for s in stubbed if s.get("missing_package_repairs")]
    check("the build gate flags the offending FND-1 file (not the clean one)",
          flagged == ["FND-1"], str(flagged))


def test_rewrite_integrity_gate():
    """Run 1914: the build gate certified clean code, then a POST-build stage rewrote
    files and REINTRODUCED defects the gate prevents — Opus's security 'fix' wrapped get_db
    in the #24 HTTPException-swallow (every endpoint a masked 500), and QA renamed the
    contract column `source`->`source_name`. Neither path re-validated. `rewrite_integrity_gate`
    is the shared re-validation both stages now run (fix #42)."""
    schema = [{"table": "menu_items", "columns": [
        {"name": "id", "type": "integer"}, {"name": "source", "type": "string"}]}]
    clean_db = ("async def get_db():\n    async with async_session() as s:\n        yield s\n")
    swallow_db = ("async def get_db():\n    try:\n        async with async_session() as s:\n"
                  "            yield s\n    except Exception:\n"
                  "        raise HTTPException(status_code=500, detail='Internal server error')\n")
    files = [{"id": 1, "filepath": "backend/app/database.py", "content": clean_db}]
    check("a clean get_db passes the rewrite gate",
          agents.rewrite_integrity_gate(clean_db, "backend/app/database.py", files, schema, file_id=1) == {})
    g = agents.rewrite_integrity_gate(swallow_db, "backend/app/database.py", files, schema, file_id=1)
    check("the reintroduced #24 get_db swallow is caught by the rewrite gate",
          bool(g.get("http_swallow_repairs")), str(g))
    good_model = ("class MenuItem(Base):\n    __tablename__='menu_items'\n"
                  "    id=sa.Column(sa.Integer, primary_key=True)\n    source=sa.Column(sa.String)\n")
    bad_model = good_model.replace("source=", "source_name=")
    mfiles = [{"id": 2, "filepath": "backend/app/models.py", "content": good_model}]
    check("a model keeping the contract column `source` passes",
          agents.rewrite_integrity_gate(good_model, "backend/app/models.py", mfiles, schema, file_id=2) == {})
    gm = agents.rewrite_integrity_gate(bad_model, "backend/app/models.py", mfiles, schema, file_id=2)
    check("a model renaming `source`->`source_name` is caught (schema_repairs)",
          gm.get("schema_repairs") == ["menu_items.source"], str(gm))
    rt = agents.repair_instructions(gm)
    check("repair renders a SCHEMA_MISMATCH naming the column + exact-name rule",
          "SCHEMA_MISMATCH" in rt and "source" in rt and "source_name" in rt, rt)
    # Fix #48 (run 1950): a post-build rewrite of a FRONTEND file must be re-checked for
    # truncation — Opus/QA left admin/menu/page.tsx unbalanced and it failed `next build`.
    check("a COMPLETE frontend file passes the rewrite gate",
          agents.rewrite_integrity_gate(
              "export default function P(){ return <div>{[1].map(x=>(<b key={x}/>))}</div>; }",
              "frontend/app/admin/menu/page.tsx", []) == {})
    fg = agents.rewrite_integrity_gate(
        "export default function P(){ return (<div>", "frontend/app/admin/menu/page.tsx", [])
    check("a TRUNCATED/unbalanced frontend rewrite is FLAGGED (frontend_repairs)",
          bool(fg.get("frontend_repairs")), str(fg))
    check("the frontend repair renders FRONTEND_FILE_BROKEN with a next-build note",
          "FRONTEND_FILE_BROKEN" in agents.repair_instructions(fg)
          and "next build" in agents.repair_instructions(fg))
    check("a non-JS, non-.py file is still a no-op for the rewrite gate",
          agents.rewrite_integrity_gate("body { color: red }", "frontend/app/globals.css", []) == {})


def test_frontend_parse_gate():
    """Fix #52 (run 1950): the Opus reviewer kept re-shipping order/page.tsx rewrites with
    JSX-STRUCTURE errors (an unclosed `<section>`, a stray `<`). Braces stayed balanced so
    frontend_incomplete PASSED, and only the deploy's real `next build` — four stages after
    the certificate — caught them, re-breaking a file that had just been fixed. The rewrite
    gate now runs a REAL parse (esbuild) so the reviewer keeps the certified-clean original.
    Fails OPEN where esbuild is absent (the balance check + QA's real build remain)."""
    import shutil
    rel = "frontend/app/order/page.tsx"
    broken = ("export default function P(){\n  return (\n    <main>\n      <section>\n"
              "        <p>hi</p>\n    </main>\n  );\n}\n")          # <section> never closed
    clean = ("export default function P(){\n  return (\n    <main>\n      <section>\n"
             "        <p>hi</p>\n      </section>\n    </main>\n  );\n}\n")
    check("the brace-balance check alone MISSES the unclosed <section> (why fix #52 exists)",
          agents.frontend_incomplete(rel, broken) is None,
          str(agents.frontend_incomplete(rel, broken)))
    # WIRING (env-independent): force a parse error, assert the gate surfaces it as a repair.
    _orig = agents.frontend_parse_error
    try:
        agents.frontend_parse_error = lambda r, c: "does not parse: mock"
        g = agents.rewrite_integrity_gate(broken, rel, [{"filepath": rel, "content": broken}])
        check("the rewrite gate surfaces a parse error as frontend_repairs/parse_error",
              bool(g.get("frontend_repairs")) and g["frontend_repairs"][0]["kind"] == "parse_error",
              str(g))
        rt = agents.repair_instructions(g)
        check("repair renders FRONTEND_FILE_BROKEN carrying the parse reason",
              "FRONTEND_FILE_BROKEN" in rt and "does not parse" in rt, rt)
    finally:
        agents.frontend_parse_error = _orig
    # REAL parse — only where esbuild is on PATH (the backend image ships it, fix #52).
    if shutil.which("esbuild"):
        check("esbuild REJECTS the unclosed-<section> JSX (real parse)",
              agents.frontend_parse_error(rel, broken) is not None,
              str(agents.frontend_parse_error(rel, broken)))
        check("esbuild ACCEPTS a well-formed component",
              agents.frontend_parse_error(rel, clean) is None,
              str(agents.frontend_parse_error(rel, clean)))
        real = agents.rewrite_integrity_gate(broken, rel, [{"filepath": rel, "content": broken}])
        check("end-to-end: the real gate returns parse_error for the broken rewrite",
              (real.get("frontend_repairs") or [{}])[0].get("kind") == "parse_error", str(real))
    else:
        print("  [skip] esbuild not on PATH — real-parse assertions skipped (fail-open path)")
    check("frontend_parse_error never flags a .py file",
          agents.frontend_parse_error("backend/app/main.py", "import os\n") is None)


def test_reviewer_rejects_unsafe_autofix():
    """Fix #42 / run 1914: the Opus security auto-fix must NOT be able to reintroduce a
    build-gate defect. If the fix adds a #24 get_db swallow the certified original didn't
    have, the reviewer keeps the ORIGINAL rather than shipping a hardening that broke it."""
    from app.reviewer import orchestrator as rev
    clean = ("async def get_db():\n    async with async_session() as s:\n        yield s\n")
    swallow = ("async def get_db():\n    try:\n        async with async_session() as s:\n"
               "            yield s\n    except Exception:\n"
               "        raise HTTPException(500, 'Internal server error')\n")

    class _GF:  # minimal stand-in for a GeneratedFile row
        def __init__(self, id, filepath, content):
            self.id, self.filepath, self.filename, self.content = id, filepath, None, content
    files = [{"id": 1, "filepath": "backend/app/database.py", "content": clean}]
    gf = _GF(1, "backend/app/database.py", clean)
    kept = rev._accept_or_reject_fix(gf, swallow, files, None)
    check("an Opus fix that reintroduces the get_db swallow is REJECTED (original kept)",
          kept == clean, "fix was wrongly accepted")
    # A genuinely clean fix is still accepted.
    clean2 = clean + "\n# reviewed\n"
    gf2 = _GF(1, "backend/app/database.py", clean)
    check("a clean security fix is still accepted",
          rev._accept_or_reject_fix(gf2, clean2, files, None) == clean2)


def test_reviewer_frontend_accept_seam():
    """Fix #53 + #55b (deterministic seam): the reviewer does not stochastically rewrite
    frontend files, so `_accept_or_reject_fix` normally sees new_content=None for a frontend
    path. When it DOES see a frontend rewrite it is a CONFIRMED-critical security repair
    (fix #55b) — accept it, but ONLY after re-checking it through the SAME frontend build gate
    (defense-in-depth): a candidate that FAILS the gate is discarded (keeping the
    certified-clean original — the pre-#53 reviewer stochastically re-broke `next build`), and
    a gate-passing repair is applied so a real frontend vuln finally has a remediation path."""
    from app.reviewer import reviewer as rv
    from app.reviewer import orchestrator as rev
    check("_is_frontend_path: .tsx under frontend/ is frontend",
          rv._is_frontend_path("frontend/app/order/page.tsx") is True)
    check("_is_frontend_path: backend .py is NOT frontend",
          rv._is_frontend_path("backend/app/main.py") is False)
    check("_is_frontend: agent_type=backend overrides a bare .ts",
          rv._is_frontend({"filepath": "seed.ts", "agent_type": "backend"}) is False)
    check("_is_frontend: a .tsx under frontend/ is frontend",
          rv._is_frontend({"filepath": "frontend/app/page.tsx", "agent_type": "frontend"}) is True)

    class _GF:
        def __init__(self, id, filepath, content):
            self.id, self.filepath, self.filename, self.content = id, filepath, None, content
    path = "frontend/app/order/page.tsx"
    original = "export default function Page(){ return <p>hi</p>; }\n"
    files = [{"id": 9, "filepath": path, "content": original}]

    # A gate-FAILING rewrite (unbalanced braces -> frontend_incomplete) is discarded.
    broken = "export default function Page(){ return <p>hi</p>; }\n{{{ \n"
    gf1 = _GF(9, path, original)
    check("a frontend rewrite that FAILS the frontend gate is DISCARDED (original kept)",
          rev._accept_or_reject_fix(gf1, broken, files, None) == original,
          "a broken frontend rewrite was wrongly applied")
    # A gate-PASSING #55b security repair is accepted.
    clean_repair = "export default function Page(){ return <p>safe</p>; }\n"
    gf2 = _GF(9, path, original)
    check("a gate-passing frontend security repair (#55b) IS accepted",
          rev._accept_or_reject_fix(gf2, clean_repair, files, None) == clean_repair,
          "a clean, validated frontend repair was wrongly discarded")
    # A None candidate (the read-only / fail-closed cases) keeps the original.
    gf3 = _GF(9, path, original)
    check("a None candidate keeps the original (read-only / fail-closed path)",
          rev._accept_or_reject_fix(gf3, None, files, None) == original)


async def test_reviewer_frontend_confirmed_repair():
    """Fix #55b: a CONFIRMED frontend security critical (run 2080's JWT-in-URL) is handed ONE
    bounded, re-validated repair through `review_file`. When the rewrite passes the frontend
    build gate AND a clean security re-review it is APPLIED (new_content set) — the deploy is
    no longer stuck with no remediation. When no safe rewrite is found within the bound, the
    cert fails CLOSED (new_content None, security_passed False). Mocks the LLM — no network."""
    from app.reviewer import reviewer as rv
    from app import codegen

    ORIG = "export default function P(){ return <a href={`/x?token=${t}`}>go</a>; }\n"
    SAFE = "export default function P(){ return <a onClick={go}>go</a>; }\n"
    STILL = "export default function P(){ return <a href={`/y?token=${t}`}>go</a>; }\n"
    CRIT = [{"severity": "critical", "type": "Token in URL", "detail": "jwt in query param"}]

    def make_generate(fix_result):
        async def fake_generate(model, system, prompt, temperature=0.0, bypass_cheap=False):
            if system.startswith("You are fixing"):            # _FIX_SYS or the #55b security fix
                return json.dumps({"content": fix_result}), None
            if system.startswith("You are a senior"):          # general pass -> clean
                return json.dumps({"issues": []}), None
            # security pass: vulnerable iff the reviewed content puts a token in the URL.
            vuln = "?token=" in prompt
            return json.dumps({"issues": CRIT if vuln else []}), None
        return fake_generate

    async def review(fix_result):
        fe = {"id": 2, "filepath": "frontend/app/integrate/page.tsx", "content": ORIG,
              "agent_type": "frontend", "ticket_id": "FE-3"}
        orig_gen = codegen.generate
        codegen.generate = make_generate(fix_result)
        try:
            return await rv.review_file(fe, "gpt-4o-mini",
                                        files=[{**fe}], schema=None)
        finally:
            codegen.generate = orig_gen

    # Repairable: the fix removes the token-in-URL -> re-review clean -> APPLIED.
    r = await review(SAFE)
    check("a confirmed frontend critical with a safe repair is APPLIED (new_content set, passed)",
          r["new_content"] == SAFE and r["security_passed"] is True and r["issues_fixed"] == 1,
          str(r))
    # Not repairable: every rewrite still leaks the token -> FAIL CLOSED, original kept.
    r = await review(STILL)
    check("a confirmed frontend critical with no safe repair FAILS CLOSED (None, not passed)",
          r["new_content"] is None and r["security_passed"] is False, str(r))


async def test_review_file_frontend_readonly():
    """Fix #53: review_file REVIEWS + REPORTS a frontend file but returns new_content=None
    (never mutates it), while a BACKEND file with the same issues IS rewritten. Proven by
    stubbing the LLM so every review reports a medium issue and every fix returns new text."""
    from app.reviewer import reviewer as rv
    from app import codegen

    MUT = "def fixed():\n    return 'this is the rewritten file body'\n"

    async def fake_generate(model, system, prompt, temperature=0.0, bypass_cheap=False):
        if system.startswith("You are fixing specific issues"):
            return json.dumps({"content": MUT}), None
        # both review passes report one medium (non-critical) issue
        return json.dumps({"issues": [{"type": "x", "severity": "medium", "detail": "d"}]}), None

    orig_gen = codegen.generate
    codegen.generate = fake_generate
    try:
        be = {"id": 1, "filepath": "backend/app/routes/menu.py",
              "content": "def orig():\n    return 1\n", "agent_type": "backend", "ticket_id": "BE-1"}
        fe = {"id": 2, "filepath": "frontend/app/order/page.tsx",
              "content": "export default function P(){return <p>hi</p>}\n",
              "agent_type": "frontend", "ticket_id": "FE-1"}
        rbe = await rv.review_file(be, "gpt-4o-mini")
        rfe = await rv.review_file(fe, "gpt-4o-mini")
    finally:
        codegen.generate = orig_gen

    check("backend file IS rewritten by the reviewer (new_content set, issues fixed)",
          rbe["new_content"] == MUT and rbe["issues_fixed"] >= 1, str(rbe))
    check("frontend file is NEVER rewritten (new_content None, issues_fixed 0)",
          rfe["new_content"] is None and rfe["issues_fixed"] == 0, str(rfe))
    check("frontend file is still REVIEWED + REPORTED (both passes ran, issues_found 2)",
          rfe["issues_found"] == 2, str(rfe))


def test_timestamp_not_null_gate():
    """Run 1937: the generated model wrote `created_at = Column(DateTime, nullable=False)`
    with NO default, and the create handler never set it -> every INSERT sends NULL ->
    NotNullViolation -> a masked 500 on EVERY create (QA missed it). The gate flags a
    NOT-NULL datetime column with no default/server_default. Zero-FP: nullable/defaulted/PK
    columns and non-datetime NOT-NULL columns (set from the request) are never flagged."""
    HEAD = "import sqlalchemy as sa\nfrom sqlalchemy import Column, Integer, String, DateTime\n"
    def model(cols):
        return HEAD + "class MenuItem(Base):\n    __tablename__ = 'menu_items'\n" + \
            "    id = Column(Integer, primary_key=True)\n" + \
            "".join(f"    {c}\n" for c in cols)
    P = "backend/app/models.py"
    # THE 1937 BUG — flagged.
    bug = model(["created_at = Column(DateTime, nullable=False)"])
    f = agents.timestamp_not_null_no_default(bug, P)
    check("a NOT-NULL datetime column with no default is flagged (run 1937)",
          len(f) == 1 and f[0]["column"] == "created_at" and f[0]["table"] == "menu_items", str(f))
    # Zero-FP cases — NOT flagged.
    check("server_default present -> NOT flagged",
          agents.timestamp_not_null_no_default(
              model(["created_at = Column(DateTime, nullable=False, server_default=sa.func.now())"]), P) == [])
    check("a Python default present -> NOT flagged",
          agents.timestamp_not_null_no_default(
              model(["created_at = Column(DateTime, nullable=False, default=sa.func.now())"]), P) == [])
    check("a NULLABLE timestamp -> NOT flagged",
          agents.timestamp_not_null_no_default(
              model(["created_at = Column(DateTime, nullable=True)"]), P) == [])
    check("a NOT-NULL STRING column (set from the request) -> NOT flagged",
          agents.timestamp_not_null_no_default(
              model(["name = Column(String, nullable=False)"]), P) == [])
    check("the primary key is never flagged",
          agents.timestamp_not_null_no_default(
              HEAD + "class T(Base):\n    __tablename__='t'\n    id = Column(DateTime, primary_key=True, nullable=False)\n", P) == [])
    # DateTime(timezone=True) and a name-first-positional both still detect the type.
    check("Column(DateTime(timezone=True), nullable=False) is flagged",
          len(agents.timestamp_not_null_no_default(
              model(["updated_at = Column(DateTime(timezone=True), nullable=False)"]), P)) == 1)
    check("a non-model file / non-.py is a no-op",
          agents.timestamp_not_null_no_default(bug, "frontend/app/page.tsx") == []
          and agents.timestamp_not_null_no_default("x=1", P) == [])
    # Repair text names the column + the server_default fix.
    rt = agents.repair_instructions({"timestamp_default_repairs": f})
    check("repair is TIMESTAMP_NO_DEFAULT naming the column + server_default=sa.func.now()",
          "TIMESTAMP_NO_DEFAULT" in rt and "created_at" in rt and "server_default" in rt
          and "func.now()" in rt, rt)
    # Build-gate wiring: _collect_stubs flags the model file.
    from app.developers import orchestrator as orch
    built = [{"ticket_id": "FND-1", "filepath": P, "content": bug, "status": "generated"}]
    stubbed = orch._collect_stubs(built, {}, 1)
    check("the build gate flags the model with the NOT-NULL-no-default timestamp",
          [s["ticket_id"] for s in stubbed] == ["FND-1"]
          and built[0].get("timestamp_default_repairs"), str(stubbed))


def test_dangling_foreign_key_gate():
    """Run 1934: `owner_id = Column(Integer, ForeignKey('users.id'))` but NO `users` table
    was ever generated. The class imports fine so the app BOOTS, but `create_all` raises
    NoReferencedTableError, the DDL transaction rolls back, and the DB is left with ZERO
    tables -> every query 500s (it looked like a per-endpoint GET /menu bug). The gate flags
    a ForeignKey whose table no model defines. Zero-FP: a FK to a defined table is clean."""
    HEAD = "from sqlalchemy import Column, Integer, String, ForeignKey\n"
    order_bad = (HEAD + "class Order(Base):\n    __tablename__ = 'orders'\n"
                 "    id = Column(Integer, primary_key=True)\n"
                 "    owner_id = Column(Integer, ForeignKey('users.id'), nullable=False)\n")
    tables_no_users = {"orders", "menu_items"}
    f = agents.dangling_foreign_keys(order_bad, tables_no_users)
    check("a ForeignKey to an undefined table is flagged (run 1934: users)",
          len(f) == 1 and f[0]["table"] == "users" and f[0]["column"] == "owner_id"
          and f[0]["referenced"] == "users.id", str(f))
    # Zero-FP: the referenced table IS defined somewhere in the build.
    check("a ForeignKey to a DEFINED table is NOT flagged",
          agents.dangling_foreign_keys(order_bad, {"orders", "users"}) == [])
    # Object-form ForeignKey(User.id) can never dangle -> not flagged.
    obj_form = (HEAD + "class Order(Base):\n    __tablename__ = 'orders'\n"
                "    id = Column(Integer, primary_key=True)\n"
                "    owner_id = Column(Integer, ForeignKey(User.id))\n")
    check("object-form ForeignKey(Model.col) is NOT flagged (cannot dangle)",
          agents.dangling_foreign_keys(obj_form, set()) == [])
    check("a non-model file (no __tablename__) is a no-op",
          agents.dangling_foreign_keys("x = ForeignKey('users.id')", set()) == [])
    # collect_tablenames unions tablenames across the whole build (models may span files).
    built_files = [
        {"filepath": "backend/app/models.py", "content": order_bad},
        {"filepath": "backend/app/more_models.py",
         "content": "class MenuItem(Base):\n    __tablename__ = 'menu_items'\n    id = Column(Integer)\n"},
    ]
    check("collect_tablenames gathers every __tablename__ across files",
          agents.collect_tablenames(built_files) == {"orders", "menu_items"}, "")
    # Build-gate wiring: _collect_stubs rejects the model file + attaches the repair.
    built = [
        {"ticket_id": "FND-1", "filepath": "backend/app/models.py",
         "content": order_bad, "status": "generated"},
        {"ticket_id": "BE-1", "filepath": "backend/app/routes/menu.py",
         "content": "def ok():\n    return 1\n", "status": "generated"},
    ]
    stubbed = orch._collect_stubs(built, {}, 1)
    check("the model with the dangling FK is rejected by the build gate",
          [s["ticket_id"] for s in stubbed] == ["FND-1"], str([s["ticket_id"] for s in stubbed]))
    check("the gate problem names the dangling reference",
          any("users.id" in p for p in built[0].get("gate_problems", [])), str(built[0].get("gate_problems")))
    check("the structural repair is attached for a precise retry",
          built[0].get("foreign_key_repairs") == f, str(built[0].get("foreign_key_repairs")))
    # Repair text explains the fix (drop the FK / identity is in the JWT).
    rt = agents.repair_instructions({"foreign_key_repairs": f})
    check("repair is FOREIGN_KEY_DANGLING naming the column + table + the drop-FK fix",
          "FOREIGN_KEY_DANGLING" in rt and "owner_id" in rt and "users" in rt
          and "ForeignKey" in rt, rt)
    # rewrite_integrity_gate re-catches a dangling FK reintroduced by a post-build rewrite.
    rg = agents.rewrite_integrity_gate(order_bad, "backend/app/models.py", built_files)
    check("rewrite_integrity_gate re-flags a reintroduced dangling FK",
          rg.get("foreign_key_repairs") and rg["foreign_key_repairs"][0]["table"] == "users", str(rg))
    # Backend prompt forbids it.
    sysp = agents._system("backend")
    check("backend prompt has a foreign-key rule forbidding a dangling ForeignKey",
          "foreign-key rule" in sysp.lower() and "users" in sysp and "create_all" in sysp, "")


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
    # Fix #41 (run 1887): an apostrophe in JSX TEXT ("Stripe's", "we're", "don't") is
    # literal text, NOT a string delimiter — treating it as one desynced the brace counter
    # and FALSE-flagged a COMPLETE settings page, failing the whole build.
    check("an apostrophe/contraction in JSX text does NOT false-flag a complete file",
          agents.frontend_incomplete(
              "a.tsx", "export default ()=> (<p>Stripe's checkout — we're ready {x(1)}</p>);") is None)
    fx1887 = os.path.join(os.path.dirname(__file__), "fixtures", "jsx_apostrophe_settings_1887.tsx")
    if os.path.isfile(fx1887):
        settings_1887 = open(fx1887, encoding="utf-8").read()
        check("1887's REAL settings page (with `Stripe's`) is NOT flagged (was a false positive)",
              agents.frontend_incomplete("frontend/app/settings/page.tsx", settings_1887) is None,
              str(agents.frontend_incomplete("x.tsx", settings_1887)))
    check("a string literal (preceded by =) is still stripped — real unterminated one flagged",
          agents.frontend_incomplete("a.tsx", "const s = 'abc") is not None)

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


def test_import_symbol_resolution_gate():
    """FIX #16 regression (project 1038): a fresh generation wrote
    `from backend.app.auth import require_admin`, but auth exports only
    get_current_user/get_current_admin_user -> ImportError at boot. The
    symbol-resolution gate must catch a `from <in-project module> import <symbol>`
    whose symbol the module does not export — auth via AUTH_EXPORTS, other modules
    via an AST scan of their own defs — and flag ONLY that, retried then failed."""
    import os
    from app.developers import orchestrator as orch

    auth = {"filepath": "backend/app/auth.py",
            "content": ("def get_current_user():\n    return {}\n"
                        "def get_current_admin_user():\n    return {}\n")}
    models = {"filepath": "backend/app/models.py",
              "content": ("class MenuItem(Base):\n    __tablename__ = 'menu_items'\n"
                          "    id = Column(Integer)\n")}
    database = {"filepath": "backend/app/database.py",
                "content": ("Base = object\n"
                            "async def get_db():\n    yield None\n"
                            "def async_session():\n    return None\n")}

    fx = os.path.join(os.path.dirname(__file__), "fixtures",
                      "menu_upload_require_admin_1038.py")
    bad = open(fx, encoding="utf-8").read()
    index = agents.build_symbol_index([auth, models, database,
                                       {"filepath": "backend/app/routes/menu_upload.py",
                                        "content": bad}])

    found = agents.import_symbol_mismatches(bad, "backend/app/routes/menu_upload.py", index)
    syms = [f["symbol"] for f in found]
    check("1038's `require_admin` is flagged as unresolved", syms == ["require_admin"], str(found))
    check("the finding names the module it was imported from",
          found and found[0]["module"] == "backend.app.auth", str(found))
    check("the finding lists the REAL available auth symbols",
          found and set(found[0]["available"]) ==
          {"get_current_user", "get_current_admin_user"}, str(found))
    check("valid sibling imports (get_db, MenuItem) are NOT flagged",
          "get_db" not in syms and "MenuItem" not in syms, str(syms))

    # A corrected import resolves cleanly — no residual false positive.
    good = bad.replace("import require_admin", "import get_current_admin_user") \
              .replace("Depends(require_admin)", "Depends(get_current_admin_user)")
    idx2 = agents.build_symbol_index([auth, models, database,
                                      {"filepath": "backend/app/routes/menu_upload.py",
                                       "content": good}])
    check("the corrected file resolves with zero findings",
          agents.import_symbol_mismatches(good, "backend/app/routes/menu_upload.py", idx2) == [],
          str(agents.import_symbol_mismatches(good, "backend/app/routes/menu_upload.py", idx2)))

    # Other-module scan (not auth): a guessed name from models.py is caught too.
    guesser = {"filepath": "backend/app/routes/order.py",
               "content": "from backend.app.models import MenuItem, Product\n"}
    idx3 = agents.build_symbol_index([models, guesser])
    g = agents.import_symbol_mismatches(guesser["content"], "backend/app/routes/order.py", idx3)
    check("a non-existent symbol from a real in-project module (models.Product) is caught",
          [f["symbol"] for f in g] == ["Product"], str(g))

    # The gate (the real _collect_stubs) rejects it and attaches the structured repair.
    built = [auth, models, database,
             {"ticket_id": "MENU-3", "filepath": "backend/app/routes/menu_upload.py",
              "content": bad, "status": "generated"},
             {"ticket_id": "OK-1", "filepath": "backend/app/routes/menu.py",
              "content": "from backend.app.models import MenuItem\nrouter = 1\n",
              "status": "generated"}]
    for f in (auth, models, database):
        f.setdefault("status", "generated")
    stubbed = orch._collect_stubs(built, {}, 1)
    ids = sorted(s.get("ticket_id") for s in stubbed if s.get("ticket_id"))
    check("gate rejects ONLY the ticket with the bad import", ids == ["MENU-3"], str(ids))
    m3 = next(s for s in built if s.get("ticket_id") == "MENU-3")
    check("the rejected ticket carries STUB_STATUS", m3["status"] == agents.STUB_STATUS)
    check("the rejected ticket carries the structured symbol_repairs",
          m3.get("symbol_repairs") and m3["symbol_repairs"][0]["symbol"] == "require_admin",
          str(m3.get("symbol_repairs")))
    check("the clean menu ticket is left untouched",
          next(s for s in built if s.get("ticket_id") == "OK-1")["status"] == "generated")

    # The structured repair renders a precise, bounded IMPORT_RESOLUTION_FAILURE ticket.
    rt = agents.repair_instructions(m3)
    check("repair text is an IMPORT_RESOLUTION_FAILURE naming the bad + available symbols",
          "IMPORT_RESOLUTION_FAILURE" in rt and "require_admin" in rt
          and "get_current_admin_user" in rt, rt)
    check("repair text scopes the fix to this file only",
          "repair ONLY this file" in rt.lower() or "only this file" in rt.lower(), rt)


def test_import_symbol_zero_false_positives():
    """HARD REQUIREMENT: zero false positives on real, working code. Run the
    symbol-resolution detector across (a) the platform's OWN backend (64 real modules,
    nested packages, package-root/submodule imports, re-exports) and (b) project 888's
    WORKING generated file set. Neither may produce a single finding. As a bonus TRUE
    positive on real generated code, 888's ORPHANED order/stripe files (dead code the
    hand-fix stripped from models.py/main.py) DO have dangling imports and must be caught."""
    import os
    import glob

    # (a) The platform's own backend — every import in it resolves (the app runs).
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    platform = []
    for path in glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True):
        rel = "backend/" + os.path.relpath(path, os.path.join(app_dir, "..")).replace(os.sep, "/")
        platform.append({"filepath": rel, "content": open(path, encoding="utf-8").read()})
    pidx = agents.build_symbol_index(platform)
    plat_findings = []
    for f in platform:
        plat_findings += agents.import_symbol_mismatches(f["content"], f["filepath"], pidx)
    check(f"ZERO false positives across the platform's own {len(platform)} backend modules",
          plat_findings == [], str(plat_findings[:6]))

    # (b) Project 888's real generated files, split into working vs orphaned.
    gdir = os.path.join(os.path.dirname(__file__), "fixtures", "gen888")
    if not os.path.isdir(gdir):
        check("888 fixture corpus present", False, f"missing {gdir}")
        return
    g888 = []
    for path in sorted(glob.glob(os.path.join(gdir, "*.py"))):
        rel = os.path.basename(path).replace("__", "/")
        g888.append({"filepath": rel, "content": open(path, encoding="utf-8").read()})
    gidx = agents.build_symbol_index(g888)

    # The 3 orphaned files the 888 hand-fix stripped from models.py/main.py.
    orphaned = {"backend/app/routes/order.py", "backend/app/routes/order_be_2.py",
                "backend/app/routes/stripe.py"}
    working_findings, orphan_findings = [], []
    for f in g888:
        found = agents.import_symbol_mismatches(f["content"], f["filepath"], gidx)
        (orphan_findings if f["filepath"] in orphaned else working_findings).extend(found)
    check("ZERO false positives across 888's WORKING generated files "
          "(auth/database/main/models/menu/menu_upload/security)",
          working_findings == [], str(working_findings))
    check("bonus: the detector DOES catch 888's orphaned order/stripe dangling imports "
          "(Order/Product/StripeAccount not in the stripped models.py)",
          {f["symbol"] for f in orphan_findings} >= {"Order", "Product", "StripeAccount"},
          str(sorted({f["symbol"] for f in orphan_findings})))


def test_python_syntax_gate():
    """FIX #17 regression (project 1071): a fresh generation of routes/order_be_3.py put a
    non-default parameter after a defaulted one -> hard Python SyntaxError at import, so
    the app never booted (caught only late, at smoke_boot). The build gate must catch an
    unparseable backend .py, attach a STRUCTURED finding, retry with a targeted repair,
    then fail. Zero false positives BY CONSTRUCTION: valid Python parses, invalid does not."""
    import os
    import glob
    from app.developers import orchestrator as orch

    # 1071's EXACT captured file (parameter-ordering SyntaxError).
    fx = os.path.join(os.path.dirname(__file__), "fixtures", "order_be_3_param_order_1071.py")
    bad = open(fx, encoding="utf-8").read()
    syn = agents.python_syntax_error(bad, "backend/app/routes/order_be_3.py")
    check("1071's EXACT param-ordering file is flagged as a syntax error", syn is not None, str(syn))
    check("the finding names the offending line + message",
          syn and syn["line"] == 18 and "default" in (syn.get("message") or ""), str(syn))

    # Other real syntax errors are caught; valid / non-.py are NOT.
    check("unclosed paren is flagged",
          agents.python_syntax_error("def f(:\n    return 1\n", "a.py") is not None)
    check("bad indentation is flagged",
          agents.python_syntax_error("def f():\nreturn 1\n", "a.py") is not None)
    check("a valid backend .py is NOT flagged",
          agents.python_syntax_error("def f(a, b=1):\n    return a + b\n", "a.py") is None)
    check("a non-.py file is ignored (frontend truncation is fix #15's job)",
          agents.python_syntax_error("const x = (", "frontend/app/page.tsx") is None)

    # Zero-false-positive proof: every real platform + 888 Python file parses.
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    plat = [(p, open(p, encoding="utf-8").read())
            for p in glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True)]
    plat_syn = [p for p, c in plat if agents.python_syntax_error(c, "backend/app/x.py")]
    check(f"ZERO false positives across the platform's own {len(plat)} backend modules",
          plat_syn == [], str(plat_syn[:6]))
    gdir = os.path.join(os.path.dirname(__file__), "fixtures", "gen888")
    g_syn = [os.path.basename(p) for p in glob.glob(os.path.join(gdir, "*.py"))
             if agents.python_syntax_error(open(p, encoding="utf-8").read(), "backend/app/x.py")]
    check("ZERO false positives across 888's real generated files", g_syn == [], str(g_syn))

    # Gate integration: _collect_stubs rejects the broken file, attaches structured
    # syntax_error, leaves clean files untouched.
    built = [
        {"ticket_id": "BE-3", "filepath": "backend/app/routes/order_be_3.py",
         "content": bad, "status": "generated"},
        {"ticket_id": "FND-1", "filepath": "backend/app/models.py",
         "content": "class MenuItem(Base):\n    __tablename__ = 'menu_items'\n    id = Column(Integer)\n",
         "status": "generated"},
    ]
    stubbed = orch._collect_stubs(built, {}, 1)
    check("gate rejects ONLY the syntax-broken ticket",
          [s["ticket_id"] for s in stubbed] == ["BE-3"], str([s["ticket_id"] for s in stubbed]))
    be3 = next(s for s in built if s["ticket_id"] == "BE-3")
    check("the rejected ticket carries STUB_STATUS", be3["status"] == agents.STUB_STATUS)
    check("the rejected ticket carries the structured syntax_error",
          be3.get("syntax_error") and be3["syntax_error"]["line"] == 18, str(be3.get("syntax_error")))
    check("the clean model ticket is left untouched", built[1]["status"] == "generated")

    # The structured repair renders a precise, bounded SYNTAX_ERROR ticket.
    rt = agents.repair_instructions(be3)
    check("repair text is a SYNTAX_ERROR naming the file + line + message",
          "SYNTAX_ERROR" in rt and "order_be_3.py" in rt and "line 18" in rt, rt)
    check("repair text scopes the fix to this file only", "only this file" in rt.lower(), rt)
    check("repair text gives the param-ordering guidance",
          "without a default" in rt and "with a default" in rt, rt)


# Shared in-project fixtures for the attribute-resolution tests (SQLAlchemy models with
# both `Column` and `mapped_column`/Mapped styles, a Pydantic schema, a plain class, and
# OPEN classes that must never be flagged).
_ATTR_MODELS = {"id": 1, "filepath": "backend/app/models.py", "content": (
    "from backend.app.database import Base\n"
    "from sqlalchemy import Column, Integer, String\n"
    "from sqlalchemy.orm import Mapped, mapped_column, relationship\n"
    "class MenuItem(Base):\n"
    "    __tablename__ = 'menu_items'\n"
    "    id = Column(Integer, primary_key=True)\n"
    "    name = Column(String)\n"
    "    price = Column(Integer)\n"
    "    status = Column(String)\n"
    "class Order(Base):\n"
    "    __tablename__ = 'orders'\n"
    "    id: Mapped[int] = mapped_column(Integer, primary_key=True)\n"
    "    total_price: Mapped[int] = mapped_column(Integer)\n"
    "    user_id: Mapped[int] = mapped_column(Integer)\n"
    "    items = relationship('OrderItem')\n"
    "    def label(self):\n        return f'order {self.id}'\n")}
_ATTR_SCHEMAS = {"id": 2, "filepath": "backend/app/schemas.py", "content": (
    "from pydantic import BaseModel\n"
    "class OrderIn(BaseModel):\n    quantity: int\n    note: str\n")}
_ATTR_OPEN = {"id": 3, "filepath": "backend/app/open_cls.py", "content": (
    "import logging\n"
    "from abc import ABC\n"
    "class Filt(logging.Filter):\n    own = 1\n"          # base logging.Filter -> open
    "class Svc(ABC):\n    own = 1\n"                       # base ABC (in-project name, unresolvable) -> open
    "class Dyn:\n    real = 1\n    def __getattr__(self, k):\n        return None\n")}  # dynamic -> open
_ATTR_DB = {"id": 4, "filepath": "backend/app/database.py", "content": (
    "from sqlalchemy.orm import DeclarativeBase\n"
    "class Base(DeclarativeBase):\n    pass\n")}


def test_attribute_resolution_gate():
    """FIX #19 (slice 1): `ClassName.attr` must resolve to a real attribute of a KNOWN
    in-project class. Catches the 'No attribute' class — the CONTEXT `MenuItem.total_amount`
    example and typos like `Order.total_amonut` — while NEVER flagging real fields, dunders,
    inherited framework attributes, relationships, or OPEN classes (dynamic / unresolvable
    base / third-party). Class-name access only; instance access is out of slice-1 scope."""
    files = [_ATTR_MODELS, _ATTR_SCHEMAS, _ATTR_OPEN, _ATTR_DB]
    idx = agents.build_symbol_index(files)

    def flags(src):
        f = {"filepath": "backend/app/routes/x.py", "content": src}
        return agents.attribute_access_mismatches(src, f["filepath"],
                                                  agents.build_symbol_index(files + [f]))

    bad = ("from backend.app.models import MenuItem, Order\n"
           "from sqlalchemy import select\n"
           "def a():\n    return select(MenuItem.total_amount)\n"     # CONTEXT example
           "def b():\n    return Order.total_amonut\n")               # typo
    found = flags(bad)
    got = sorted((f["class"], f["attribute"]) for f in found)
    check("flags MenuItem.total_amount (CONTEXT example) + Order.total_amonut (typo)",
          got == [("MenuItem", "total_amount"), ("Order", "total_amonut")], str(got))
    check("the finding lists the class's REAL fields",
          any(f["class"] == "Order" and set(f["available"]) >= {"id", "total_price", "user_id"}
              for f in found), str(found))

    ok = ("from backend.app.models import MenuItem, Order\n"
          "from sqlalchemy import select\n"
          "def a():\n    return select(MenuItem.status, MenuItem.price, Order.total_price)\n"  # real columns
          "def b():\n    return Order.items\n"                    # relationship
          "def c():\n    return Order.label\n"                    # method
          "def d():\n    return Order.__table__\n"                # dunder
          "def e():\n    return MenuItem.metadata\n"              # SQLA base attr
          "def f():\n    return Order.query\n")                   # SQLA base attr
    check("real columns / relationship / method / dunder / SQLA-base attrs are NOT flagged",
          flags(ok) == [], str(flags(ok)))

    pyd = ("from backend.app.schemas import OrderIn\n"
           "def a():\n    return OrderIn.quantity\n"              # real field
           "def b():\n    return OrderIn.model_fields\n"          # Pydantic base attr
           "def c():\n    return OrderIn.notez\n")                # typo -> flagged
    pf = sorted((f["class"], f["attribute"]) for f in flags(pyd))
    check("Pydantic: real field + model_fields NOT flagged; a typo IS flagged",
          pf == [("OrderIn", "notez")], str(pf))

    openacc = ("from backend.app.open_cls import Filt, Svc, Dyn\n"
               "from backend.app.database import Base\n"
               "def a():\n    return Filt.anything\n"             # logging.Filter base -> open
               "def b():\n    return Svc.whatever\n"              # ABC base -> open
               "def c():\n    return Dyn.nope\n"                  # __getattr__ -> open
               "def d():\n    return Base.metadata\n")            # DeclarativeBase base -> open
    check("OPEN classes (third-party/ABC base, dynamic, DeclarativeBase) are NEVER flagged",
          flags(openacc) == [], str(flags(openacc)))

    outofscope = ("from backend.app.models import Order\n"
                  "def a(o):\n    return o.total_amonut\n"        # instance access -> slice-2, skip
                  "def b():\n    o = Order()\n    return o.total_amonut\n"  # local construction -> skip
                  "import backend.app.models as m\n"
                  "def c():\n    return m.Order.total_amonut\n")  # module-qualified -> skip
    check("instance/constructed/module-qualified access is OUT of slice-1 scope (skipped)",
          flags(outofscope) == [], str(flags(outofscope)))

    shadow = ("from backend.app.models import Order\n"
              "def a():\n    Order = object()\n    return Order.total_amonut\n")  # shadowed name
    check("a class name shadowed by a local variable is NOT flagged (ambiguous)",
          flags(shadow) == [], str(flags(shadow)))

    # Gate integration: _collect_stubs rejects a file with a bad attribute access.
    from app.developers import orchestrator as orch
    built = [{**_ATTR_DB, "ticket_id": "FND-2", "status": "generated"},
             {**_ATTR_MODELS, "ticket_id": "FND-1", "status": "generated"},
             {"ticket_id": "BE-1", "filepath": "backend/app/routes/x.py", "status": "generated",
              "content": "from backend.app.models import Order\ndef a():\n    return Order.total_amonut\n"}]
    stubbed = orch._collect_stubs(built, {}, 1)
    check("gate rejects the ticket with the bad attribute access",
          [s["ticket_id"] for s in stubbed] == ["BE-1"], str([s["ticket_id"] for s in stubbed]))
    be1 = next(s for s in built if s["ticket_id"] == "BE-1")
    check("the rejected ticket carries structured attribute_repairs",
          be1.get("attribute_repairs") and be1["attribute_repairs"][0]["attribute"] == "total_amonut",
          str(be1.get("attribute_repairs")))
    check("the model ticket is left untouched",
          next(b for b in built if b["ticket_id"] == "FND-1")["status"] == "generated")
    rt = agents.repair_instructions(be1)
    check("repair text is an ATTRIBUTE_RESOLUTION_FAILURE naming the class + attribute",
          "ATTRIBUTE_RESOLUTION_FAILURE" in rt and "Order" in rt and "total_amonut" in rt, rt)


def test_attribute_zero_false_positives():
    """HARD REQUIREMENT: zero false positives on real, working code. Run the attribute
    gate across the platform's own ~64 backend modules AND every real generated fixture
    (888's 10 files + the captured 1105 files). Not one may be flagged."""
    import os
    import glob
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    platform = []
    for path in glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True):
        rel = "backend/" + os.path.relpath(path, os.path.join(app_dir, "..")).replace(os.sep, "/")
        platform.append({"filepath": rel, "content": open(path, encoding="utf-8").read()})
    pidx = agents.build_symbol_index(platform)
    pf = []
    for f in platform:
        pf += agents.attribute_access_mismatches(f["content"], f["filepath"], pidx)
    check(f"ZERO false positives across the platform's own {len(platform)} backend modules",
          pf == [], str([(x["file"].split("/")[-1], x["class"] + "." + x["attribute"]) for x in pf[:8]]))

    fx = os.path.join(os.path.dirname(__file__), "fixtures")
    real = [{"filepath": os.path.basename(p).replace("__", "/"),
             "content": open(p, encoding="utf-8").read()}
            for p in sorted(glob.glob(os.path.join(fx, "gen888", "*.py")))]
    for name in ("stripe_stripeoauthstate_1105.py", "order_be_3_param_order_1071.py"):
        p = os.path.join(fx, name)
        if os.path.isfile(p):
            real.append({"filepath": f"backend/app/routes/{name}", "content": open(p, encoding="utf-8").read()})
    ridx = agents.build_symbol_index(real)
    rf = []
    for f in real:
        rf += agents.attribute_access_mismatches(f["content"], f["filepath"], ridx)
    check(f"ZERO false positives across {len(real)} real generated fixtures (888 + 1105)",
          rf == [], str([(x["file"], x["class"] + "." + x["attribute"]) for x in rf[:8]]))


def test_http_exception_swallow_gate():
    """FIX #24 regression (project 1289): the generated database.py `get_db` wrapped
    `yield session` in `except Exception: raise HTTPException(500)`. FastAPI runs the
    request inside the yield, so a downstream HTTPException(401) got re-raised as a 500 —
    every 401/404/422 on every DB endpoint became "Internal server error" (all 20 QA
    failures). The build gate must flag the 1289 file, attach a structured finding,
    render a targeted repair, and reject ONLY that ticket. Zero false positives: a
    dependency generator that catches a SPECIFIC exception, re-raises HTTPException, or
    guards with isinstance is correct; a broad-500 raise in a plain route handler (no
    yield) is out of scope."""
    import os
    import glob
    from app.developers import orchestrator as orch

    # 1289's EXACT captured database.py — the true positive.
    fx = os.path.join(os.path.dirname(__file__), "fixtures", "database_get_db_swallow_1289.py")
    bad = open(fx, encoding="utf-8").read()
    hit = agents.http_exception_swallow(bad, "backend/app/database.py")
    check("1289's get_db is flagged as an HTTPException swallow",
          len(hit) == 1 and hit[0]["function"] == "get_db", str(hit))

    # NEGATIVES — each of these is a correct pattern and must NOT be flagged.
    ok_specific = ("async def get_db():\n"
                   "    async with async_session() as s:\n"
                   "        try:\n            yield s\n"
                   "        except SQLAlchemyError as e:\n"
                   "            raise HTTPException(status_code=500, detail='db')\n")
    check("get_db catching a SPECIFIC SQLAlchemyError is NOT flagged (gen888 pattern)",
          agents.http_exception_swallow(ok_specific, "backend/app/database.py") == [])
    ok_sibling = ("async def get_db():\n"
                  "    try:\n"
                  "        async with async_session() as s:\n            yield s\n"
                  "    except HTTPException:\n        raise\n"
                  "    except Exception:\n        raise HTTPException(500, 'x')\n")
    check("a broad handler with an earlier `except HTTPException: raise` sibling is NOT flagged",
          agents.http_exception_swallow(ok_sibling, "backend/app/database.py") == [])
    ok_isinstance = ("async def get_db():\n"
                     "    try:\n"
                     "        async with async_session() as s:\n            yield s\n"
                     "    except Exception as e:\n"
                     "        if isinstance(e, HTTPException):\n            raise\n"
                     "        raise HTTPException(500, 'x')\n")
    check("a broad handler that re-raises HTTPException via isinstance guard is NOT flagged",
          agents.http_exception_swallow(ok_isinstance, "backend/app/database.py") == [])
    ok_bare = ("async def get_db():\n"
               "    try:\n"
               "        async with async_session() as s:\n            yield s\n"
               "    except Exception:\n        log()\n        raise\n")
    check("a broad handler with a bare `raise` (re-raise) is NOT flagged",
          agents.http_exception_swallow(ok_bare, "backend/app/database.py") == [])
    route_500 = ("async def create_order(db=Depends(get_db)):\n"
                 "    try:\n        return await do()\n"
                 "    except Exception:\n        raise HTTPException(status_code=500, detail='x')\n")
    check("a broad-500 raise in a plain route handler (no yield) is out of scope",
          agents.http_exception_swallow(route_500, "backend/app/routes/order.py") == [])
    check("a non-.py file is ignored",
          agents.http_exception_swallow(bad, "frontend/app/page.tsx") == [])

    # Zero-false-positive proof across platform + all real generated fixtures.
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    plat = [(p, open(p, encoding="utf-8").read())
            for p in glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True)]
    plat_fp = [p for p, c in plat if agents.http_exception_swallow(c, "backend/app/x.py")]
    check(f"ZERO false positives across the platform's own {len(plat)} backend modules",
          plat_fp == [], str(plat_fp[:6]))
    fxdir = os.path.join(os.path.dirname(__file__), "fixtures")
    real = list(glob.glob(os.path.join(fxdir, "gen888", "*.py")))
    for n in ("stripe_stripeoauthstate_1105.py", "order_be_3_param_order_1071.py"):
        p = os.path.join(fxdir, n)
        if os.path.isfile(p):
            real.append(p)
    real_fp = [os.path.basename(p) for p in real
               if agents.http_exception_swallow(open(p, encoding="utf-8").read(), "backend/app/x.py")]
    check("ZERO false positives across the real generated fixtures (888 + 1105/1071)",
          real_fp == [], str(real_fp))

    # Gate integration: _collect_stubs rejects ONLY the swallowing file, attaches the
    # structured finding, and the repair renders a precise HTTP_EXCEPTION_SWALLOW ticket.
    built = [
        {"ticket_id": "FND-2", "filepath": "backend/app/database.py",
         "content": bad, "status": "generated"},
        {"ticket_id": "FND-1", "filepath": "backend/app/models.py",
         "content": "class MenuItem(Base):\n    __tablename__ = 'menu_items'\n    id = Column(Integer)\n",
         "status": "generated"},
    ]
    stubbed = orch._collect_stubs(built, {}, 1)
    check("gate rejects ONLY the HTTPException-swallowing ticket",
          [s["ticket_id"] for s in stubbed] == ["FND-2"], str([s["ticket_id"] for s in stubbed]))
    fnd2 = next(s for s in built if s["ticket_id"] == "FND-2")
    check("the rejected ticket carries STUB_STATUS", fnd2["status"] == agents.STUB_STATUS)
    check("the rejected ticket carries the structured http_swallow_repairs",
          fnd2.get("http_swallow_repairs") and fnd2["http_swallow_repairs"][0]["function"] == "get_db",
          str(fnd2.get("http_swallow_repairs")))
    check("the clean model ticket is left untouched", built[1]["status"] == "generated")
    rt = agents.repair_instructions(fnd2)
    check("repair text is an HTTP_EXCEPTION_SWALLOW naming the function",
          "HTTP_EXCEPTION_SWALLOW" in rt and "get_db" in rt, rt)
    check("repair text tells it to let HTTPException propagate / not turn into 500",
          "propagate" in rt.lower() and "HTTPException(500)" in rt, rt)
    check("repair text scopes the fix to this file only", "only this file" in rt.lower(), rt)


async def scenario_syntax_repair_retry():
    print("\n=== S5: a syntax-broken backend file is REPAIRED via the structured retry -> built ===")
    pid = await _make_project()

    bp = {"sprint_tickets": [
        {"id": "FND-1", "title": "models", "assigned_to": "backend",
         "filepath": "backend/app/models.py", "description": "x", "dependencies": []},
        {"id": "BE-3", "title": "order update", "assigned_to": "backend",
         "filepath": "backend/app/routes/order_be_3.py", "description": "x", "dependencies": ["FND-1"]},
        {"id": "APP-1", "title": "entrypoint", "assigned_to": "backend",
         "filepath": "backend/app/main.py", "description": "x", "dependencies": ["FND-1"]}],
        "llm_routing": {}, "database_schema": [], "api_endpoints": []}
    async with async_session() as db:
        row = await db.get(Blueprint, (await db.execute(
            select(Blueprint.id).where(Blueprint.project_id == pid))).scalar_one())
        row.blueprint_json = json.dumps(bp)
        await db.commit()

    seen_repair: dict[str, str] = {}
    calls: dict[str, int] = {}

    async def _bt(ticket, model, existing, contract="", repair=""):
        tid = ticket["id"]
        calls[tid] = calls.get(tid, 0) + 1
        if tid == "BE-3":
            seen_repair[f"call{calls[tid]}"] = repair
            if calls[tid] == 1:   # first attempt: the 1071 param-ordering SyntaxError
                content = ("def f(\n    order_id: int = 1,\n    order_update,\n):\n    return order_id\n")
            else:                 # retry: parameters reordered -> parses
                content = ("def f(\n    order_update,\n    order_id: int = 1,\n):\n    return order_id\n")
        elif tid == "FND-1":
            content = "class MenuItem(Base):\n    __tablename__ = 'menu_items'\n    id = Column(Integer)\n"
        else:
            content = "app = 1\n"
        return {"filename": ticket["filepath"].rpartition("/")[2],
                "filepath": ticket["filepath"], "content": content,
                "agent_type": "backend", "ticket_id": tid, "status": "generated"}

    agents.build_ticket = _bt
    summary = await orch.run(pid, bp)
    print(f"    summary={summary}   BE-3 calls={calls.get('BE-3')}")
    check("BE-3 was retried once (syntax error -> gate -> retry)", calls.get("BE-3") == 2, str(calls))
    check("the FIRST attempt got NO repair text", seen_repair.get("call1") == "")
    check("the RETRY received a structured SYNTAX_ERROR repair",
          "SYNTAX_ERROR" in (seen_repair.get("call2") or ""), seen_repair.get("call2"))
    check("the repair converged -> status 'built'", summary["status"] == "built", str(summary))
    check("no surviving stubs", summary["stubbed"] == [], str(summary))

    async with async_session() as db:
        row = (await db.execute(select(GeneratedFile.content).where(
            GeneratedFile.project_id == pid, GeneratedFile.ticket_id == "BE-3"))).first()
    check("BE-3's file now PARSES (real Python)",
          row and agents.python_syntax_error(row[0], "backend/app/routes/order_be_3.py") is None, str(row))


async def scenario_symbol_repair_retry():
    print("\n=== S4: a bad-import file is REPAIRED via the structured retry -> built ===")
    pid = await _make_project()

    # A blueprint whose BE-1 (routes/menu.py) imports a bad auth symbol on the first
    # attempt; FND-1 provides the real auth exports; APP-1 is a clean entrypoint.
    bp = {"sprint_tickets": [
        {"id": "FND-1", "title": "auth", "assigned_to": "backend",
         "filepath": "backend/app/auth.py", "description": "x", "dependencies": []},
        {"id": "BE-1", "title": "routes", "assigned_to": "backend",
         "filepath": "backend/app/routes/menu.py", "description": "x", "dependencies": ["FND-1"]},
        {"id": "APP-1", "title": "entrypoint", "assigned_to": "backend",
         "filepath": "backend/app/main.py", "description": "x", "dependencies": ["FND-1"]}],
        "llm_routing": {}, "database_schema": [], "api_endpoints": []}
    async with async_session() as db:
        row = await db.get(Blueprint, (await db.execute(
            select(Blueprint.id).where(Blueprint.project_id == pid))).scalar_one())
        row.blueprint_json = json.dumps(bp)
        await db.commit()

    seen_repair: dict[str, str] = {}
    calls: dict[str, int] = {}

    def _auth_file():
        return ("def get_current_user():\n    return {}\n"
                "def get_current_admin_user():\n    return {}\n")

    async def _bt(ticket, model, existing, contract="", repair=""):
        tid = ticket["id"]
        calls[tid] = calls.get(tid, 0) + 1
        if tid == "FND-1":
            content = _auth_file()
        elif tid == "BE-1":
            seen_repair[f"call{calls[tid]}"] = repair
            if calls[tid] == 1:      # first attempt: the 1038 bad import
                content = "from backend.app.auth import require_admin\nrouter = 1\n"
            else:                    # retry: repaired to a real export
                content = "from backend.app.auth import get_current_admin_user\nrouter = 1\n"
        else:
            content = "app = 1\n"
        return {"filename": ticket["filepath"].rpartition("/")[2],
                "filepath": ticket["filepath"], "content": content,
                "agent_type": "backend", "ticket_id": tid, "status": "generated"}

    agents.build_ticket = _bt
    summary = await orch.run(pid, bp)
    print(f"    summary={summary}   BE-1 calls={calls.get('BE-1')}")
    check("BE-1 was retried once (bad import -> gate -> retry)", calls.get("BE-1") == 2, str(calls))
    check("the FIRST attempt got NO repair text", seen_repair.get("call1") == "")
    check("the RETRY received a structured IMPORT_RESOLUTION_FAILURE repair",
          "IMPORT_RESOLUTION_FAILURE" in (seen_repair.get("call2") or "")
          and "require_admin" in (seen_repair.get("call2") or ""), seen_repair.get("call2"))
    check("the repair converged -> status 'built'", summary["status"] == "built", str(summary))
    check("no surviving stubs", summary["stubbed"] == [], str(summary))

    async with async_session() as db:
        row = (await db.execute(select(GeneratedFile.content).where(
            GeneratedFile.project_id == pid, GeneratedFile.ticket_id == "BE-1"))).first()
    check("BE-1's file now imports a REAL auth export, not require_admin",
          row and "get_current_admin_user" in row[0] and "require_admin" not in row[0], str(row))


async def main():
    original = agents.build_ticket
    removed = await cleanup()
    if removed:
        print(f"(cleaned {removed} previous synthetic project(s))")
    try:
        test_auth_symbol_contract()
        test_response_model_rule()
        test_pydantic_v2_rule()
        test_frontend_item_image_rule()
        test_stub_function_detection()
        test_build_gate()
        test_no_stub_prompt_rule()
        test_session_dependency_rule()
        test_schema_adherence()
        test_frontend_completeness_gate()
        test_import_symbol_resolution_gate()
        test_import_symbol_zero_false_positives()
        test_python_syntax_gate()
        test_attribute_resolution_gate()
        test_attribute_zero_false_positives()
        test_http_exception_swallow_gate()
        test_missing_endpoint_attribution()
        test_frontend_deps_and_css_gate()
        test_frontend_missing_login_gate()
        test_duplicate_endpoint_gate()
        test_hallucinated_package_gate()
        test_hallucinated_submodule_gate()
        test_rewrite_integrity_gate()
        test_frontend_parse_gate()
        test_reviewer_rejects_unsafe_autofix()
        test_reviewer_frontend_accept_seam()
        await test_review_file_frontend_readonly()
        await test_reviewer_frontend_confirmed_repair()
        test_timestamp_not_null_gate()
        test_dangling_foreign_key_gate()
        test_missing_in_project_module_gate()
        await scenario_all_good()
        await scenario_one_stub()
        await scenario_stub_recovers_on_retry()
        await scenario_symbol_repair_retry()
        await scenario_syntax_repair_retry()
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
