"""QA agent (Week 6) verification — real assembly, real HTTP, no LLM spend.

Builds three synthetic "generated apps" and runs the actual QA machinery
against them:

  A) VULNERABLE app  -> Level 1 + Level 2 must CATCH the planted bugs
  B) WELL-BUILT app  -> must pass cleanly (no false positives)
  C) BROKEN app      -> assembly must fail as a QA FINDING, not a crash

Root-cause tracing is checked against its deterministic rules only, so no model
is called. Requires the platform's Postgres (already running) for the throwaway
per-run database.

Run: docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
         backend python tests/test_qa_offline.py
"""
import asyncio
import sys

from app.qa import assembly, level1, level2, root_cause
from app.qa.outcome import TestOutcome

_failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


def gf(ticket: str, path: str, content: str) -> dict:
    return {"id": abs(hash(path)) % 100000, "ticket_id": ticket,
            "filename": path.split("/")[-1], "filepath": path,
            "content": content, "agent_type": "backend"}


# ------------------------------------------------------------------ fixtures
VULNERABLE = '''
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
ORDERS = {1: {"item": "coffee"}, 2: {"item": "tea"}, 3: {"item": "cake"}}

class Login(BaseModel):
    email: str
    password: str

class Payment(BaseModel):
    amount: float
    note: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/admin/users")
def admin_users():
    # No authorization check at all.
    return [{"id": 1, "email": "owner@example.com", "role": "admin"}]

@app.post("/login")
def login(body: Login):
    # Accepts literally any credentials.
    return {"token": "abc123", "user": body.email}

@app.get("/orders/{order_id}")
def get_order(order_id: int):
    # No ownership check -> anyone can read any order.
    return ORDERS.get(order_id, {"item": "unknown"})

@app.post("/payments")
def pay(body: Payment):
    # Never validates the amount.
    return {"charged": body.amount}

@app.post("/search")
def search(body: dict):
    q = body.get("q", "")
    if "'" in q:
        # Leaks a raw database error straight back to the caller.
        raise RuntimeError("syntax error at or near \\'" + q + "\\'")
    return {"results": []}
'''

WELL_BUILT = '''
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI()

class Login(BaseModel):
    email: str
    password: str

class Payment(BaseModel):
    amount: float = Field(gt=0)
    note: str = Field(max_length=200)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/admin/users")
def admin_users():
    raise HTTPException(status_code=401, detail="Authentication required")

@app.post("/login")
def login(body: Login):
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/orders/{order_id}")
def get_order(order_id: int):
    raise HTTPException(status_code=401, detail="Authentication required")

@app.post("/payments")
def pay(body: Payment):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    return {"charged": body.amount}
'''

BROKEN = '''
from fastapi import FastAPI
app = FastAPI(

def oops(:
    return
'''


def names_failed(results: list[TestOutcome]) -> list[str]:
    return [r.name for r in results if not r.passed]


# ------------------------------------------------------------------ A
async def test_vulnerable():
    print("\n=== A: VULNERABLE app — QA must catch the planted bugs ===")
    env = await assembly.assemble([gf("BE-1", "backend/app/main.py", VULNERABLE)])
    try:
        check("app assembled and booted", env.ok,
              "; ".join(f.reason[:120] for f in env.failures))
        if not env.ok:
            return
        l1 = await level1.run(env)
        l2 = await level2.run(env)
        # Match case-insensitively — test names contain e.g. "SQL injection".
        failed = [f.lower() for f in names_failed(l1) + names_failed(l2)]
        blob = " | ".join(failed)

        check("L1 ran real endpoint tests", len(l1) >= 8, f"only {len(l1)}")
        check("L2 ran real attack tests", len(l2) >= 4, f"only {len(l2)}")
        check("caught unprotected admin endpoint",
              any("admin/users" in f and "without login" in f for f in failed), blob[:200])
        check("caught login accepting invalid credentials",
              any("invalid credentials" in f for f in failed), blob[:200])
        check("caught SQL error leaking to the caller",
              any("sql injection" in f for f in failed), blob[:200])
        check("caught other people's records via ID change",
              any("other people's records" in f for f in failed), blob[:200])
        check("caught negative payment amount accepted",
              any("negative amounts" in f for f in failed), blob[:200])
    finally:
        await assembly.teardown(env)
    check("temp directory removed after teardown",
          env.root is not None and not __import__("os").path.isdir(env.root))


