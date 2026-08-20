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
        # Regression: nothing creates an app -> the BLUEPRINT is missing an
        # entrypoint. Must NOT go to the Developer (burns 3 retries on a task no
        # Developer can complete). Found during Week 6 verification.
        ("assembly: no runnable app found",
         "None of the generated backend files create a FastAPI application", 1,
         root_cause.ARCHITECT_REWORK),
        ("GET /admin — blocks access without login", "private information returned", 2,
         root_cause.DEVELOPER_FIX),
        ("POST /pay — rejects negative amounts", "negative amount accepted", 2,
         root_cause.DEVELOPER_FIX),
        # Step 3: harness faults must never be blamed on an agent.
        ("assembly: app did not start",
         "RuntimeError: Missing required authentication environment variables: "
         "AUTH0_DOMAIN. Refusing to start with an insecure auth configuration.", 1,
         root_cause.ENVIRONMENT_FAULT),
        ("assembly: could not create test database", "connection refused", 1,
         root_cause.ENVIRONMENT_FAULT),
        # Step 3: architect-level evidence must not be pattern-matched down to
        # developer_fix just because the text contains "server error".
        ("POST /api/orders — happy path",
         "Server error 500 — column orders.customer_email does not exist and is "
         "not present in the blueprint's database schema.", 1, None),
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
        (root_cause.ENVIRONMENT_FAULT, False),
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


# ================================ F: verification-session regression fixes
PARTIAL_APP = '''
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/menu")
def menu():
    return []
'''


async def test_partial_boot_is_assembly_failure():
    print("\n=== F: partially-booted app must FAIL assembly, not 'mostly pass' ===")
    # Blueprint designed 3 endpoints; the app only exposes /api/menu.
    expected = ["/api/menu", "/api/orders", "/admin/stripe/status"]
    env = await assembly.assemble(
        [gf("BE-1", "backend/app/main.py", PARTIAL_APP)], expected)
    try:
        check("assembly reported NOT ok (crippled app)", env.ok is False)
        check("missing designed endpoints reported",
              any("missing from the running app" in f.test_name for f in env.failures),
              str([f.test_name for f in env.failures])[:200])
        reason = " ".join(f.reason for f in env.failures)
        check("names the missing endpoints",
              "/api/orders" in reason and "/admin/stripe/status" in reason)
    finally:
        await assembly.teardown(env)

    # All designed endpoints present -> assembly is fine.
    env2 = await assembly.assemble(
        [gf("BE-1", "backend/app/main.py", PARTIAL_APP)], ["/api/menu"])
    try:
        check("complete app still assembles ok", env2.ok is True,
              str([f.reason[:120] for f in env2.failures]))
    finally:
        await assembly.teardown(env2)


def test_file_targeting():
    print("\n=== F: _file_for_target no longer guesses ===")
    from app.qa.orchestrator import _file_for_target
    files = [
        {"id": 1, "filepath": "backend/app/main.py", "content": "app = FastAPI()"},
        {"id": 2, "filepath": "backend/app/routers/orders.py",
         "content": '@router.post("/api/orders")\ndef create(): ...'},
        {"id": 3, "filepath": "backend/app/tiny.py", "content": "# app"},
    ]
    hit = _file_for_target("POST /api/orders", files)
    check("route maps to the file that declares it",
          hit is not None and hit["id"] == 2, str(hit))

    # Assembly-level target used to grab whichever short file contained "app".
    check("bare 'app' target with no traceback -> no guess",
          _file_for_target("app", files) is None)

    tb = 'File "/tmp/qa-build-abc/backend/app/routers/orders.py", line 10, in <module>'
    hit = _file_for_target("app", files, tb)
    check("assembly failure resolved from traceback",
          hit is not None and hit["id"] == 2, str(hit))


def test_mixed_import_styles_single_module():
    print("\n=== F: mixed import styles must NOT double-execute a module ===")
    import os
    import subprocess
    import sys
    import tempfile
    from app.qa.assembly import _python_path, _write_alias_hook

    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "backend", "app"), exist_ok=True)
    for p in ("backend/__init__.py", "backend/app/__init__.py"):
        open(os.path.join(root, p), "w").close()
    with open(os.path.join(root, "backend/app/models.py"), "w") as fh:
        fh.write("import builtins\n"
                 "builtins.__qa_exec_count = getattr(builtins,'__qa_exec_count',0)+1\n")
    _write_alias_hook(root, "backend.app.main")

    prog = ("import builtins, app.models, backend.app.models as b;"
            "print(builtins.__qa_exec_count, app.models is b)")
    r = subprocess.run([sys.executable, "-c", prog], cwd=root,
                       env={**os.environ, "PYTHONPATH": _python_path(root)},
                       capture_output=True, text=True)
    out = (r.stdout or "").strip()
    check("module executed exactly once via both import styles",
          out.startswith("1 "), out or r.stderr[-200:])
    check("both styles yield the same module object", out.endswith("True"),
          out or r.stderr[-200:])
    check("PYTHONPATH is single-rooted (no duplicate-import path)",
          _python_path(root) == root)


