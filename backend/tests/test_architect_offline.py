"""Offline Architect gating + Stripe-Connect + delegated-auth test.

Runs with ZERO LLM spend: it monkeypatches app.llm.complete_json to return None,
forcing the Architect's deterministic _mock_creative path. All of this session's
changes live in the Architect's deterministic logic (+ a reviewer helper), so
this exercises exactly what changed and re-checks the pre-existing gating
invariants (Opus-always security, foundation-first, mobile/third-party detection,
cloud tiering) at the Architect layer.

Run:  docker compose run --rm --no-deps -v "$PWD/backend:/app" backend \
          python tests/test_architect_offline.py
"""
import asyncio
import sys

import app.llm as llm_mod


# --- force the free, deterministic path (no network, no cost) ---------------
async def _no_llm(*args, **kwargs):
    return None


llm_mod.complete_json = _no_llm  # every _generate_creative call -> mock creative

from app.architect import builder  # noqa: E402  (import after the patch)
from app.reviewer import reviewer  # noqa: E402


# ---------------------------------------------------------------- tiny harness
_failures: list[str] = []


def check(label: str, cond: bool) -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}")
    if not cond:
        _failures.append(label)


def tickets_by_id(bp: dict) -> dict:
    return {t.get("id"): t for t in bp.get("sprint_tickets", [])}


def table_names(bp: dict) -> set:
    return {t.get("table") for t in bp.get("database_schema", [])}


def endpoint_paths(bp: dict) -> set:
    return {e.get("path") for e in bp.get("api_endpoints", [])}


def measures_text(bp: dict) -> str:
    return " ".join(bp.get("security", {}).get("measures", [])).lower()


# ---------------------------------------------------------------- summaries
def summary(**over) -> dict:
    base = {
        "build": "an app",
        "audience": "customers",
        "budget": "$50",
        "user_count": "a few hundred",
        "plan": {"id": "production", "name": "Production ready"},
        "customer_facing": True,
        "mobile_choice": "web",
        "priorities": {"must_have": [], "nice_to_have": []},
        "competitor_features": [],
        "missing_essentials": [],
    }
    base.update(over)
    return base


