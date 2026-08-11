"""Offline proof for the Menu Onboarding feature (Week 10 Part 2).

Covers all six agent changes with NO LLM, NO network, NO real build:
  - Architect: deterministic MENU tickets + schema + endpoints, gated on
    is_food + menu_setup; manual vs pdf; not emitted for non-food; LLM guard.
  - BA: menu-setup parsing, ASK_MENU gating on is_food, summary capture.
  - Code Reviewer: extraction files flagged (MENU-3/4 + upload/review paths),
    ordinary menu CRUD NOT flagged.
  - QA: the _menu_pdf_extraction probe PASSES a correct synthetic app and FAILS
    a broken one (crashes on a corrupt PDF / auto-publishes) — so the probe can
    fail for the reason it exists.
  - Documentation: the menu fact derives from real files; the PDF guide/handoff
    mention the review step and do not overstate accuracy.
  - DevOps: _has_menu_pdf gates the scoped platform vision-key injection.

Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
    backend python tests/test_menu_onboarding_offline.py
"""
import asyncio

PASS = 0
FAIL = 0


def check(cond: bool, label: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {label}")
    else:
        FAIL += 1
        print(f"[FAIL] {label}")


# ======================================================================= ARCHITECT
from app.architect import builder

# No LLM: force the deterministic mock so only our menu additions vary.
builder._generate_creative = lambda *a, **k: _none()


async def _none():
    return None


async def _wrap(val):
    return val


def _bp(is_food, menu_setup):
    return asyncio.run(builder.build_blueprint({
        "build": "a taco spot", "is_food": is_food, "menu_setup": menu_setup,
        "audience": "customers", "user_count": "100", "budget": "$50",
        "mobile_choice": None,
    }))


bp_pdf = _bp(True, "pdf")
ids_pdf = [t["id"] for t in bp_pdf["sprint_tickets"]]
tables_pdf = [t["table"] for t in bp_pdf["database_schema"]]
paths_pdf = [e["path"] for e in bp_pdf["api_endpoints"]]

check(all(i in ids_pdf for i in ("MENU-1", "MENU-2", "MENU-3", "MENU-4")),
      "Architect food+pdf: emits MENU-1..4")
check("menu_items" in tables_pdf, "Architect food+pdf: menu_items table in schema")
check("/admin/menu/upload" in paths_pdf and "/menu" in paths_pdf,
      "Architect food+pdf: upload + public menu endpoints in contract")
menu_files = [t.get("filepath") for t in bp_pdf["sprint_tickets"]
              if str(t["id"]).startswith("MENU-")]
check(len(menu_files) == len(set(menu_files)) and all(menu_files),
      "Architect: every MENU ticket has a unique explicit filepath")

bp_manual = _bp(True, "manual")
ids_manual = [t["id"] for t in bp_manual["sprint_tickets"]]
paths_manual = [e["path"] for e in bp_manual["api_endpoints"]]
check("MENU-1" in ids_manual and "MENU-2" in ids_manual,
      "Architect food+manual: emits MENU-1 + MENU-2")
check("MENU-3" not in ids_manual and "MENU-4" not in ids_manual,
      "Architect food+manual: NO PDF tickets (MENU-3/4 absent)")
check("/admin/menu/upload" not in paths_manual,
      "Architect food+manual: no upload endpoint")
check("menu_items" in [t["table"] for t in bp_manual["database_schema"]],
      "Architect food+manual: shared menu_items table still present")

bp_none = _bp(False, None)
ids_none = [t["id"] for t in bp_none["sprint_tickets"]]
check(not any(str(i).startswith("MENU-") for i in ids_none),
      "Architect non-food: NO menu tickets")
check("menu_items" not in [t["table"] for t in bp_none["database_schema"]],
      "Architect non-food: no menu_items table")

check("menu" in builder._ARCH_SYSTEM.lower()
      and "do not create" in builder._ARCH_SYSTEM.lower(),
      "Architect LLM prompt tells the model not to generate menu tickets")

# MENU-3 must actually instruct the two extraction methods + no-auto-publish.
m3 = next(t for t in bp_pdf["sprint_tickets"] if t["id"] == "MENU-3")["description"].lower()
check("text" in m3 and ("vision" in m3 or "image" in m3) and "pending_review" in m3
      and "menu_extraction_api_key" in m3,
      "MENU-3 spec: text-first + vision fallback + pending_review + platform key")
check("filename" in m3 and ("max" in m3 or "size" in m3),
      "MENU-3 spec: filename-injection + file-size guardrails called out")
# project 689: the LLM hallucinated `from anthropic import Claude`. Pin the real
# SDK client class and forbid the made-up one.
check("from anthropic import anthropic" in m3,
      "MENU-3 spec: pins the real Anthropic SDK client class (from anthropic import Anthropic)")
check("no `claude` class" in m3,
      "MENU-3 spec: forbids the hallucinated `Claude` import class (project 689)")

# --- REGRESSION: the live-run bug — LLM Architect ALSO schemas menu_items.
# Two menu_items entries made FND-1 define the model twice ("table already
# defined") and the app never booted. build_blueprint must reconcile to ONE.
_llm_with_menu = {
    "tech_stack": {"backend": "FastAPI", "frontend": "Next.js", "database": "PostgreSQL"},
    "database_schema": [
        {"table": "menu_items", "columns": [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "string"},
            {"name": "image_url", "type": "string"},   # extra column only the LLM has
        ], "relationships": []},
        {"table": "orders", "columns": [{"name": "id", "type": "integer"}],
         "relationships": []},
    ],
    "api_endpoints": [{"method": "GET", "path": "/menu", "purpose": "display"}],
    "sprint_tickets": [{"id": "BE-1", "title": "menu retrieval endpoint",
                        "assigned_to": "backend", "description": "GET /menu",
                        "dependencies": []}],
}
builder._generate_creative = lambda *a, **k: _wrap(_llm_with_menu)
bp_collide = asyncio.run(builder.build_blueprint({
    "build": "an italian restaurant", "is_food": True, "menu_setup": "pdf",
    "audience": "customers", "user_count": "100", "budget": "$50", "mobile_choice": None}))