def test_third_party_import_gate():
    """Run 1496: the generated integrate.py wrote `from stripe.api_resources import
    PaymentIntent` — stripe IS installed but that submodule doesn't exist, so the app
    ImportErrors at boot. The venv-based gate catches a wrong third-party submodule/name
    deterministically. True positives use INSTALLED packages (the venv fallback is the
    platform python); zero false positives on real generated code."""
    import os
    import glob
    from app.qa.assembly import (_third_party_import_errors, _third_party_import_candidates,
                                  _import_error_reason)
    V = "/nonexistent-venv"     # -> _venv_python falls back to the platform python

    # True positives against installed packages: a wrong NAME and a wrong SUBMODULE.
    w = {"backend/app/routes/pay.py": "from httpx import NotARealThing\n"
                                       "from httpx import AsyncClient\n",
         "backend/app/routes/x.py": "from fastapi.totally_fake_sub import Thing\n"}
    res = _third_party_import_errors(V, w)
    kinds = {(r["module"], r["kind"]) for r in res}
    check("a wrong third-party NAME is flagged (httpx.NotARealThing)",
          ("httpx", "no_attr") in kinds, str(kinds))
    check("a wrong third-party SUBMODULE is flagged (fastapi.totally_fake_sub)",
          ("fastapi.totally_fake_sub", "no_submodule") in kinds, str(kinds))
    check("exactly the two bad imports are flagged (AsyncClient is fine)", len(res) == 2, str(res))
    check("the reason is actionable", "does not exist" in _import_error_reason(res[0])
          or "no " in _import_error_reason(res[0]))

    # In-project / stdlib / relative / star / correct imports are NEVER flagged.
    clean = {"a.py": "from fastapi import FastAPI\n"           # correct third-party
                     "from backend.app.models import Order\n"  # in-project (Fix #16's job)
                     "from app.database import get_db\n"       # in-project
                     "import os\nfrom typing import List\n"    # stdlib
                     "from .local import x\n"                  # relative
                     "from httpx import *\n"}                  # star -> unverifiable
    check("no false positives on correct/in-project/stdlib/relative/star imports",
          _third_party_import_errors(V, clean) == [], str(_third_party_import_errors(V, clean)))

    # Zero-FP across the platform's own backend + 888's real generated files.
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    plat = {("backend/" + os.path.relpath(p, os.path.join(app_dir, ".."))): open(p, encoding="utf-8").read()
            for p in glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True)}
    check(f"ZERO false positives across the platform's own {len(plat)} modules",
          _third_party_import_errors(V, plat) == [],
          str([(x["file"], x["module"]) for x in _third_party_import_errors(V, plat)][:6]))
    # NOTE: gen888 is NOT a clean corpus for THIS gate — its security.py genuinely
    # imports `from starlette.middleware.ratelimit import ...`, a module that does not
    # exist in starlette (dead code in the fixture). The gate is CORRECT to flag it, so
    # asserting zero there would be asserting the gate MISSES a real bug. The platform's
    # own 68 modules (all deps present, all imports correct) are the clean corpus; the
    # explicit correct/in-project/stdlib/relative/star cases above cover the FP classes.
    # A real submodule that only fails on a MISSING OPTIONAL DEP (starlette sessions ->
    # itsdangerous) is proven NOT flagged:
    dep_case = {"s.py": "from starlette.middleware.sessions import SessionMiddleware\n"}
    check("a real submodule failing only on a missing optional dep is NOT flagged",
          _third_party_import_errors(V, dep_case) == [], str(_third_party_import_errors(V, dep_case)))

    # The real 1496 fixture: stripe isn't installed HERE so the check skips it, but the
    # candidate extractor must still SEE the offending import (it would be caught in the
    # assembly venv where stripe is installed).
    fx = os.path.join(os.path.dirname(__file__), "fixtures", "integrate_stripe_api_resources_1496.py")
    if os.path.isfile(fx):
        cands = _third_party_import_candidates({"backend/app/routes/integrate.py": open(fx, encoding="utf-8").read()})
        hit = [c for c in cands if c["module"] == "stripe.api_resources"]
        check("the 1496 fixture's `from stripe.api_resources import ...` is a checked candidate",
              hit and "PaymentIntent" in hit[0]["names"], str(cands))


