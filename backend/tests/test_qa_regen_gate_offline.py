"""Close the ungated QA regeneration loop (run 1105).

Run 1105 proved the decisive hole: QA's repair loop regenerates a file through the
Developer agent and ACCEPTED the result with NO deterministic validation, so it
re-introduced the exact classes the BUILD gate already closes:
  * `order_be_3.py` — a param-ordering `SyntaxError` (fix #17 class); and
  * `stripe.py` — `from backend.app.models import StripeOAuthState`, a symbol
    models.py never exported (fix #16 class).
Both then broke the app at boot. QA's regeneration path now gets the SAME
deterministic gates (`qa.orchestrator._gate_regenerated`) plus a BOUNDED, re-validated
repair (`_regenerate_validated`); a rewrite that still fails is REJECTED (previous
content kept), never churned into a non-booting state.

Pure-function + monkeypatched-`_regenerate` tests — no LLM, no network, no DB.

Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tests/test_qa_regen_gate_offline.py
"""
import asyncio
import glob
import os
import sys

import app.qa.orchestrator as orch
from app.qa.outcome import TestOutcome

_failures: list[str] = []
_FX = os.path.join(os.path.dirname(__file__), "fixtures")


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"   ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


# Minimal in-project foundation so a candidate's imports can be resolved. models.py
# deliberately does NOT define StripeOAuthState (the exact 1105 state QA created).
_MODELS = {"id": 1, "filepath": "backend/app/models.py", "content": (
    "from backend.app.database import Base\n"
    "from sqlalchemy import Column, Integer, String\n"
    "class StripeAccount(Base):\n    __tablename__ = 'stripe_accounts'\n"
    "    id = Column(Integer)\n    user_id = Column(Integer)\n    connected = Column(Boolean)\n"
    "class MenuItem(Base):\n    __tablename__ = 'menu_items'\n"
    "    id = Column(Integer)\n    name = Column(String)\n    price = Column(Integer)\n    status = Column(String)\n")}
_DATABASE = {"id": 2, "filepath": "backend/app/database.py", "content": (
    "Base = object\n"
    "async def get_db():\n    yield None\n"
    "def async_session():\n    return None\n")}
_AUTH = {"id": 3, "filepath": "backend/app/auth.py", "content": (
    "def get_current_user():\n    return {}\n"
    "def get_current_admin_user():\n    return {}\n")}


def _read_fixture(name: str) -> str:
    return open(os.path.join(_FX, name), encoding="utf-8").read()


def test_gate_syntax():
    """The QA-regen gate flags 1105's real param-ordering SyntaxError (fix #17 class)."""
    bad = _read_fixture("order_be_3_param_order_1071.py")
    files = [_MODELS, _DATABASE, _AUTH,
             {"id": 10, "filepath": "backend/app/routes/order_be_3.py", "content": bad}]
    gate = orch._gate_regenerated(bad, "backend/app/routes/order_be_3.py", files, 10)
    check("regenerated order_be_3 (syntax error) is flagged by the QA gate",
          bool(gate.get("syntax_error")), str(gate))
    check("the syntax finding names the offending line",
          gate.get("syntax_error", {}).get("line") == 18, str(gate.get("syntax_error")))
    # It renders a SYNTAX_ERROR repair (fed back into the bounded retry).
    rt = orch.dev_agents.repair_instructions(gate)
    check("gate result renders a SYNTAX_ERROR repair", "SYNTAX_ERROR" in rt, rt)


def test_gate_symbol():
    """The QA-regen gate flags 1105's real `stripe.py`->`StripeOAuthState` wrong-symbol
    import (fix #16 class) and leaves the valid sibling imports alone."""
    bad = _read_fixture("stripe_stripeoauthstate_1105.py")
    files = [_MODELS, _DATABASE, _AUTH,
             {"id": 11, "filepath": "backend/app/routes/stripe.py", "content": bad}]
    gate = orch._gate_regenerated(bad, "backend/app/routes/stripe.py", files, 11)
    syms = [s["symbol"] for s in gate.get("symbol_repairs", [])]
    check("regenerated stripe.py's StripeOAuthState import is flagged", syms == ["StripeOAuthState"], str(syms))
    check("valid siblings (StripeAccount, get_db, get_current_admin_user) NOT flagged",
          all(s not in syms for s in ("StripeAccount", "get_db", "get_current_admin_user")), str(syms))
    rt = orch.dev_agents.repair_instructions(gate)
    check("gate result renders an IMPORT_RESOLUTION_FAILURE repair naming the symbol",
          "IMPORT_RESOLUTION_FAILURE" in rt and "StripeOAuthState" in rt, rt)
    # Once models.py DOES export StripeOAuthState, the same file is clean.
    models_fixed = {**_MODELS, "content": _MODELS["content"] +
                    "class StripeOAuthState(Base):\n    __tablename__ = 'stripe_oauth_states'\n"
                    "    id = Column(Integer)\n    state = Column(String)\n"
                    "    user_id = Column(Integer)\n    expires_at = Column(TIMESTAMP)\n"}
    files2 = [models_fixed, _DATABASE, _AUTH,
              {"id": 11, "filepath": "backend/app/routes/stripe.py", "content": bad}]
    check("with StripeOAuthState defined, the same stripe.py passes the gate",
          orch._gate_regenerated(bad, "backend/app/routes/stripe.py", files2, 11) == {}, "should be clean")