menu_tables = [t for t in bp_collide["database_schema"]
               if (t.get("table") or "").lower() == "menu_items"]
check(len(menu_tables) == 1,
      "Architect dedupe: EXACTLY ONE menu_items table when the LLM also schemas one")
_cols = {c["name"] for c in menu_tables[0]["columns"]} if menu_tables else set()
check({"status", "source", "name", "price"}.issubset(_cols),
      "Architect dedupe: the surviving menu_items keeps the feature's required columns")
check("image_url" in _cols,
      "Architect dedupe: extra LLM columns (image_url) are merged, not lost")
builder._generate_creative = lambda *a, **k: _none()   # restore mock for later use


# ============================================================================= BA
from app.ba import controller, state as st

check(controller._parse_menu_setup("Upload a PDF") == "pdf"
      and controller._parse_menu_setup("upload my file") == "pdf",
      "BA: 'upload a PDF' -> pdf")
check(controller._parse_menu_setup("Type them in myself") == "manual"
      and controller._parse_menu_setup("i'll type them") == "manual",
      "BA: 'type them in' -> manual")

food_state = st.BAState(project_id=1, fields={"is_food": True})
nonfood_state = st.BAState(project_id=2, fields={"is_food": False})
check(controller._should_skip(st.ASK_MENU, nonfood_state) is True,
      "BA: ASK_MENU skipped for a non-food business")
check(controller._should_skip(st.ASK_MENU, food_state) is False,
      "BA: ASK_MENU asked for a food business")
check(st.ASK_MENU in st.ORDER and st.ORDER.index(st.ASK_MENU) > st.ORDER.index(st.ASK_AUDIENCE),
      "BA: ASK_MENU is in the ordered flow after audience")