async def test_certificate_drift_detection():
    print("\n=== F: certificate detects drift from ANY source ===")
    from app.reviewer import orchestrator as ro

    # No certificate at all -> nothing to invalidate.
    check("no certificate -> nothing flagged",
          await ro.drifted_files(999999, {}) == [])
    # A certificate with no fingerprint cannot be proven to match disk, so it
    # must FAIL CLOSED (re-review), never be assumed clean.
    check("un-fingerprinted certificate fails closed (project with no files)",
          await ro.drifted_files(999999, {"passed": True}) == [])

    # Simulate: certificate recorded hashes, one file's content later changed.
    cert = {"passed": True, "file_hashes": {"1": "aaaa", "2": "bbbb"}}
    recorded = cert["file_hashes"]
    current = {"1": "aaaa", "2": "CHANGED"}
    drifted = [int(f) for f, h in current.items() if recorded.get(f) != h]
    check("changed file is detected as drifted", drifted == [2], str(drifted))
    check("unchanged file is not flagged", 1 not in drifted)
    check("hash is content-derived", ro._hash("x") != ro._hash("y"))
    check("hash is stable", ro._hash("same") == ro._hash("same"))


async def test_missing_certificate_fails_closed():
    print("\n=== F: a MISSING certificate must BLOCK, never default to certified ===")
    import json as _json

    from app.qa import orchestrator as qo

    # Redis holds the certificate and had no persistence volume, so a restart
    # could delete it while Postgres still said the project was `secured`.
    # drifted_files() correctly returns [] with no certificate (drift is
    # meaningless without a baseline), which used to flow through _recertify as
    # {} and land on `certified = True` — a build marked `tested` with no
    # security certificate at all.
    class _FakeRedis:
        def __init__(self, value):
            self.value = value

        async def get(self, key):
            return self.value

        async def set(self, *a, **k):
            return None

    calls = {"review_subset": 0}

    async def _counting_review(*a, **k):
        calls["review_subset"] += 1
        return {"passed": True, "issues_found": 0, "issues_fixed": 0,
                "files_reviewed": 0}

    real_redis = qo.redis_client
    real_review = qo.reviewer_orchestrator.review_subset
    qo.reviewer_orchestrator.review_subset = _counting_review
    try:
        # --- 1) no certificate at all (project 424242 has no generated files)
        qo.redis_client = _FakeRedis(None)
        recert = await qo._recertify(424242, {}, set())
        check("missing certificate returns a blocking result, not {}", bool(recert))
        check("missing certificate is flagged as such",
              recert.get("certificate_missing") is True)
        check("missing certificate does NOT report passed",
              recert.get("passed") is False)
        # The exact expression qo.run() uses to decide the project's fate.
        certified = bool(recert.get("passed", False)) if recert else False
        check("=> certified is FALSE (this defaulted to True before the fix)",
              certified is False)
        check("no Opus review was silently spent papering over the loss",
              calls["review_subset"] == 0, str(calls))

        # --- 2) the fix must block the MISSING case without blocking the normal
        #        one: a real, undrifted certificate still certifies.
        qo.redis_client = _FakeRedis(
            _json.dumps({"passed": True, "file_hashes": {}}))
        ok = await qo._recertify(424242, {}, set())
        check("a real undrifted certificate still certifies",
              (bool(ok.get("passed", False)) if ok else False) is True)

        # --- 3) a certificate that itself failed must not be rescued by defaults
        qo.redis_client = _FakeRedis(
            _json.dumps({"passed": False, "file_hashes": {}}))
        bad = await qo._recertify(424242, {}, set())
        check("a failed certificate stays failed",
              (bool(bad.get("passed", False)) if bad else False) is False)
    finally:
        qo.redis_client = real_redis
        qo.reviewer_orchestrator.review_subset = real_review