# ------------------------------------------------------------------ B
async def test_well_built():
    print("\n=== B: WELL-BUILT app — must pass cleanly (no false positives) ===")
    env = await assembly.assemble([gf("BE-1", "backend/app/main.py", WELL_BUILT)])
    try:
        check("app assembled and booted", env.ok,
              "; ".join(f.reason[:120] for f in env.failures))
        if not env.ok:
            return
        l1 = await level1.run(env)
        l2 = await level2.run(env)
        failed = names_failed(l1) + names_failed(l2)
        check("no Level 1 false positives", not names_failed(l1), str(names_failed(l1))[:300])
        check("no Level 2 false positives", not names_failed(l2), str(names_failed(l2))[:300])
        check("a meaningful number of tests actually ran", len(l1) + len(l2) >= 12,
              f"{len(l1) + len(l2)}")
        print(f"       ({len(l1)} Level-1 + {len(l2)} Level-2 tests, {len(failed)} failed)")
    finally:
        await assembly.teardown(env)


# ------------------------------------------------------------------ C
async def test_broken_assembly():
    print("\n=== C: BROKEN app — assembly failure is a FINDING, not a crash ===")
    env = await assembly.assemble([gf("BE-1", "backend/app/main.py", BROKEN)])
    try:
        check("QA did not crash", isinstance(env, assembly.TestEnv))
        check("assembly reported not-ok", env.ok is False)
        check("syntax error captured as a finding",
              any("syntax error" in f.test_name.lower() for f in env.failures),
              str([f.test_name for f in env.failures])[:200])
        # The finding must be traceable like any other bug.
        first = env.failures[0]
        cause = root_cause._deterministic(
            TestOutcome(first.test_name, 1, False, first.reason, "app"))
        check("syntax error traced to developer_fix", cause == root_cause.DEVELOPER_FIX,
              str(cause))
    finally:
        await assembly.teardown(env)


# ------------------------------------------------------------------ D
def test_root_cause_rules():
    print("\n=== D: Level 3 root cause tracing (deterministic rules) ===")
    cases = [
        ("assembly: syntax error in backend/app/main.py", "line 3: invalid syntax", 1,
         root_cause.DEVELOPER_FIX),
        ("frontend/app/page.tsx — imports resolve",
         "imports point at files that were never generated: ./missing", 1,
         root_cause.DEVELOPER_FIX),
        ("assembly: app did not start", "failed to start within 45s", 1,
         root_cause.DEVELOPER_REWORK),
        ("GET /admin — blocks access without login", "private information returned", 2,
         root_cause.DEVELOPER_FIX),
        ("POST /pay — rejects negative amounts", "negative amount accepted", 2,
         root_cause.DEVELOPER_FIX),
    ]
    for name, reason, level, expected in cases:
        got = root_cause._deterministic(TestOutcome(name, level, False, reason, "x"))
        check(f"'{name[:42]}…' -> {expected}", got == expected, f"got {got}")

    # Routing policy: only developer-level causes are auto-sent back.
    for cause, should_auto in (
        (root_cause.DEVELOPER_FIX, True),
        (root_cause.DEVELOPER_REWORK, True),
        (root_cause.ARCHITECT_REWORK, False),
        (root_cause.BA_REWORK, False),
    ):
        o = TestOutcome("t", 1, False, "r", "x")
        o.root_cause_agent = cause
        check(f"{cause} auto-routed == {should_auto}",
              root_cause.is_auto_fixable(o) is should_auto)


# ------------------------------------------------------------------ E
async def test_scope_guard():
    print("\n=== E: attack simulation is locked to the local throwaway instance ===")
    try:
        level2._assert_local("http://example.com/api")
        check("external host refused", False, "no exception raised")
    except RuntimeError:
        check("external host refused", True)
    try:
        level2._assert_local("http://127.0.0.1:8123")
        check("loopback allowed", True)
    except RuntimeError:
        check("loopback allowed", False)


async def main():
    await test_vulnerable()
    await test_well_built()
    await test_broken_assembly()
    test_root_cause_rules()
    await test_scope_guard()

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