# ============================================================ TEST 1: payments
async def test_payment_domain():
    print("\n=== TEST 1: payment domain (coffee shop, online ordering + tips) ===")
    bp = await builder.build_blueprint(summary(
        build="a coffee shop with online ordering and the option to leave a tip",
        priorities={"must_have": ["let customers pay online", "tipping at checkout"],
                    "nice_to_have": ["email order confirmations"]},
    ))
    tp = bp["third_party_apis"]
    tk = tickets_by_id(bp)

    # Stripe Connect (not plain Stripe), user-handled, in-app OAuth.
    stripe = next((a for a in tp if "stripe" in a["name"].lower()), None)
    check("Stripe Connect present in third_party_apis", stripe is not None)
    check("named 'Stripe Connect' (not plain 'Stripe')",
          bool(stripe) and stripe["name"] == "Stripe Connect")
    check("who_handles == user", bool(stripe) and stripe.get("who_handles") == "user")
    check("connection == in_app_oauth (not platform-mediated)",
          bool(stripe) and stripe.get("connection") == "in_app_oauth")
    check("no old setup step asks the user to paste a secret key into the platform",
          bool(stripe) and not any("paste" in s.lower() and "key" in s.lower()
                                   for s in stripe.get("setup_steps", [])))

    # Backend + frontend payment tickets exist and are flagged.
    check("PAY-1 backend ticket exists", "PAY-1" in tk and tk["PAY-1"]["assigned_to"] == "backend")
    check("PAY-2 frontend ticket exists", "PAY-2" in tk and tk["PAY-2"]["assigned_to"] == "frontend")
    check("PAY-1 flagged security_critical", tk.get("PAY-1", {}).get("security_critical") is True)
    check("PAY-2 flagged security_critical", tk.get("PAY-2", {}).get("security_critical") is True)
    pay2 = tk.get("PAY-2", {}).get("description", "")
    check("PAY-2 says payment UI VISIBLE but DISABLED", "DISABLED" in pay2)
    check("PAY-2 has the exact 'Connect Stripe to start accepting payments' copy",
          "Connect Stripe to start accepting payments" in pay2)
    p1 = tk.get("PAY-1", {}).get("description", "")
    check("PAY-1 mandates ENCRYPTED token storage", "ENCRYPTED" in p1)
    check("PAY-1 forbids the platform touching the credential",
          "platform" in p1.lower())

    # Encrypted-token table + OAuth endpoints frozen into the contract.
    check("stripe_accounts table added to schema", "stripe_accounts" in table_names(bp))
    cols = {c["name"] for t in bp["database_schema"] if t["table"] == "stripe_accounts"
            for c in t["columns"]}
    check("stripe_accounts has access_token_encrypted column", "access_token_encrypted" in cols)
    check("no plaintext 'access_token' column", "access_token" not in cols)
    eps = endpoint_paths(bp)
    check("OAuth connect endpoint present", "/admin/stripe/connect" in eps)
    check("OAuth callback endpoint present", "/admin/stripe/callback" in eps)
    check("connect status endpoint present (drives disabled UI)", "/admin/stripe/status" in eps)

    # Security section flags the payment feature for the Opus review.
    ps = bp["security"].get("payment_security")
    check("security.payment_security present", ps is not None)
    check("payment feature flagged_for_security_review", bool(ps) and ps.get("flagged_for_security_review") is True)
    check("payment must_verify lists encrypted-token check",
          bool(ps) and any("encrypt" in m.lower() for m in ps.get("must_verify", [])))

    # Stripe is NOT double-handled by a generic integration ticket.
    int_tickets = [t for t in bp["sprint_tickets"] if t.get("assigned_to") == "integration"]
    check("no integration ticket mentions Stripe (PAY-* owns it)",
          all("stripe" not in t.get("title", "").lower() for t in int_tickets))

    # Auth: payments present -> MFA required.
    auth = bp["security"]["auth"]
    check("auth.mfa_required True (payments present)", auth["mfa_required"] is True)
    check("auth.triggers.payments True", auth["triggers"]["payments"] is True)

    # Platform never builds a Stripe connection: nothing marks Stripe who_handles=platform.
    check("no third-party Stripe entry is platform-handled",
          all(not ("stripe" in a["name"].lower() and a.get("who_handles") == "platform")
              for a in tp))


# ======================================================= TEST 2: no payments
async def test_non_payment_domain():
    print("\n=== TEST 2: non-payment domain (personal recipe box, just me) ===")
    bp = await builder.build_blueprint(summary(
        build="a personal recipe box just for me to save and organise my recipes",
        audience="just me",
        budget="$15",
        user_count="1",
        plan={"id": "quick", "name": "Quick launch"},
        customer_facing=False,
        priorities={"must_have": ["save recipes", "search by ingredient"],
                    "nice_to_have": []},
    ))
    tp = bp["third_party_apis"]
    tk = tickets_by_id(bp)

    check("no Stripe in third_party_apis", all("stripe" not in a["name"].lower() for a in tp))
    check("no PAY-1 ticket", "PAY-1" not in tk)
    check("no PAY-2 ticket", "PAY-2" not in tk)
    check("no stripe_accounts table", "stripe_accounts" not in table_names(bp))
    check("no stripe OAuth endpoints",
          not any("/admin/stripe" in p for p in endpoint_paths(bp)))
    check("no payment_security block", "payment_security" not in bp["security"])

    auth = bp["security"]["auth"]
    check("auth tier == basic", auth["tier"] == "basic")
    check("auth.mfa_required False", auth["mfa_required"] is False)
    check("passkeys 'offered' (not scale default)", auth["passkeys"] == "offered")
    check("AUTH-1 delegated-auth ticket still present", "AUTH-1" in tk)

    # Nothing broke: all sections still present + secure-by-default.
    for key in ("tech_stack", "database_schema", "api_endpoints", "third_party_apis",
                "sprint_tickets", "security", "llm_routing", "cloud_config"):
        check(f"blueprint has '{key}'", key in bp)
    check("security review model is Opus", bp["security"]["review_model"] == "claude-opus-4-8")
    check("no custom-auth (bcrypt) in security measures", "bcrypt" not in measures_text(bp))