def test_env_autodiscovery():
    """QA supplies throwaway values for env vars the generated code fail-fast
    requires — a real baseline booted-failed on STRIPE_STATE_SECRET, which the
    code correctly required but _TEST_ENV didn't supply. Only NO-DEFAULT reads
    are filled, and never a var _TEST_ENV already curates."""
    print("\n=== F: QA auto-discovers required env vars from generated code ===")
    from app.qa import assembly

    files = [{
        "filepath": "backend/app/routes/stripe.py",
        "content": (
            "import os\n"
            "STATE = os.environ.get('STRIPE_STATE_SECRET')\n"
            "if not STATE: raise RuntimeError('STRIPE_STATE_SECRET not set')\n"
            "REDIRECT = os.getenv('STRIPE_REDIRECT_URI')\n"
            "KEY = os.environ['STRIPE_SECRET_KEY']\n"           # curated in _TEST_ENV
            "MODE = os.getenv('APP_MODE', 'prod')\n"            # HAS a default
            # project 606: a module-level Fernet cipher — the QA value MUST be a
            # valid Fernet key or a correct app crashes at import. This var name is
            # NOT curated in _TEST_ENV, so it exercises the discovery path.
            "ENC = os.environ['APP_TOKEN_ENC_KEY']\n"
        ),
    }, {
        "filepath": "frontend/app/page.tsx",              # non-python: ignored
        "content": "const x = process.env.SHOULD_BE_IGNORED",
    }]
    found = assembly._discover_required_env(files)

    check("the exact var that broke project 332 is discovered",
          "STRIPE_STATE_SECRET" in found)
    check("a bare os.getenv (no default) is discovered",
          "STRIPE_REDIRECT_URI" in found)
    check("a var _TEST_ENV already curates is NOT overridden",
          "STRIPE_SECRET_KEY" not in found)
    check("a var WITH an explicit default is left alone (not clobbered)",
          "APP_MODE" not in found, str(found))
    check("non-Python files are not scanned for env vars",
          "SHOULD_BE_IGNORED" not in found)
    check("URL-shaped vars get a loopback URL, others a placeholder",
          found.get("STRIPE_REDIRECT_URI", "").startswith("http://127.0.0.1")
          and found.get("STRIPE_STATE_SECRET") == "qa-test-stripe_state_secret",
          str(found))
    # project 606 regression: an encryption-key env var must be a VALID Fernet key,
    # or a correct app that builds `Fernet(KEY.encode())` at import crashes under QA
    # with "Fernet key must be 32 url-safe base64-encoded bytes" (a QA-env fault).
    from cryptography.fernet import Fernet

    def _valid_fernet(k: str) -> bool:
        try:
            Fernet((k or "").encode())
            return True
        except Exception:
            return False

    check("a discovered *_ENC_KEY env var is filled", "APP_TOKEN_ENC_KEY" in found)
    check("the DISCOVERED *_ENC_KEY value is a VALID Fernet key",
          _valid_fernet(found.get("APP_TOKEN_ENC_KEY")), found.get("APP_TOKEN_ENC_KEY"))
    check("the CURATED STRIPE_TOKEN_ENC_KEY is a VALID Fernet key (project 606 fix)",
          _valid_fernet(assembly._TEST_ENV.get("STRIPE_TOKEN_ENC_KEY")),
          assembly._TEST_ENV.get("STRIPE_TOKEN_ENC_KEY"))
    check("every supplied value is obviously fake (loopback/placeholder/throwaway key)",
          all(v.startswith(("qa-test-", "http://127.0.0.1"))
              or v == assembly._FAKE_FERNET_KEY for v in found.values()))

    # project 773: the entrypoint reads ALLOWED_ORIGINS WITH a default ('') then
    # fail-fasts if empty. Discovery skips defaulted vars, so it MUST be curated with
    # a value that survives `os.getenv('ALLOWED_ORIGINS','').split(',')` being non-empty.
    _ao = assembly._TEST_ENV.get("ALLOWED_ORIGINS", "")
    check("ALLOWED_ORIGINS is curated with a non-empty origin list (project 773)",
          bool(_ao) and _ao.split(",")[0].strip() != "", repr(_ao))