def test_gate_attribute():
    """The QA-regen gate also runs the attribute-resolution check (fix #19): a regenerated
    file accessing a field the in-project model does not define is flagged, not accepted."""
    bad = ("from backend.app.models import MenuItem\n"
           "from sqlalchemy import select\n"
           "def q():\n    return select(MenuItem.total_amount)\n")   # MenuItem has no total_amount
    files = [_MODELS, _DATABASE, _AUTH,
             {"id": 13, "filepath": "backend/app/routes/menu.py", "content": bad}]
    gate = orch._gate_regenerated(bad, "backend/app/routes/menu.py", files, 13)
    check("a regenerated file with a bad attribute access is flagged by the QA gate",
          [a["attribute"] for a in gate.get("attribute_repairs", [])] == ["total_amount"], str(gate))
    rt = orch.dev_agents.repair_instructions(gate)
    check("gate result renders an ATTRIBUTE_RESOLUTION_FAILURE repair",
          "ATTRIBUTE_RESOLUTION_FAILURE" in rt and "total_amount" in rt, rt)
    good = bad.replace("total_amount", "price")
    check("using a real field passes the QA gate",
          orch._gate_regenerated(good, "backend/app/routes/menu.py",
                                 [_MODELS, _DATABASE, _AUTH,
                                  {"id": 13, "filepath": "backend/app/routes/menu.py", "content": good}], 13) == {},
          "should be clean")


def test_gate_http_swallow():
    """The QA-regen gate also runs the HTTPException-swallow check (fix #24): a regenerated
    database.py whose get_db re-raises framework HTTPExceptions as a 500 is flagged, not
    accepted (run 1289's QA loop regenerated files — this closes that class here too)."""
    import os
    fx = os.path.join(os.path.dirname(__file__), "fixtures", "database_get_db_swallow_1289.py")
    bad = open(fx, encoding="utf-8").read()
    files = [_MODELS, _AUTH, {"id": 14, "filepath": "backend/app/database.py", "content": bad}]
    gate = orch._gate_regenerated(bad, "backend/app/database.py", files, 14)
    check("a regenerated get_db that swallows HTTPException is flagged by the QA gate",
          [h["function"] for h in gate.get("http_swallow_repairs", [])] == ["get_db"], str(gate))
    rt = orch.dev_agents.repair_instructions(gate)
    check("gate result renders an HTTP_EXCEPTION_SWALLOW repair",
          "HTTP_EXCEPTION_SWALLOW" in rt and "get_db" in rt, rt)
    good = ("from sqlalchemy.ext.asyncio import AsyncSession\n"
            "async def get_db():\n    async with async_session() as s:\n        yield s\n")
    check("a clean get_db passes the QA gate",
          orch._gate_regenerated(good, "backend/app/database.py",
                                 [_MODELS, _AUTH,
                                  {"id": 14, "filepath": "backend/app/database.py", "content": good}], 14) == {},
          "should be clean")


def test_gate_clean_and_noop():
    """A valid regeneration passes; non-.py / frontend files are a no-op (not this gate's job)."""
    good = ("from backend.app.database import get_db\n"
            "def handler(db=None):\n    return {'ok': True}\n")
    files = [_MODELS, _DATABASE, _AUTH,
             {"id": 12, "filepath": "backend/app/routes/ok.py", "content": good}]
    check("a clean regenerated backend .py passes the gate ({})",
          orch._gate_regenerated(good, "backend/app/routes/ok.py", files, 12) == {}, "should be clean")
    check("a frontend .tsx is a no-op for this gate",
          orch._gate_regenerated("const x = (", "frontend/app/page.tsx", files, 99) == {})
    check("a non-.py file is a no-op",
          orch._gate_regenerated("body {", "frontend/app/globals.css", files, 98) == {})