# ============================================ TEST 3: 8-scenario gating suite
async def test_gating_suite():
    print("\n=== TEST 3: 8-scenario gating invariants (BA/PI/Architect chain, Architect layer) ===")
    scenarios = [
        ("B2B SaaS w/ subscription billing",
         summary(build="a B2B SaaS dashboard with monthly subscription billing",
                 audience="business teams", plan={"id": "scale", "name": "Scale ready"},
                 user_count="50,000"), {"payments": True, "mobile": False}),
        ("Internal staff scheduling tool",
         summary(build="an internal tool for managers to schedule employee shifts",
                 audience="just my staff", customer_facing=False), {"payments": False, "mobile": False}),
        ("Telehealth (patient health data)",
         summary(build="a telehealth app where patients book medical consultations",
                 audience="patients"), {"payments": False, "mobile": False, "mfa": True}),
        ("Native mobile app",
         summary(build="a native iPhone app for tracking workouts",
                 mobile_choice="native"), {"payments": False, "mobile": True}),
        ("Tipping app (implied payment)",
         summary(build="an app that lets fans leave a tip for street performers"),
         {"payments": True, "mobile": False}),
        ("Budget mismatch (scale plan, tiny budget)",
         summary(build="a marketplace", plan={"id": "scale", "name": "Scale ready"},
                 budget="$10", audience="just me", user_count="5"),
         {"payments": False, "mobile": False}),
        ("Personal single-user tool",
         summary(build="a personal habit tracker for myself", audience="just me",
                 customer_facing=False, plan={"id": "quick", "name": "Quick launch"}),
         {"payments": False, "mobile": False}),
        ("Public newsletter site",
         summary(build="a public newsletter website with a signup form"),
         {"payments": False, "mobile": False}),
    ]

    for name, s, expect in scenarios:
        print(f"\n  -- {name} --")
        bp = await builder.build_blueprint(s)
        tk = tickets_by_id(bp)

        # Invariant: all sections present.
        check("all blueprint sections present",
              all(k in bp for k in ("tech_stack", "database_schema", "api_endpoints",
                                    "third_party_apis", "sprint_tickets", "security",
                                    "llm_routing", "cloud_config")))
        # Invariant: security ALWAYS Opus (core rule).
        check("security review == claude-opus-4-8",
              bp["security"]["review_model"] == "claude-opus-4-8"
              and bp["llm_routing"]["security_review"] == "claude-opus-4-8")
        # Invariant: foundation-first.
        ids = [t.get("id") for t in bp["sprint_tickets"]]
        check("foundation tickets first (FND-1, FND-2)", ids[:2] == ["FND-1", "FND-2"])
        # project 801: models.py must import the shared Base from the database
        # module, never call declarative_base() itself — a second Base leaves models
        # unregistered, so create_all makes no tables and every query 500s.
        fnd1_desc = tk.get("FND-1", {}).get("description", "")
        check("FND-1 pins importing the shared Base from the database module",
              "from backend.app.database import Base" in fnd1_desc
              and "do not call declarative_base()" in fnd1_desc.lower())
        # Invariant: delegated auth on every build, no custom hashing.
        check("exactly one AUTH-1 ticket", ids.count("AUTH-1") == 1)
        # Invariant: every build MUST commission an application entrypoint, and
        # it must run LAST so it can register the routers. (Week 6 verification
        # found real blueprints with five routers and no app to mount them on.)
        check("exactly one APP-1 entrypoint ticket", ids.count("APP-1") == 1)
        check("entrypoint ticket is last", ids[-1] == "APP-1")
        app_t = tk.get("APP-1", {})
        check("entrypoint depends on all other tickets",
              len(app_t.get("dependencies", [])) == len(ids) - 1)
        check("entrypoint asks for the FastAPI app + routers",
              "FastAPI" in app_t.get("description", "")
              and "include_router" in app_t.get("description", ""))
        # project 773: pin the EXACT CORS origins env var name so QA can supply it
        # (the Opus review hardens CORS to read from env and fail-fast if empty).
        check("entrypoint pins the ALLOWED_ORIGINS env var name",
              "ALLOWED_ORIGINS" in app_t.get("description", ""))
        check("no bcrypt/custom-auth in measures", "bcrypt" not in measures_text(bp))
        check("auth measure mentions delegated provider",
              "delegate" in measures_text(bp) and "auth0" in measures_text(bp))
        # Invariant: cloud tier valid.
        check("cloud tier valid", bp["cloud_config"]["tier"] in ("small", "medium", "large"))

        # Payment expectation.
        has_stripe = any("stripe" in a["name"].lower() for a in bp["third_party_apis"])
        check(f"payments detected == {expect['payments']}", has_stripe == expect["payments"])
        if expect["payments"]:
            check("PAY-1 & PAY-2 present", "PAY-1" in tk and "PAY-2" in tk)
            check("stripe_accounts table present", "stripe_accounts" in table_names(bp))
            check("payment flagged for security review",
                  bp["security"].get("payment_security", {}).get("flagged_for_security_review") is True)
        else:
            check("no PAY tickets", "PAY-1" not in tk and "PAY-2" not in tk)
            check("no stripe_accounts table", "stripe_accounts" not in table_names(bp))

        # Mobile expectation.
        has_mobile = any(t.get("assigned_to") == "mobile" for t in bp["sprint_tickets"])
        check(f"mobile tickets == {expect['mobile']}", has_mobile == expect["mobile"])

        # Explicit MFA expectation where given.
        if expect.get("mfa"):
            check("MFA required (sensitive data)", bp["security"]["auth"]["mfa_required"] is True)