summ = controller.build_summary_dict(
    st.BAState(project_id=3, fields={"is_food": True, "menu_setup": "pdf", "build": "x"}))
check(summ.get("is_food") is True and summ.get("menu_setup") == "pdf",
      "BA: summary carries is_food + menu_setup to the Architect")


# ======================================================================= REVIEWER
from app.reviewer import reviewer

check(reviewer._is_menu_extraction({"ticket_id": "MENU-3"}) is True,
      "Reviewer: MENU-3 flagged for extra scrutiny")
check(reviewer._is_menu_extraction(
      {"filepath": "backend/app/routes/menu_upload.py"}) is True,
      "Reviewer: menu_upload.py flagged by path")
check(reviewer._is_menu_extraction(
      {"filepath": "frontend/app/admin/menu/review/page.tsx"}) is True,
      "Reviewer: menu review screen flagged by path")
check(reviewer._is_menu_extraction(
      {"ticket_id": "MENU-1", "filepath": "backend/app/routes/menu.py"}) is False,
      "Reviewer: ordinary menu CRUD (MENU-1) is NOT over-flagged")
check(reviewer._is_menu_extraction(
      {"filepath": "backend/app/routes/orders.py"}) is False,
      "Reviewer: an unrelated file is not flagged")
check("upload" in reviewer._MENU_EXTRACTION_FOCUS.lower()
      and "auto-publish" in reviewer._MENU_EXTRACTION_FOCUS.lower(),
      "Reviewer: extraction focus checklist covers uploads + auto-publish")


# ================================================================== DOCUMENTATION
from app.documentation import datasource, generators

check(datasource._menu([{"filepath": "backend/app/routes/menu_upload.py"}])
      == {"built": True, "is_pdf": True},
      "Docs: menu_upload.py -> menu built + pdf path")
mn = datasource._menu([{"filepath": "backend/app/routes/menu.py"}])
check(mn["built"] is True and mn["is_pdf"] is False,
      "Docs: menu.py -> menu built, not pdf")
check(datasource._menu([{"filepath": "backend/app/routes/orders.py"}])["built"] is False,
      "Docs: no menu files -> menu not built")

# Force the deterministic (no-spend) fallback path in the guide generator.
generators._llm = lambda *a, **k: _none()

_facts_pdf = {
    "business_name": "Taco Spot", "platform": "website", "features": [],
    "screens": [], "has_payments": False, "menu": {"built": True, "is_pdf": True},
}
guide_pdf = asyncio.run(generators.user_guide(_facts_pdf))
check("Your menu" in guide_pdf and ("review" in guide_pdf.lower()
      or "Confirm" in guide_pdf),
      "Docs (pdf): user guide has a menu section mentioning review/confirm")
check("perfect" in guide_pdf.lower(),
      "Docs (pdf): guide is honest that extraction 'isn't always perfect'")

_facts_manual = {**_facts_pdf, "menu": {"built": True, "is_pdf": False}}
guide_manual = asyncio.run(generators.user_guide(_facts_manual))
check("Your menu" in guide_manual and "Add item" in guide_manual
      and "upload" not in guide_manual.lower(),
      "Docs (manual): guide describes typing items in, not uploading")

_facts_ho = {
    "project_id": 1, "business_name": "Taco Spot", "built_at": None,
    "platform": "website", "features": [], "screens": [],
    "deployment": None, "integrations": [],
    "security": {"status": "ok", "passed": True, "issues_found": 0,
                 "issues_fixed": 0, "model_used": "x"},
    "qa": {"available": True, "total": 3, "passed": 3, "failed": 0, "escalated": 0},
    "menu": {"built": True, "is_pdf": True},
}
ho = generators.handoff_summary(_facts_ho)
check(any("review" in n.lower() and "menu" in n.lower() for n in ho["honest_notes"]),
      "Docs (pdf): handoff honest_notes flag the menu review-before-publish step")