def test_gate_zero_false_positives():
    """HARD REQUIREMENT: zero false positives on real, working code. Run the QA-regen
    gate over (a) the platform's OWN backend and (b) 888's real generated files —
    treating each file as a 'regeneration' of itself against the real set. None may flag."""
    # (a) platform
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    plat = []
    for i, p in enumerate(sorted(glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True))):
        rel = "backend/" + os.path.relpath(p, os.path.join(app_dir, "..")).replace(os.sep, "/")
        plat.append({"id": i, "filepath": rel, "content": open(p, encoding="utf-8").read()})
    plat_flags = [f["filepath"] for f in plat
                  if orch._gate_regenerated(f["content"], f["filepath"], plat, f["id"])]
    check(f"ZERO false positives across the platform's own {len(plat)} backend modules",
          plat_flags == [], str(plat_flags[:6]))
    # (b) 888 WORKING files (exclude the known-orphaned order/stripe dead code)
    gdir = os.path.join(_FX, "gen888")
    orphaned = {"backend/app/routes/order.py", "backend/app/routes/order_be_2.py",
                "backend/app/routes/stripe.py"}
    g = []
    for i, p in enumerate(sorted(glob.glob(os.path.join(gdir, "*.py")))):
        rel = os.path.basename(p).replace("__", "/")
        g.append({"id": i, "filepath": rel, "content": open(p, encoding="utf-8").read()})
    g_flags = [f["filepath"] for f in g if f["filepath"] not in orphaned
               and orch._gate_regenerated(f["content"], f["filepath"], g, f["id"])]
    check("ZERO false positives across 888's real WORKING generated files", g_flags == [], str(g_flags))


# ------------------------------------------------------------------ wrapper scenarios
_BAD_SYNTAX = "def f(\n    a: int = 1,\n    b,\n):\n    return a\n"          # non-default after default
_GOOD = "def f(\n    b,\n    a: int = 1,\n):\n    return a\n"                 # reordered -> parses
_ROW = {"id": 10, "filepath": "backend/app/routes/order_be_3.py", "ticket_id": "BE-3", "agent_type": "backend"}
_FILES = [_MODELS, _DATABASE, _AUTH, _ROW | {"content": "x = 1\n"}]
_BP = {"llm_routing": {}, "sprint_tickets": [], "database_schema": [], "api_endpoints": []}


def _script_regenerate(sequence):
    """Return an async stand-in for orch._regenerate that yields `sequence` items in
    order and records the `repair` string it was called with each time."""
    calls = {"n": 0, "repairs": []}

    async def _fake(file_row, ticket, blueprint, failures, repair=""):
        calls["repairs"].append(repair)
        i = min(calls["n"], len(sequence) - 1)
        calls["n"] += 1
        return sequence[i]
    return _fake, calls


async def scenario_converges():
    print("\n=== S1: broken rewrite on attempt 1, fixed on attempt 2 -> ACCEPTED ===")
    orig = orch._regenerate
    fake, calls = _script_regenerate([_BAD_SYNTAX, _GOOD])
    orch._regenerate = fake
    try:
        out = await orch._regenerate_validated(_ROW, {"id": "BE-3", "assigned_to": "backend"}, _BP, [], _FILES)
    finally:
        orch._regenerate = orig
    check("a broken-then-fixed regeneration converges (returns the parseable version)",
          out == _GOOD, repr(out))
    check("it took 2 attempts", calls["n"] == 2, str(calls["n"]))
    check("attempt 1 got NO repair text", calls["repairs"][0] == "")
    check("attempt 2 was fed a structured SYNTAX_ERROR repair",
          "SYNTAX_ERROR" in (calls["repairs"][1] or ""), calls["repairs"][1])


async def scenario_rejects():
    print("\n=== S2: rewrite broken on EVERY attempt -> REJECTED (None), previous kept ===")
    orig = orch._regenerate
    fake, calls = _script_regenerate([_BAD_SYNTAX])   # always broken
    orch._regenerate = fake
    try:
        out = await orch._regenerate_validated(_ROW, {"id": "BE-3", "assigned_to": "backend"}, _BP, [], _FILES)
    finally:
        orch._regenerate = orig
    check("a persistently-broken regeneration is REJECTED (None, not accepted)", out is None, repr(out))
    check("it stopped at the bounded attempt limit",
          calls["n"] == orch._QA_REGEN_MAX_REVALIDATE + 1, str(calls["n"]))


async def scenario_accepts_clean():
    print("\n=== S3: a clean rewrite on attempt 1 -> ACCEPTED immediately, no repair ===")
    orig = orch._regenerate
    fake, calls = _script_regenerate([_GOOD])
    orch._regenerate = fake
    try:
        out = await orch._regenerate_validated(_ROW, {"id": "BE-3", "assigned_to": "backend"}, _BP, [], _FILES)
    finally:
        orch._regenerate = orig
    check("a clean regeneration is accepted on the first attempt", out == _GOOD, repr(out))
    check("no wasted extra attempts", calls["n"] == 1, str(calls["n"]))


async def main():
    test_gate_syntax()
    test_gate_symbol()
    test_gate_attribute()
    test_gate_http_swallow()
    test_gate_clean_and_noop()
    test_gate_zero_false_positives()
    await scenario_converges()
    await scenario_rejects()
    await scenario_accepts_clean()

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