# ======================================== TEST 4: reviewer payment flag helper
def test_reviewer_flag():
    print("\n=== TEST 4: Code Reviewer payment-sensitivity flag ===")
    check("PAY-1 ticket file flagged",
          reviewer._is_payment_sensitive({"ticket_id": "PAY-1", "filepath": "backend/app/x.py"}))
    check("stripe filepath flagged",
          reviewer._is_payment_sensitive({"ticket_id": "BE-9", "filepath": "backend/app/stripe_connect.py"}))
    check("oauth filepath flagged",
          reviewer._is_payment_sensitive({"ticket_id": "BE-9", "filepath": "backend/app/oauth_handler.py"}))
    check("ordinary file NOT flagged",
          not reviewer._is_payment_sensitive({"ticket_id": "BE-2", "filepath": "backend/app/orders.py"}))
    check("focus text mentions encrypted token + no leakage",
          "encrypt" in reviewer._PAYMENT_SECURITY_FOCUS.lower()
          and "leakage" in reviewer._PAYMENT_SECURITY_FOCUS.lower())


async def test_unique_filepaths():
    """Two tickets writing the same file silently destroyed one ticket's work.

    Real failure it caused: project 201 would not boot
    (ImportError: cannot import name 'OrderItem'), and of 16 generated files
    only ~13 distinct paths survived — THREE tickets wrote backend/app/main.py
    and TWO wrote backend/app/routes/orders.py.
    """
    print("\n=== TEST 5: every ticket owns a UNIQUE output filepath ===")
    from app.architect import builder

    bp = await builder.build_blueprint(summary(build="a coffee shop with online "
                                                     "ordering, card payments and tips"))
    tickets = bp["sprint_tickets"]
    paths = [t.get("filepath") for t in tickets]

    check("every ticket has a filepath", all(paths))
    check("no ticket shares a filepath with another",
          len(set(paths)) == len(paths))
    if len(set(paths)) != len(paths):
        dupes = {p for p in paths if paths.count(p) > 1}
        print(f"      DUPLICATES: {dupes}")
    check("APP-1 owns backend/app/main.py",
          tickets_by_id(bp)["APP-1"].get("filepath") == "backend/app/main.py")
    check("FND-1 owns backend/app/models.py",
          tickets_by_id(bp)["FND-1"].get("filepath") == "backend/app/models.py")

    # The frontend manifest — without it `next build` cannot start at all.
    tk = tickets_by_id(bp)
    check("FND-3 frontend manifest ticket exists", "FND-3" in tk)
    check("FND-3 owns frontend/package.json",
          tk.get("FND-3", {}).get("filepath") == "frontend/package.json")
    check("FND-3 runs in the FIRST wave (FND- prefix, no dependencies)",
          tk.get("FND-3", {}).get("dependencies") == [])
    check("FND-3 demands real npm packages only",
          "genuinely exist" in tk.get("FND-3", {}).get("description", ""))

    # The root layout — Next.js App Router refuses to build any page without it.
    check("FND-4 root layout ticket exists", "FND-4" in tk)
    check("FND-4 owns frontend/app/layout.tsx",
          tk.get("FND-4", {}).get("filepath") == "frontend/app/layout.tsx")
    check("FND-4 runs in the FIRST wave (FND- prefix, no dependencies)",
          tk.get("FND-4", {}).get("dependencies") == [])
    fnd4 = tk.get("FND-4", {}).get("description", "")
    check("FND-4 mandates the <html> and <body> tags a root layout needs",
          "<html" in fnd4 and "<body>" in fnd4)
    check("FND-4 keeps the layout server-only (no 'use client')",
          "use client" in fnd4)  # phrased as a prohibition

    # The global stylesheet — the layout imports it by convention, so it must
    # exist or `next build` fails on an unresolved module.
    check("FND-5 global stylesheet ticket exists", "FND-5" in tk)
    check("FND-5 owns frontend/app/globals.css",
          tk.get("FND-5", {}).get("filepath") == "frontend/app/globals.css")
    check("FND-5 runs in the FIRST wave (FND- prefix, no dependencies)",
          tk.get("FND-5", {}).get("dependencies") == [])
    check("FND-5 forbids @tailwind directives without a config (plain CSS)",
          "@tailwind" in tk.get("FND-5", {}).get("description", ""))

    # The entrypoint must be flagged so the Developer injects the real router
    # module paths — guessing conventional names is what broke a real build.
    check("APP-1 is flagged is_entrypoint",
          tk.get("APP-1", {}).get("is_entrypoint") is True)

    # CONVENTIONAL names: modules sit where the model's imports point, instead of
    # title-slugs it can't guess. A real build failed on `No module named
    # 'backend.app.auth'` because auth had a slug name.
    check("AUTH-1 is at the conventional backend/app/auth.py",
          tk.get("AUTH-1", {}).get("filepath") == "backend/app/auth.py")
    check("AUTH-1 exposes the standard get_current_admin_user dependency",
          "get_current_admin_user" in tk.get("AUTH-1", {}).get("description", ""))
    check("SEC-1 is at the conventional backend/app/security.py",
          tk.get("SEC-1", {}).get("filepath") == "backend/app/security.py")
    # Creative endpoint tickets get short conventional stems, not full-title slugs.
    be_paths = [t.get("filepath", "") for t in bp["sprint_tickets"]
                if str(t.get("id", "")).startswith(("BE-", "PAY-"))
                and (t.get("filepath") or "").endswith(".py")]
    if not all("implement_" not in p and "create_" not in p for p in be_paths):
        print(f"      slug-prefixed paths: {be_paths}")
    check("no backend route file keeps the 'implement_/create_' title-slug prefix",
          all("implement_" not in p and "create_" not in p for p in be_paths))

    # Direct test of the collision resolver, independent of any blueprint.
    collided = builder._assign_filepaths([
        {"id": "BE-1", "assigned_to": "backend",
         "description": "Create backend/app/routes/orders.py"},
        {"id": "BE-2", "assigned_to": "backend",
         "description": "Also create backend/app/routes/orders.py"},
        {"id": "FE-1", "assigned_to": "frontend",
         "description": "Create frontend/app/page.tsx"},
        {"id": "FE-2", "assigned_to": "frontend",
         "description": "Also create frontend/app/page.tsx"},
    ])
    out = [t["filepath"] for t in collided]
    print(f"      resolved: {out}")
    check("colliding backend tickets get distinct paths", out[0] != out[1])
    check("the first ticket keeps the original path",
          out[0] == "backend/app/routes/orders.py")
    check("a colliding page.tsx MOVES DIRECTORY (renaming would break routing)",
          out[3].endswith("/page.tsx") and out[3] != out[2],
          )
    check("all four resolved paths are unique", len(set(out)) == 4)