async def test_frontend_checks_not_gated_on_backend_boot():
    """Frontend buildability has nothing to do with whether the backend starts.

    Both were chained to one condition: _full_frontend_build lived inside
    level1.run(), which _run_round calls only `if env.ok`. On project 201 the
    backend failed to boot, so the frontend got ZERO coverage and Step 5's whole
    question went unanswered — silently, because a test that never runs reports
    nothing at all.
    """
    print("\n=== F: frontend checks run even when the backend never booted ===")
    from app.config import settings
    from app.qa import level1
    from app.qa.assembly import TestEnv

    prev = settings.qa_frontend_full_build
    settings.qa_frontend_full_build = True
    try:
        # Interface files exist, backend did NOT boot.
        env = TestEnv()
        env.ok = False
        env.files = {"frontend/app/page.tsx":
                     "export default function P(){ return null }"}
        out = await level1.run_static(env)
        names = [o.name for o in out]
        check("run_static yields outcomes on a build that never booted",
              bool(out), str(names))
        build = [o for o in out if o.name.startswith("frontend — build")]
        check("the frontend build is REPORTED, never silently skipped",
              bool(build), str(names))
        check("interface files with nowhere to build them is a FAILURE",
              bool(build) and build[0].passed is False,
              str([(o.name, o.passed) for o in build]))

        # A backend-only build genuinely has no interface — say so explicitly.
        env2 = TestEnv()
        env2.ok = False
        env2.files = {"backend/app/main.py": "app = 1"}
        out2 = await level1.run_static(env2)
        names2 = [o.name for o in out2]
        check("a build with no interface says 'not applicable' (never [])",
              any("not applicable" in n for n in names2), str(names2))
        check("...and that is recorded as PASSING, not as a failure",
              all(o.passed for o in out2 if o.name.startswith("frontend — build")),
              str([(o.name, o.passed) for o in out2]))
    finally:
        settings.qa_frontend_full_build = prev


async def test_frontend_truncation_caught_statically():
    """Regression (project 1007): the generated admin/menu/review/page.tsx was
    truncated mid-JSX. It passed QA (whose real `next build` is opt-in and OFF) and
    only died four stages later at the deploy's `next build`. QA's ALWAYS-ON static
    check must now FAIL a truncated/invalid interface file — no Node required."""
    print("\n=== G: a truncated frontend file FAILS QA statically (project 1007) ===")
    import os
    from app.qa import level1
    from app.qa.assembly import TestEnv

    fx = os.path.join(os.path.dirname(__file__), "fixtures", "truncated_review_page_1007.tsx")
    truncated = open(fx, encoding="utf-8").read()
    env = TestEnv()
    env.ok = True
    env.files = {
        "frontend/app/admin/menu/review/page.tsx": truncated,               # 1007's cut-off file
        "frontend/app/page.tsx": "export default function P(){ return <div/>; }",  # complete
    }
    out = await level1.run_static(env)   # qa_frontend_full_build stays OFF (default)
    parse = [o for o in out if "complete & parseable" in o.name]
    trunc = [o for o in parse if "review/page.tsx" in o.name]
    good = [o for o in parse if "app/page.tsx" in o.name and "review" not in o.name]
    check("the truncated review page FAILS the static parse check (no next build needed)",
          bool(trunc) and trunc[0].passed is False, str([(o.name, o.passed) for o in parse]))
    check("a complete page PASSES the parse check",
          bool(good) and good[0].passed is True, str([(o.name, o.passed) for o in parse]))


def test_env_provides_provider_config():
    print("\n=== F: test env supplies provider config (no false 'bug') ===")
    for key in ("AUTH0_DOMAIN", "AUTH0_API_AUDIENCE", "STRIPE_CLIENT_ID",
                "STRIPE_TOKEN_ENC_KEY"):
        check(f"{key} provided to the app under test", key in assembly._TEST_ENV)


def test_entrypoint_ticket_forbids_workarounds():
    print("\n=== F: entrypoint ticket forbids silent skips + fake secrets ===")
    from app.architect import builder
    desc = builder._entrypoint_ticket(["FND-1"])["description"]
    check("forbids hiding import errors", "DO NOT hide import errors" in desc)
    check("forbids inventing env vars", "DO NOT set, default, mock or invent" in desc)
    check("forbids wildcard CORS with credentials", 'allow_origins=["*"]' in desc)


async def main():
    await test_vulnerable()
    await test_well_built()
    await test_broken_assembly()
    test_root_cause_rules()
    await test_scope_guard()
    await test_partial_boot_is_assembly_failure()
    test_file_targeting()
    test_mixed_import_styles_single_module()
    test_third_party_import_gate()
    await test_certificate_drift_detection()
    await test_missing_certificate_fails_closed()
    test_env_autodiscovery()
    await test_frontend_checks_not_gated_on_backend_boot()
    await test_frontend_truncation_caught_statically()
    test_env_provides_provider_config()
    test_entrypoint_ticket_forbids_workarounds()

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