_facts_ho_manual = {**_facts_ho, "menu": {"built": True, "is_pdf": False}}
ho_m = generators.handoff_summary(_facts_ho_manual)
check(not any("menu" in n.lower() for n in ho_m["honest_notes"]),
      "Docs (manual): no PDF-review note when the manual path shipped")


# ========================================================================= DEVOPS
from app.devops import orchestrator
from app.config import settings

check(orchestrator._has_menu_pdf(
      [{"filepath": "backend/app/routes/menu_upload.py"}]) is True,
      "DevOps: _has_menu_pdf detects the upload route file")
check(orchestrator._has_menu_pdf(
      [{"ticket_id": "MENU-3", "filepath": "x"}]) is True,
      "DevOps: _has_menu_pdf detects MENU-3 by ticket id")
check(orchestrator._has_menu_pdf(
      [{"filepath": "backend/app/routes/menu.py"}]) is False,
      "DevOps: manual-only menu app does NOT trigger the vision key")
check(hasattr(settings, "menu_extraction_api_key"),
      "DevOps: settings expose the scoped platform menu_extraction_api_key")


# ====================================================================== QA PROBE
# Prove the probe against a CORRECT app (all checks pass) and a BROKEN app
# (crashes on a corrupt PDF AND auto-publishes) — so it can fail for cause.
import httpx
from fastapi import FastAPI, Request, HTTPException
from app.qa import level2

pdf_bytes = level2._text_pdf("QATESTMENUITEM 9.99")
check(pdf_bytes.startswith(b"%PDF") and b"QATESTMENUITEM" in pdf_bytes
      and b"stream" in pdf_bytes,
      "QA: _text_pdf builds a %PDF with the sentinel + a content stream")

_SPEC = {"paths": {"/admin/menu/upload": {"post": {"summary": "upload"}}}}


def _good_app():
    app = FastAPI()
    pending, published = [], []

    @app.post("/admin/menu/upload")
    async def up(request: Request):
        data = await request.body()
        if b"%PDF" not in data:
            raise HTTPException(400, "not a pdf")
        if b"QATESTMENUITEM" in data:      # real text extracted -> await review
            pending.append("QATESTMENUITEM 9.99")
            return {"pending": 1}
        raise HTTPException(400, "could not read menu")   # corrupt: graceful

    @app.get("/menu")
    async def menu():
        return published                    # published only (never pending)

    @app.get("/admin/menu/pending")
    async def pend():
        return pending
    return app


def _bad_app():
    app = FastAPI()
    published = []

    @app.post("/admin/menu/upload")
    async def up(request: Request):
        data = await request.body()
        data.index(b"stream")               # ValueError -> 500 on a corrupt PDF
        published.append("QATESTMENUITEM 9.99")   # auto-publishes, no review
        return {"ok": True}

    @app.get("/menu")
    async def menu():
        return published
    return app


async def _run_probe(app):
    # raise_app_exceptions=False -> an unhandled crash becomes a 500 RESPONSE,
    # exactly what the probe sees over real HTTP (not a client-side exception).
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        return await level2._menu_pdf_extraction(c, "http://localhost", _SPEC)


good = asyncio.run(_run_probe(_good_app()))
check(len(good) >= 2 and all(o.passed for o in good),
      "QA probe: a correct menu app passes every extraction check")
check(any("auto-published" in o.name for o in good),
      "QA probe: the auto-publish guard actually ran (name present)")

bad = asyncio.run(_run_probe(_bad_app()))
crash = next((o for o in bad if "corrupt PDF handled gracefully" in o.name), None)
autopub = next((o for o in bad if "auto-published" in o.name), None)
check(crash is not None and not crash.passed,
      "QA probe: FAILS a server that crashes on a corrupt PDF")
check(autopub is not None and not autopub.passed,
      "QA probe: FAILS a server that auto-publishes extracted items")


# ============================================================================ END
print()
print(f"{PASS} passed, {FAIL} failed")
if FAIL == 0:
    print("RESULT: ALL CHECKS PASSED ✓")
    raise SystemExit(0)
print("RESULT: FAILURES ✗")
raise SystemExit(1)