def test_entrypoint_gets_real_router_paths():
    """The entrypoint imports routers by their REAL module paths, not guesses.

    A real baseline build booted-failed on `No module named
    'backend.app.routes.menu'`: main.py imported the conventional name while the
    generated file was `routes/implement_menu_retrieval_endpoint.py` (a
    consequence of the unique-filepath slug naming). The Developer now injects
    the exact module paths of the files that actually define an APIRouter.
    """
    print("\n=== TEST 7: entrypoint is handed the REAL router module paths ===")
    from app.developers import agents

    # Slug-named routers + non-routers, exactly the project-252 shape.
    existing = [
        {"filepath": "backend/app/models.py", "content": "class Order: pass"},
        {"filepath": "backend/app/database.py", "content": "engine = None"},
        {"filepath": "backend/app/routes/implement_menu_retrieval_endpoint.py",
         "content": "from fastapi import APIRouter\nrouter = APIRouter()"},
        {"filepath": "backend/app/routes/implement_order_creation_endpoint.py",
         "content": "router = APIRouter(prefix='/orders')"},
        {"filepath": "backend/app/routes/set_up_fastapi_project_structure.py",
         "content": "SETTINGS = {}"},                         # no router
        {"filepath": "backend/app/integrations/notify.py",
         "content": "def send(): ..."},                       # no router
    ]

    mods = dict(agents._router_modules(existing))
    check("only APIRouter files detected (2 of 6)", len(mods) == 2)
    check("menu router detected at its REAL slug path",
          "backend.app.routes.implement_menu_retrieval_endpoint" in mods)
    check("orders router detected at its REAL slug path",
          "backend.app.routes.implement_order_creation_endpoint" in mods)
    check("models.py (no router) excluded",
          "backend.app.models" not in mods)
    check("scaffolding (no router) excluded",
          "backend.app.routes.set_up_fastapi_project_structure" not in mods)

    entry = {"id": "APP-1", "is_entrypoint": True, "title": "entrypoint",
             "description": "build main.py", "filepath": "backend/app/main.py"}
    prompt = agents._base_prompt(entry, existing, "")
    block = prompt.split("REGISTER EXACTLY", 1)[-1] if "REGISTER EXACTLY" in prompt else ""
    check("entrypoint prompt enumerates the routers", bool(block))
    check("prompt carries the EXACT menu module path",
          "backend.app.routes.implement_menu_retrieval_endpoint" in block)
    check("prompt does NOT suggest a conventional 'routes.menu' name",
          "routes.menu " not in block and "routes.menu\n" not in block)
    check("a non-entrypoint ticket gets NO router block",
          "REGISTER EXACTLY" not in agents._base_prompt(
              {"id": "BE-1", "title": "x", "description": "y"}, existing, ""))


def test_conventional_stem():
    print("\n=== TEST 7b: title -> conventional module stem ===")
    from app.architect import builder as b
    cases = {
        "Implement menu retrieval endpoint": "menu",
        "Implement order creation endpoint": "order",
        "Stripe Connect OAuth handler + encrypted tokens": "stripe",
        "Build core API endpoints": "api",       # 'build','core' are filler
    }
    for title, expected in cases.items():
        got = b._conventional_stem(title, "BE-9")
        check(f"{title!r} -> {expected!r}", got == expected)
    check("empty title falls back to a slug of the ticket id",
          b._conventional_stem("", "BE-9") == "be_9")


def test_contract_declares_exact_module_paths():
    """The binding contract lists every module at its EXACT import path.

    A real build booted-failed on `No module named
    'backend.app.integrations.stripe'`: a router imported that conventional path
    while the generated file was the slug
    `integrations/integrate_stripe_connect_for_payments.py`. The old contract
    only described the layout generically ("integrations/ -> wrappers"), leaving
    the path to a guess. It now declares each generated module's exact dotted
    path, closing the whole cross-file import-mismatch family at the root.
    """
    print("\n=== TEST 8: contract declares every module's EXACT path ===")
    from app.developers.orchestrator import _contract_text

    # A slug-named integration + router, exactly the shape that failed.
    bp = {
        "database_schema": [], "api_endpoints": [],
        "sprint_tickets": [
            {"id": "FND-1", "assigned_to": "backend", "title": "models",
             "filepath": "backend/app/models.py"},
            {"id": "INT-1", "assigned_to": "integration", "title": "Stripe wrapper",
             "filepath": "backend/app/integrations/integrate_stripe_connect_for_payments.py"},
            {"id": "PAY-1", "assigned_to": "backend", "title": "Stripe router",
             "filepath": "backend/app/routes/stripe_connect_oauth_handler.py"},
            {"id": "FE-1", "assigned_to": "frontend", "title": "menu page",
             "filepath": "frontend/app/menu/page.tsx"},
        ],
    }
    c = _contract_text(bp)
    check("declares the EXACT slug integration module path",
          "backend.app.integrations.integrate_stripe_connect_for_payments" in c)
    check("declares the router module by its dotted path",
          "backend.app.routes.stripe_connect_oauth_handler" in c)
    check("lists frontend files too", "frontend/app/menu/page.tsx" in c)
    check("explicitly forbids inventing a path not in the map",
          "NEVER import a module path that is not in the map" in c)
    check("names the exact wrong-guess it must avoid",
          "backend.app.integrations.stripe" in c)  # cited as a DON'T
    check("tells the agent to inline rather than import a missing module",
          "implement it INLINE" in c)
    check("dropped the old generic 'wrappers' layout line",
          "third-party service wrappers" not in c)


def test_developer_pins_assigned_path():
    print("\n=== TEST 6: the Developer is PINNED to the assigned filepath ===")
    from app.developers import agents

    ticket = {"id": "BE-9", "filepath": "backend/app/routes/orders.py",
              "assigned_to": "backend"}
    # The model ignored the instruction and picked another ticket's file.
    rogue = {"filename": "main.py", "filepath": "backend/app/main.py",
             "content": "x = 1"}
    pinned = agents._pin_path(rogue, ticket)
    check("a rogue filepath is overridden with the assigned one",
          pinned["filepath"] == "backend/app/routes/orders.py")
    check("filename is derived from the assigned path",
          pinned["filename"] == "orders.py")
    check("content is untouched", pinned["content"] == "x = 1")
    check("a ticket with no assigned path leaves the file alone",
          agents._pin_path(rogue, {"id": "X"})["filepath"] == "backend/app/main.py")
    check("the prompt states the required path",
          "backend/app/routes/orders.py" in agents._base_prompt(ticket, [], ""))


def test_homepage_helpers():
    """FIX #22 unit layer (deploy gap #4): the route helper + the FND-6 ticket builder."""
    print("\n=== TEST 7a: homepage helpers (route derivation + ticket) ===")
    tickets = [
        {"id": "FND-4", "filepath": "frontend/app/layout.tsx"},     # not a page
        {"id": "FND-5", "filepath": "frontend/app/globals.css"},    # not a page
        {"id": "FE-1", "filepath": "frontend/app/menu/page.tsx"},
        {"id": "MENU-2", "filepath": "frontend/app/admin/menu/page.tsx"},
        {"id": "FND-6", "filepath": "frontend/app/page.tsx"},        # the ROOT page (excluded)
    ]
    routes = builder._frontend_page_routes(tickets)
    check("routes are derived from */page.tsx, root EXCLUDED, layout/css ignored",
          routes == ["/menu", "/admin/menu"], )
    check("_has_root_homepage detects an existing root page",
          builder._has_root_homepage(tickets) is True)
    check("_has_root_homepage is False when no root page exists",
          builder._has_root_homepage(tickets[:-1]) is False)

    t = builder._frontend_homepage_ticket(["/menu", "/admin/menu"], "Bella Vista")
    check("homepage ticket is FND-6, frontend, pinned to frontend/app/page.tsx, no deps",
          t["id"] == "FND-6" and t["assigned_to"] == "frontend"
          and t["filepath"] == "frontend/app/page.tsx" and t["dependencies"] == [])
    check("homepage names the business + lists the exact routes + is server-only",
          "Bella Vista" in t["description"] and "`/menu`" in t["description"]
          and "`/admin/menu`" in t["description"] and 'do NOT add "use client"' in t["description"])
    # No routes / no business name -> still a real welcome page, no invented links.
    t0 = builder._frontend_homepage_ticket([], None)
    check("with no routes: a clean welcome, no nav links invented",
          "no nav links are needed" in t0["description"] and "this app" in t0["description"])


async def test_generated_homepage():
    """FIX #22 (deploy gap #4): run 1105's deployed app 404'd at `/` because no
    frontend/app/page.tsx was ever generated. build_blueprint must now commission a real
    root home page that links to the app's ACTUAL routes. Proven against a real blueprint."""
    print("\n=== TEST 7b: generated home page (root / is no longer a 404) ===")
    bp = await builder.build_blueprint(summary(
        build="Bella Vista Italian restaurant with online ordering and Stripe payments",
        business_name="Bella Vista", is_food=True, menu_setup="pdf", is_local=True))
    tickets = bp["sprint_tickets"]
    roots = [t for t in tickets if t.get("filepath") == "frontend/app/page.tsx"]
    check("exactly one root home page (frontend/app/page.tsx) is commissioned",
          len(roots) == 1)
    hp = roots[0]
    check("it is FND-6, a frontend ticket, first-wave (no deps)",
          hp["id"] == "FND-6" and hp["assigned_to"] == "frontend" and hp["dependencies"] == [])
    check("its description names the business", "Bella Vista" in hp["description"])
    # Consistency: it links EXACTLY the app's real routes (whatever the build produced).
    real_routes = builder._frontend_page_routes(tickets)
    check("there ARE real routes to link (a menu app has feature pages)", len(real_routes) > 0)
    check("the home page links every real route, and none that don't exist",
          all(f"`{r}`" in hp["description"] for r in real_routes))
    check("the root route is NOT among the nav routes (the home page never links itself)",
          "/" not in real_routes)
    check("the home page is a server component (no client hooks / no data fetch)",
          'do NOT add "use client"' in hp["description"] and "do NOT fetch data" in hp["description"])
    # It survives the pipeline's own duplicate-path guard (unique root path).
    dupes = [t for t in tickets if t.get("filepath") == "frontend/app/page.tsx"]
    check("no other ticket collided onto the root page path", len(dupes) == 1)


async def main():
    await test_payment_domain()
    await test_non_payment_domain()
    await test_gating_suite()
    test_reviewer_flag()
    await test_unique_filepaths()
    test_entrypoint_gets_real_router_paths()
    test_conventional_stem()
    test_contract_declares_exact_module_paths()
    test_developer_pins_assigned_path()
    test_homepage_helpers()
    await test_generated_homepage()

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
