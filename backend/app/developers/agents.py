"""Developer agents (Week 4).

One agent per ticket type (backend / frontend / mobile / integration).
Each ticket runs the exact 5-step process:

  1. Read the assigned ticket.
  2. Check already-generated files to reuse / avoid duplication.
  3. Write code in chunks — skeleton, logic, error handling.
  4. Self-review — does it satisfy the ticket?
  5. Return the file to be stored in generated_files.

Recovery when a ticket won't pass self-review:
  try 1 -> generate; try 2 -> rewrite with a different approach;
  try 3 -> minimal version; then flag status = needs_review.
Never silently fails.
"""
import json
import ast
import logging
import re

from app import codegen
from app.architect.builder import AUTH_EXPORTS as _AUTH_EXPORTS, \
    AUTH_MODULE as _AUTH_MODULE

logger = logging.getLogger("developers")

MAX_TRIES = 3

# Self-review is a cheap yes/no judgement — always run it on the cheapest fast
# model rather than the (expensive) generation model. This halves the number of
# Claude calls per ticket without touching generation quality.
REVIEW_MODEL = "gemini-2.5-flash-lite"

_STACK = {
    "backend": "FastAPI + async SQLAlchemy + PostgreSQL. File path under 'backend/app/'.",
    "frontend": "Next.js + React + TypeScript. File path under 'frontend/app/'.",
    "mobile": "React Native (TypeScript). File path under 'mobile/src/'.",
    "integration": "Python service wiring a third-party API. File path under "
                   "'backend/app/integrations/'.",
}


def _system(agent_type: str) -> str:
    # FastAPI-specific rule for backend files: a build died at startup with
    # "Invalid args for response field" because a route used a SQLAlchemy ORM model
    # as its response_model / return type (projects 342 and 573). FastAPI rejects an
    # ORM model there at app construction — pin the rule so no backend file guesses.
    backend_rule = (
        " CRITICAL FastAPI rule: a route's `response_model` — and any response "
        "TYPE ANNOTATION on the endpoint function — MUST be a Pydantic schema (a "
        "BaseModel), NEVER a SQLAlchemy ORM model. FastAPI rejects an ORM model "
        "there at app startup with 'Invalid args for response field'. Define a "
        "Pydantic response schema for what you return, or set response_model=None "
        "and do not annotate the return type with an ORM model."
        # Pydantic v2 rule (project 829): `conlist(Item, min_items=1)` crashes the
        # app at import with "conlist() got an unexpected keyword argument
        # 'min_items'" — v2 renamed those arguments. Any v1 spelling breaks boot.
        " CRITICAL Pydantic rule: this stack is Pydantic v2. Length constraints use "
        "`min_length` / `max_length`, NEVER the v1 names `min_items` / `max_items` "
        "(removed in v2 — they raise `TypeError` at import and the app will not "
        "start). This applies to `conlist(...)`, `constr(...)`, `Field(...)` and "
        "`conset(...)`. Use `min_length=`/`max_length=` everywhere."
        # DB-session dependency (project 888): a route used `Depends(async_session)`,
        # so FastAPI read the sessionmaker's __call__(**local_kw) as a query param and
        # every request 422'd. Only visible over real HTTP.
        " CRITICAL DB-session rule: inject the database session with "
        "`Depends(get_db)` (the async generator dependency in "
        "backend/app/database.py). NEVER `Depends(async_session)` — that is the "
        "sessionmaker itself; FastAPI turns its `__call__(**local_kw)` into a REQUIRED "
        "query parameter and every request fails with 422 before your handler runs."
        # Schema adherence (project 888): the model renamed the contract column
        # `source` to `source_name`, so a response schema field `source` 500'd once
        # rows existed (ResponseValidationError, 'source' Field required).
        " CRITICAL schema-adherence rule: use the EXACT column names from the binding "
        "contract's DATABASE SCHEMA in BOTH your SQLAlchemy models AND your Pydantic "
        "request/response schemas — never rename a column (do NOT turn `source` into "
        "`source_name`, `user` into `user_id`, etc.). A response-schema field that "
        "does not match a real model attribute raises ResponseValidationError (500) "
        "as soon as a row is serialized."
        # Error propagation in get_db (project 1289): `get_db` wrapped `yield session`
        # in `except Exception: raise HTTPException(500)`. FastAPI runs the request
        # inside the yield, so a downstream HTTPException(401) got re-raised as a 500 —
        # every 401/404/422 on every DB endpoint became "Internal server error".
        # Stripe Connect account (owner onboarding): the platform connects the OWNER's
        # Stripe account BEFORE deploy and injects its id as STRIPE_CONNECTED_ACCOUNT_ID.
        # The app must charge ON that account so money reaches the owner, not the platform.
        # Third-party import paths (run 1496): `from stripe.api_resources import
        # PaymentIntent` — the LLM guessed an INTERNAL submodule; the real path is
        # `from stripe import PaymentIntent`. ImportError at startup, boot fails.
        " CRITICAL third-party import rule: import third-party symbols from their "
        "DOCUMENTED PUBLIC location — almost always the package's TOP LEVEL (e.g. "
        "`from stripe import PaymentIntent`, `import stripe` then `stripe.Charge`; "
        "`from pypdf import PdfReader`). Do NOT guess internal submodule paths such as "
        "`stripe.api_resources`, `pypdf.errors`, or `<pkg>.models` unless you are certain "
        "they are the package's public API — a wrong path is an ImportError that crashes "
        "the app at startup."
        " CRITICAL Stripe-account rule: if this app takes payments via Stripe Connect, "
        "read the owner's connected account id from the environment variable "
        "`STRIPE_CONNECTED_ACCOUNT_ID`. When it is set, treat the account as ALREADY "
        "connected (do NOT require the runtime OAuth connect flow just to take a payment) "
        "and pass it on every Stripe API call that acts for the owner — either the "
        "`Stripe-Account: <id>` header or the `stripe_account=<id>` parameter — so charges "
        "and payouts go to the OWNER's account. Fall back to any stored/OAuth-obtained "
        "account only when STRIPE_CONNECTED_ACCOUNT_ID is absent."
        # Provider config env-var NAMES must match what the platform injects
        # (run 1614 fail-fasted on AUTH0_AUDIENCE / STRIPE_CLIENT_SECRET mismatches).
        " CRITICAL provider-config naming rule: read provider configuration from "
        "these EXACT environment variable names (the platform injects these): Auth0 "
        "-> `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` (the API audience), `AUTH0_CLIENT_ID`, "
        "`AUTH0_CLIENT_SECRET`; Stripe -> `STRIPE_CLIENT_ID`, `STRIPE_CLIENT_SECRET` "
        "(the secret key), `STRIPE_REDIRECT_URI`, `STRIPE_TOKEN_ENC_KEY`, and "
        "`STRIPE_STATE_SECRET` if you sign OAuth state. Do NOT invent other spellings "
        "(not API_AUDIENCE, not STRIPE_SECRET_KEY) - a mismatch makes the app "
        "fail-fast at startup because the value is not present under the name you read."
        " CRITICAL error-propagation rule: a database-session dependency generator "
        "(`get_db` and any `Depends`-ed generator that `yield`s) MUST let framework "
        "`HTTPException`s (401/404/422/400) propagate UNCHANGED. Do NOT wrap the `yield` "
        "in a broad `try/except Exception` that raises `HTTPException(500)` — that catches "
        "the request's own HTTPExceptions (FastAPI runs the request inside the yield) and "
        "turns every intended 4xx into a 500. Prefer the plain `async with "
        "async_session() as session: yield session` with NO wrapping try/except; if you "
        "must catch, re-raise `HTTPException` first (`except HTTPException: raise`) and "
        "only map a specific `SQLAlchemyError`, never broad `Exception`, to a 500."
    ) if agent_type == "backend" else ""
    # Frontend API-base contract (deploy gap #2): the deploy wires the backend behind a
    # `/api` prefix and injects the base URL as `NEXT_PUBLIC_API_BASE_URL` at BUILD time.
    # The frontend MUST read that exact env var — a different name (or a hardcoded host)
    # means the browser can't reach the backend (the run-1105 "Loading…" forever bug).
    # NOTE: this literal MUST match manifest.FRONTEND_API_BASE_ENV; test_devops_offline
    # asserts they agree.
    frontend_rule = (
        " CRITICAL API-base rule: to call the backend, use EXACTLY the environment "
        "variable `process.env.NEXT_PUBLIC_API_BASE_URL` as the base URL for every "
        "request (e.g. `fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/menu`)`). Do "
        "NOT hardcode a backend host/port, do NOT use a relative path without that "
        "base, and do NOT invent another env-var name (not NEXT_PUBLIC_API_URL, not "
        "NEXT_PUBLIC_BACKEND_URL). The platform sets NEXT_PUBLIC_API_BASE_URL at build "
        "time and routes it to the backend; any other name leaves the UI unable to "
        "reach the API."
        # Auth0 login (owner onboarding): the platform auto-provisions a per-project
        # Auth0 app and injects these PUBLIC values at build time. The frontend MUST read
        # these EXACT names — nothing else is provisioned. NOTE: must match
        # manifest.FRONTEND_AUTH0_ENVS; test_devops_offline asserts they agree.
        " CRITICAL Auth0 login rule: if this app has user login/accounts, implement it "
        "with Auth0 and read the configuration from EXACTLY these build-time environment "
        "variables — `process.env.NEXT_PUBLIC_AUTH0_DOMAIN`, "
        "`process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID`, and "
        "`process.env.NEXT_PUBLIC_AUTH0_AUDIENCE` (the API audience for access tokens). "
        "Do NOT hardcode an Auth0 domain/client id and do NOT invent other env-var names. "
        "The platform sets these at build time; any other name leaves login unconfigured. "
        "You MUST actually IMPLEMENT the login flow (not just read the vars): use "
        "`@auth0/auth0-react` — wrap the app in `<Auth0Provider>` (via the root layout), "
        "provide a Login/Logout button (`loginWithRedirect()`/`logout()`), and on every "
        "call to a PROTECTED backend endpoint attach the access token from "
        "`getAccessTokenSilently()` as an `Authorization: Bearer <token>` header. A backend "
        "that returns 401 is not a bug — it means the frontend never logged the user in. "
        "Without a real login flow every gated feature is an unreachable 401."
    ) if agent_type == "frontend" else ""
    return (
        f"You are a senior {agent_type} developer. Generate ONE complete, "
        f"production-quality code file for the given ticket. Stack: "
        f"{_STACK.get(agent_type, 'the project stack')} Write it in order: a "
        f"clear skeleton, then the real logic, then error handling. Include "
        f"input validation and sensible error handling. EVERY function MUST contain "
        f"its REAL, working implementation: NEVER leave a function the ticket asks "
        f"for as a placeholder/stub — no bare `pass`, no `return []`/`return None` "
        f"standing in for logic, no `# TODO`, no `raise NotImplementedError`. A "
        f"function named for work it should do (parse/extract/process/…) that just "
        f"returns an empty value is a BUG: it makes the feature silently do nothing "
        f"while endpoints still answer 200. You MUST obey the "
        f"BINDING PROJECT CONTRACT given below: use its exact table/column "
        f"names and endpoint paths, import shared models/session from the "
        f"stated modules instead of redefining them, read secrets from "
        f"environment variables, and only import packages that actually exist. "
        f"Return ONLY a JSON "
        f'object: {{"filename": string, "filepath": string, "content": string}}. '
        f"content is the FULL file as a single string. No markdown fences, no prose."
        + backend_rule + frontend_rule
    )


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


async def _generate(agent_type: str, model: str, prompt: str) -> dict | None:
    text, _used = await codegen.generate(model, _system(agent_type), prompt, temperature=0.1)
    result = _extract_json(text)
    if result and result.get("content") and result.get("filename"):
        result.setdefault("filepath", result["filename"])
        return result
    return None


_REVIEW_SYS = (
    "You review generated code against its ticket. Reply JSON "
    '{"ok": true|false, "issues": "short reason if not ok"}. Be lenient: '
    "ok=true if the file plausibly fulfills the ticket."
)


async def _self_review(model: str, ticket: dict, file: dict) -> tuple[bool, str]:
    # `model` (the generation model) is deliberately ignored — reviews run on
    # the cheap REVIEW_MODEL.
    text, _ = await codegen.generate(
        REVIEW_MODEL, _REVIEW_SYS,
        f"Ticket: {ticket.get('title')} — {ticket.get('description')}\n"
        f"File: {file['filename']}\n\n{file['content'][:4000]}",
        temperature=0.0,
    )
    res = _extract_json(text)
    if not isinstance(res, dict):
        return True, ""  # can't review -> don't block
    return bool(res.get("ok", True)), str(res.get("issues", ""))


_ROUTER_RE = re.compile(r"^\s*(\w+)\s*=\s*APIRouter\b", re.M)


def _module_path(filepath: str) -> str:
    """backend/app/routes/menu.py -> backend.app.routes.menu"""
    return filepath[:-3].replace("/", ".") if filepath.endswith(".py") else \
        filepath.replace("/", ".")


def _router_modules(existing: list[dict]) -> list[tuple[str, str]]:
    """(module_path, router_var) for every already-generated file that actually
    defines an APIRouter.

    CONTENT-based, not path- or name-based. The entrypoint used to guess
    conventional router names (`routes.menu`) that did not match the real
    generated filenames (`routes.implement_menu_retrieval_endpoint`), and the app
    failed to import. Detecting the router by its `= APIRouter(...)` assignment
    means the exact, real module path is handed to the entrypoint — and files
    that define no router (models, database, scaffolding, middleware) are
    correctly left out, so the entrypoint never imports a `router` that isn't
    there.
    """
    out: list[tuple[str, str]] = []
    for f in existing:
        content = f.get("content") or ""
        fp = f.get("filepath") or f.get("filename") or ""
        if not fp.endswith(".py"):
            continue
        m = _ROUTER_RE.search(content)
        if m:
            out.append((_module_path(fp), m.group(1)))
    return out


def _auth_contract() -> str:
    """Symbol-level contract for backend/app/auth.py — the counterpart to the
    router-path pinning below. Two live boots died because a backend file GUESSED
    a name that auth.py never exported (435: 'Auth0Config', 513: 'verify_token').
    Pin the exact exported names so importers never guess."""
    exports = "\n".join(
        f"    {n}   (FastAPI dependency)" for n in _AUTH_EXPORTS)
    return (
        f"AUTH CONTRACT — {_AUTH_MODULE} exports EXACTLY these importable names, "
        f"and NO others:\n{exports}\n"
        f"To protect an endpoint, import the EXACT name you need directly from "
        f"{_AUTH_MODULE} (e.g. `from {_AUTH_MODULE} import {_AUTH_EXPORTS[-1]}`) and "
        f"add it as a dependency. Do NOT invent other auth names (no verify_token, "
        f"verify_admin, decode_token, require_auth, get_current_active_user), and do "
        f"NOT import auth helpers from any other module — authorization lives ONLY in "
        f"{_AUTH_MODULE}.\n"
    )


def _base_prompt(ticket: dict, existing: list[dict], contract: str = "") -> str:
    # Full paths, not bare filenames: the entrypoint ticket (APP-1) has to import
    # routers by module path, and paths also make duplicate-file collisions
    # visible to the agent.
    names = ", ".join(f.get("filepath") or f["filename"] for f in existing) or "none yet"
    parts = []
    if contract:
        parts.append(contract)

    # Every backend file EXCEPT auth.py itself gets the auth symbol contract, so it
    # imports the real exported names instead of guessing (the 435/513 boot deaths).
    if ticket.get("assigned_to") == "backend" and \
            (ticket.get("filepath") or "") != f"{_AUTH_MODULE.replace('.', '/')}.py":
        parts.append("\n" + _auth_contract())

    # Hand the agent the REAL foundation code so it imports the actual models
    # and session instead of inventing its own (the cross-file drift fix).
    foundation = [f for f in existing if str(f.get("ticket_id", "")).startswith("FND-")]
    for f in foundation:
        parts.append(
            f"\n=== EXISTING SHARED FILE: {f.get('filepath', f['filename'])} "
            f"(import from this — do not redefine) ===\n{f['content'][:6000]}"
        )

    parts.append(
        f"\nTicket {ticket.get('id')}: {ticket.get('title')}\n"
        f"Description: {ticket.get('description')}\n"
        f"Other files already generated (reuse, don't duplicate): {names}\n"
    )
    # The Architect assigns the output path so two tickets can never land on the
    # same file. State it explicitly — the agent still needs to know where its
    # own module lives in order to write correct imports.
    if ticket.get("filepath"):
        parts.append(
            f"Write this ticket's code to EXACTLY this path: "
            f"{ticket['filepath']}\nReturn that same value as \"filepath\". Do "
            f"not choose a different location — another ticket may own it.\n"
        )

    # The entrypoint must register the routers that were actually generated, by
    # their REAL module paths. Enumerate them explicitly rather than trusting the
    # model to reconstruct the names — that guessing is what broke a real build.
    if ticket.get("is_entrypoint"):
        routers = _router_modules(existing)
        if routers:
            lines = "\n".join(f"    from {mod} import {var} as {mod.split('.')[-1]}_router"
                              for mod, var in routers)
            parts.append(
                "\nREGISTER EXACTLY THESE ROUTERS — they are the only modules that "
                "define an APIRouter, and these module paths are EXACT (do not "
                "shorten, rename, or invent conventional names like "
                "`routes.menu`):\n" + lines + "\n"
                "Import each as shown and register every one with "
                "app.include_router(...). Import NO other router module.\n"
            )
    return "\n".join(parts)


def _pin_path(file: dict, ticket: dict) -> dict:
    """Force the Architect's assigned path onto the generated file.

    The prompt asks for it, but a prompt is a request, not a guarantee — and a
    file landing on another ticket's path silently destroys that ticket's work.
    This is the enforcement.
    """
    assigned = (ticket.get("filepath") or "").strip()
    if not assigned:
        return file
    return {**file, "filepath": assigned, "filename": assigned.rpartition("/")[2]}


STUB_STATUS = "stub"

# Function names that carry the app's actual work — if one of these is left as a
# placeholder, the feature silently does nothing (project 888: the generated
# `parse_menu_items` was `return []`, so the menu extraction pipeline extracted
# NOTHING from any menu while every endpoint returned 200). A trivial body is fine
# for a genuine no-op helper, so we only flag functions whose NAME says they do work.
_WORK_FUNC_HINTS = ("parse", "extract", "process", "transform", "compute", "convert",
                    "analyze", "analyse", "generate", "build", "render", "handle")


def _strip_docstring(body: list) -> list:
    if body and isinstance(body[0], ast.Expr) and isinstance(
            getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _is_empty_returnish(value) -> bool:
    """True for `return`/`return None`/`return []`/`{}`/`()`/`set()`/''/0/False —
    i.e. a return that yields nothing meaningful."""
    if value is None:
        return True  # bare `return`
    if isinstance(value, ast.Constant):
        return value.value in (None, "", 0, False)
    if isinstance(value, (ast.List, ast.Tuple)) and not value.elts:
        return True
    if isinstance(value, ast.Dict) and not value.keys:
        return True
    if isinstance(value, ast.Set) and not value.elts:
        return True
    if isinstance(value, ast.Call) and getattr(value.func, "id", None) in (
            "list", "dict", "tuple", "set") and not value.args and not value.keywords:
        return True
    return False


def _is_stub_body(node) -> bool:
    """A function whose body (ignoring a docstring) is ONLY `pass`, a single empty
    return, or `raise NotImplementedError` — a placeholder that does no real work."""
    body = _strip_docstring(list(node.body))
    if not body:
        return True
    if len(body) != 1:
        return False
    stmt = body[0]
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Return):
        return _is_empty_returnish(stmt.value)
    if isinstance(stmt, ast.Raise):
        exc = stmt.exc
        name = None
        if isinstance(exc, ast.Call):
            name = getattr(exc.func, "id", None) or getattr(exc.func, "attr", None)
        elif isinstance(exc, ast.Name):
            name = exc.id
        return name == "NotImplementedError"
    return False


def stub_functions(content: str, only_work_named: bool = True) -> list[str]:
    """Names of functions that are placeholder STUBS (see `_is_stub_body`).

    With `only_work_named` (default), reports only functions whose name says they do
    real work (`_WORK_FUNC_HINTS`) — so `parse_menu_items() -> return []` is caught
    while a legitimately trivial helper is not. Same 'a stub is not built'
    philosophy as the whole-file stub gate, at function granularity.
    """
    try:
        tree = ast.parse(content or "")
    except SyntaxError:
        return []      # a syntax error is already its own QA finding
    names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_stub_body(node):
            if not only_work_named or any(h in node.name.lower() for h in _WORK_FUNC_HINTS):
                names.append(node.name)
    return names


_BAD_SESSION_DEP_RE = re.compile(r"Depends\(\s*async_session\s*\)")


def bad_session_dependency(content: str) -> bool:
    """True if the file injects the SQLAlchemy sessionmaker DIRECTLY as a FastAPI
    dependency — `Depends(async_session)` — instead of the `get_db` generator.
    FastAPI introspects the sessionmaker's `__call__(self, **local_kw)` signature and
    turns `local_kw` into a REQUIRED query parameter, so EVERY request 422s before the
    handler runs (project 888 — invisible until a real HTTP request hit the endpoint).
    The session dependency must be `Depends(get_db)`."""
    return bool(_BAD_SESSION_DEP_RE.search(content or ""))


def _model_columns(models_content: str) -> dict[str, set]:
    """{table name -> set of column ATTRIBUTE names} for every SQLAlchemy model
    (a class with `__tablename__`) defined in the file."""
    out: dict[str, set] = {}
    try:
        tree = ast.parse(models_content or "")
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        tablename, cols = None, set()
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
                continue
            tgt = stmt.targets[0]
            if not isinstance(tgt, ast.Name):
                continue
            if tgt.id == "__tablename__" and isinstance(stmt.value, ast.Constant) \
                    and isinstance(stmt.value.value, str):
                tablename = stmt.value.value
            elif isinstance(stmt.value, ast.Call):
                fn = stmt.value.func
                if (getattr(fn, "id", None) or getattr(fn, "attr", None)) in ("Column", "mapped_column"):
                    cols.add(tgt.id)
        if tablename:
            out[tablename] = cols
    return out


def model_schema_mismatches(models_content: str, database_schema: list) -> list[str]:
    """Contract adherence: every column the binding contract's `database_schema`
    declares for a table MUST appear, by its EXACT name, on the generated model for
    that table. A RENAMED column (project 888: the contract's `source` became
    `source_name` in the model) leaves the contract name missing, which breaks any
    response schema / query that uses the real name — a 500 that only appears once
    rows exist. Returns 'table.column' for each declared column absent from its model.
    A table with no matching model is skipped (that is a different, missing-file
    problem, not a rename)."""
    model_cols = _model_columns(models_content)
    missing = []
    for t in database_schema or []:
        tname = t.get("table")
        if tname not in model_cols:
            continue
        for c in (t.get("columns") or []):
            name = c.get("name")
            if name and name not in model_cols[tname]:
                missing.append(f"{tname}.{name}")
    return missing


# ------------------------------------------------- HTTPException swallow (FIX #24)
# ERROR PROPAGATION (project 1289): the generated `database.py` (FND-2) wrote a
# `get_db` dependency whose `yield session` is wrapped in `try: ... except
# Exception: raise HTTPException(500, "Internal server error")`. FastAPI runs the
# rest of a request INSIDE that generator's `yield`, so when a protected endpoint's
# OAuth2 dependency raises `HTTPException(401)`, that 401 propagates back through the
# yield, is caught by the broad `except`, and is RE-RAISED AS A 500 — masking every
# intended 401/404/422/400 on every endpoint that depends on get_db (run 1289: all
# 20 QA failures, no-login/missing-field/injection/happy-path all became 500). The
# correct pattern lets framework HTTPExceptions propagate unchanged and only maps
# genuinely-unexpected errors. This is the deterministic detector for that anti-pattern.
def _status_is_500(node: ast.AST) -> bool:
    """True if an AST node denotes HTTP 500 — literal `500`,
    `status.HTTP_500_INTERNAL_SERVER_ERROR`, or a bare `HTTP_500_*` name."""
    if isinstance(node, ast.Constant) and node.value == 500:
        return True
    if isinstance(node, ast.Attribute):
        return node.attr.startswith("HTTP_500")
    if isinstance(node, ast.Name):
        return node.id.startswith("HTTP_500")
    return False


def _raises_http_500(node: ast.AST) -> bool:
    """True if `node` is a `raise HTTPException(...)` whose status is 500 (positional
    first arg or `status_code=`), or a `return`/`raise` of a *Response(status_code=500)."""
    call = None
    if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
        call = node.exc
    elif isinstance(node, ast.Return) and isinstance(node.value, ast.Call):
        call = node.value
    if call is None:
        return False
    fname = getattr(call.func, "id", None) or getattr(call.func, "attr", None) or ""
    is_http = fname == "HTTPException" or fname.endswith("Response")
    if not is_http:
        return False
    for kw in call.keywords:
        if kw.arg in ("status_code", "status") and _status_is_500(kw.value):
            return True
    # HTTPException(500, ...) — status is the first positional arg
    if fname == "HTTPException" and call.args and _status_is_500(call.args[0]):
        return True
    return False


def _reraises_httpexception(handler: ast.ExceptHandler) -> bool:
    """True if a broad `except` body preserves already-HTTPException errors: a bare
    `raise` (re-raises the current exception) or an `isinstance(e, HTTPException)`
    guard anywhere in its body. Either makes the handler safe → not flagged."""
    for n in ast.walk(handler):
        if isinstance(n, ast.Raise) and n.exc is None:      # bare `raise`
            return True
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "isinstance":
            for a in n.args[1:]:
                for sub in ast.walk(a):
                    if isinstance(sub, ast.Name) and sub.id == "HTTPException":
                        return True
    return False


_BROAD_EXC_NAMES = {"Exception", "BaseException"}


def _handler_is_broad(handler: ast.ExceptHandler) -> bool:
    """True if `except:` (bare) or `except Exception`/`except BaseException` (single or
    in a tuple). A specific type like `SQLAlchemyError` is NOT broad — the gen888 get_db
    catches SQLAlchemyError and is correct, so it must never be flagged."""
    t = handler.type
    if t is None:
        return True                                          # bare except:
    types = t.elts if isinstance(t, ast.Tuple) else [t]
    return any(isinstance(x, ast.Name) and x.id in _BROAD_EXC_NAMES for x in types)


def http_exception_swallow(content: str, filepath: str) -> list[dict]:
    """Structured findings for a FastAPI DEPENDENCY GENERATOR (a function whose `try`
    body contains a `yield` — get_db and friends) that SWALLOWS framework HTTPExceptions
    into a 500. Flags only when a `try` wrapping a `yield` has a handler that (1) catches
    broad `Exception`/`BaseException`/bare-`except`, (2) raises/returns HTTP 500, and
    (3) does NOT preserve already-HTTPException errors (no bare `raise`, no
    `isinstance(_, HTTPException)` guard, and no earlier `except HTTPException` sibling on
    the same try). Backend `.py` only; returns [] on non-`.py` or a SyntaxError (the
    syntax gate owns that). Returns [{file, line, function, detail}]."""
    if not filepath.endswith(".py"):
        return []
    try:
        tree = ast.parse(content or "")
    except SyntaxError:
        return []
    findings: list[dict] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for tnode in ast.walk(fn):
            if not isinstance(tnode, ast.Try):
                continue
            if not any(isinstance(y, (ast.Yield, ast.YieldFrom))
                       for stmt in tnode.body for y in ast.walk(stmt)):
                continue                                     # not a dependency generator's try
            # An earlier `except HTTPException` sibling already preserves 401/404/422.
            has_http_sibling = any(
                h.type is not None and any(
                    isinstance(x, ast.Name) and x.id == "HTTPException"
                    for x in (h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]))
                for h in tnode.handlers)
            for h in tnode.handlers:
                if not _handler_is_broad(h):
                    continue
                if not any(_raises_http_500(n) for n in ast.walk(h)):
                    continue
                if has_http_sibling or _reraises_httpexception(h):
                    continue
                findings.append({
                    "file": filepath, "line": h.lineno, "function": fn.name,
                    "detail": (f"dependency generator `{fn.name}` catches broad "
                               f"{'except:' if h.type is None else ast.unparse(h.type)} "
                               f"around its `yield` and re-raises framework "
                               f"HTTPExceptions as HTTP 500")})
                break                                        # one finding per function is enough
    return findings


# ---------------------------------------------------------------- symbol resolution (FIX #16)
# IMPORT RESOLUTION (projects 1038): a fresh generation wrote
# `from backend.app.auth import require_admin`, but auth.py exports only
# `get_current_user` / `get_current_admin_user` — the app dies at boot on
# `ImportError: cannot import name 'require_admin'`. Fix #3's PROMPT rule asks the
# LLM not to guess auth names; a prompt is non-deterministic and did not stop it.
# This gate is the deterministic counterpart: for every generated backend `.py`,
# each `from <in-project module> import <symbol>` MUST resolve to a real export of
# that module — auth against the authoritative AUTH_EXPORTS contract, every other
# in-project module against an AST scan of its OWN generated defs. Same 'a guessed
# symbol is a build failure' philosophy as the schema-adherence gate above.
#
# HARD REQUIREMENT — zero false positives on valid code. A `from M import Y` is
# flagged ONLY when M is unambiguously an in-project module whose full export set we
# can enumerate AND Y is neither an export, a submodule of M, nor a dunder. Anything
# uncertain — a third-party/stdlib module (OUT OF SCOPE for #16, deferred to a later
# dependency-validation slice that runs where the package is installed), a module
# that star-imports (opaque), an unparseable module, or a relative import — is
# treated as resolvable and never flagged.
_AUTH_ALIASES = frozenset({_AUTH_MODULE, _AUTH_MODULE.split(".", 1)[1]})  # backend.app.auth + app.auth


def _dotted_aliases(filepath: str) -> tuple[list[str], bool]:
    """(dotted module paths this file answers to, is_package). A file is registered
    under BOTH its `backend.app.…` and `app.…` spellings because generated code uses
    the former and the platform's own code uses the latter. An `__init__.py` maps to
    its PACKAGE path (the trailing `.__init__` dropped)."""
    if not filepath.endswith(".py"):
        return [], False
    dotted = filepath[:-3].replace("/", ".")
    is_pkg = dotted.endswith(".__init__")
    if is_pkg:
        dotted = dotted[: -len(".__init__")]
    aliases = {dotted}
    if dotted.startswith("backend.app"):
        aliases.add(dotted[len("backend.") :])           # backend.app.x -> app.x
    elif dotted.startswith("app.") or dotted == "app":
        aliases.add("backend." + dotted)                 # app.x -> backend.app.x
    return sorted(aliases), is_pkg


def _collect_module_names(body: list, names: set) -> bool:
    """Collect module-level BOUND names from a list of statements, descending through
    top-level control flow (if/try/for/while/with) but NOT into function/class bodies
    (their locals are not module exports). Returns False if the module is OPAQUE — it
    contains a star import, so its real export set is unknowable and callers must not
    flag anything imported from it."""
    ok = True
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                for nm in ast.walk(tgt):
                    if isinstance(nm, ast.Name):
                        names.add(nm.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if any(a.name == "*" for a in node.names):
                ok = False                                # star import -> opaque
            else:
                for a in node.names:
                    names.add(a.asname or a.name)
        elif isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.AsyncFor,
                               ast.AsyncWith)):
            ok = _collect_module_names(node.body, names) and ok
            ok = _collect_module_names(getattr(node, "orelse", []), names) and ok
        elif isinstance(node, ast.Try):
            ok = _collect_module_names(node.body, names) and ok
            ok = _collect_module_names(node.orelse, names) and ok
            ok = _collect_module_names(node.finalbody, names) and ok
            for h in node.handlers:
                ok = _collect_module_names(h.body, names) and ok
    return ok


def _module_exports(content: str) -> set | None:
    """The set of names importable from a module's source, or None if the module is
    OPAQUE (unparseable, or star-imports). None means 'cannot enumerate -> never
    flag imports from here'."""
    try:
        tree = ast.parse(content or "")
    except SyntaxError:
        return None
    names: set = set()
    return names if _collect_module_names(tree.body, names) else None


# ---- class attribute surface (FIX #19 — Attribute Resolution Gate) --------------------
# The curated framework-base attribute surfaces. A class's OWN body defs are captured by
# AST scan; these are the inherited names we cannot see in the body but must NOT flag.
# Dunders are excluded on the ACCESS side regardless, so these hold the non-dunder API.
_SQLA_MODEL_ATTRS = frozenset({
    "metadata", "registry", "query", "c", "awaitable_attrs",
    "__table__", "__tablename__", "__mapper__", "__mapper_args__", "__table_args__"})
_PYDANTIC_MODEL_ATTRS = frozenset({
    "model_dump", "model_dump_json", "model_validate", "model_validate_json",
    "model_construct", "model_copy", "model_config", "model_fields", "model_fields_set",
    "model_extra", "model_rebuild", "model_json_schema", "model_post_init",
    "dict", "json", "copy", "parse_obj", "parse_raw", "schema", "schema_json",
    "construct", "validate", "from_orm", "update_forward_refs", "Config"})
_DYNAMIC_ATTR_METHODS = ("__getattr__", "__getattribute__", "__setattr__", "__init_subclass__")


def _class_body_attrs(node: ast.ClassDef) -> tuple[set, bool]:
    """(attribute names bound on the class, is_dynamic). Captures class-body assigns
    (`Column(...)`, `relationship(...)`, `mapped_column(...)`), annotations, methods,
    `@property`/`@hybrid_property` (they are class-body FunctionDefs), nested classes,
    and `self.X = ...` assignments in methods. `is_dynamic` is True when the class opts
    into dynamic attributes (a `__getattr__`/`__setattr__` method or a `setattr(...)`
    call) — its real surface is then unknowable and it must NEVER be flagged.
    Over-capture is SAFE here (it only suppresses a flag); under-capture is what causes
    false positives, so this errs toward capturing more."""
    attrs: set = set()
    dynamic = False
    for stmt in node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            attrs.add(stmt.name)
            if stmt.name in _DYNAMIC_ATTR_METHODS:
                dynamic = True
            for sub in ast.walk(stmt):                     # self.X = ... / self.X: T = ...
                if isinstance(sub, ast.Assign):
                    for tgt in sub.targets:
                        if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) \
                                and tgt.value.id == "self":
                            attrs.add(tgt.attr)
                elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Attribute) \
                        and isinstance(sub.target.value, ast.Name) and sub.target.value.id == "self":
                    attrs.add(sub.target.attr)
        elif isinstance(stmt, ast.ClassDef):
            attrs.add(stmt.name)
        elif isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                for nm in ast.walk(tgt):
                    if isinstance(nm, ast.Name):
                        attrs.add(nm.id)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            attrs.add(stmt.target.id)
    for sub in ast.walk(node):                             # any setattr(...) -> dynamic surface
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                and sub.func.id == "setattr":
            dynamic = True
    return attrs, dynamic


def _module_class_index(content: str) -> tuple[dict, dict]:
    """({ClassName -> raw class info}, {local name -> (raw module, original name)}) for one
    module's source. The imports map lets a class name — or a base class — be resolved to
    where it is defined, across files. Returns ({}, {}) for unparseable content."""
    try:
        tree = ast.parse(content or "")
    except SyntaxError:
        return {}, {}
    classes: dict = {}
    imports: dict = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            attrs, dynamic = _class_body_attrs(node)
            classes[node.name] = {
                "attrs": attrs,
                "bases": [b.id for b in node.bases if isinstance(b, ast.Name)],
                # a base we can't name (Attribute like logging.Filter, a Subscript, or a
                # metaclass= keyword) means the surface is not fully enumerable -> open.
                "open_base": any(not isinstance(b, ast.Name) for b in node.bases)
                or bool(node.keywords),
                "tablename": "__tablename__" in attrs,     # the SQLAlchemy-model signal
                "dynamic": dynamic,
            }
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            for a in node.names:
                if a.name != "*":
                    imports[a.asname or a.name] = (node.module, a.name)
    return classes, imports


def build_symbol_index(project_files: list[dict]) -> dict:
    """Build the in-project symbol index once for a whole build, then reuse it for
    every file (see `import_symbol_mismatches` / `attribute_access_mismatches`). Structure:
      - modules: dotted module path -> source content (both spellings; __init__ maps
        to its package path)
      - all_paths: every dotted module/package path that exists (for submodule imports)
      - auth_present: whether an auth.py was actually generated
      - classes: dotted module -> {ClassName -> raw class info} (FIX #19)
      - class_imports: dotted module -> {local name -> (raw module, original name)} (FIX #19)
    """
    modules: dict[str, str] = {}
    all_paths: set[str] = set()
    classes: dict[str, dict] = {}
    class_imports: dict[str, dict] = {}
    auth_present = False
    for f in project_files:
        fp = (f.get("filepath") or f.get("filename") or "")
        if not fp.endswith(".py"):
            continue
        aliases, _is_pkg = _dotted_aliases(fp)
        content = f.get("content") or ""
        cdefs, cimports = _module_class_index(content)
        for a in aliases:
            modules[a] = content
            all_paths.add(a)
            classes[a] = cdefs
            class_imports[a] = cimports
        if any(a in _AUTH_ALIASES for a in aliases):
            auth_present = True
    return {"modules": modules, "all_paths": all_paths, "auth_present": auth_present,
            "classes": classes, "class_imports": class_imports}


def _in_project_two_seg_prefixes(modules) -> set:
    out = set()
    for m in modules:
        parts = m.split(".")
        if len(parts) >= 2:
            out.add(".".join(parts[:2]))
    return out


def _missing_in_project_module(mod: str, modules: dict, all_paths: set) -> bool:
    """True if `mod` LOOKS in-project (shares a generated module's 2-segment package
    prefix, e.g. `backend.app`) but was NEVER generated (run 1614: `backend.app.catalog`
    imported by order.py). A third-party / genuinely external module has no in-project
    prefix -> False (skipped, zero false positive). A package dir that CONTAINS generated
    modules is not 'missing'."""
    if not mod or mod in modules:
        return False
    parts = mod.split(".")
    if len(parts) < 2 or ".".join(parts[:2]) not in _in_project_two_seg_prefixes(modules):
        return False
    if any(gm == mod or gm.startswith(mod + ".") for gm in modules):
        return False
    if mod in all_paths:
        return False
    return True


def import_symbol_mismatches(content: str, filepath: str, index: dict) -> list[dict]:
    """Structured findings for every `from <in-project module> import <symbol>` in a
    generated backend `.py` whose symbol does NOT resolve to a real export of that
    module. Deterministic; zero false positives (see the module docstring above).

    Each finding: {file, line, module, symbol, available} — machine-readable so the
    bounded retry can build a precise repair prompt (see `repair_instructions`)."""
    if not filepath.endswith(".py"):
        return []
    try:
        tree = ast.parse(content or "")
    except SyntaxError:
        return []                                         # syntax is its own finding
    modules = index.get("modules", {})
    all_paths = index.get("all_paths", set())
    auth_present = index.get("auth_present", False)
    self_aliases = set(_dotted_aliases(filepath)[0])
    findings: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:                                    # relative import -> skip (safe)
            continue
        mod = node.module or ""
        # AUTH: authoritative contract, regardless of auth.py's own generated content —
        # but only when an auth module was actually generated for this app.
        if mod in _AUTH_ALIASES and auth_present:
            for a in node.names:
                y = a.name
                if y == "*" or y.startswith("__") or y in _AUTH_EXPORTS:
                    continue
                findings.append({"file": filepath, "line": node.lineno, "module": mod,
                                 "symbol": y, "available": list(_AUTH_EXPORTS)})
            continue
        if mod not in modules or mod in self_aliases:
            # Fix B (run 1614): a `from backend.app.<X> import ...` where <X> was never
            # generated is a MISSING in-project module, not a third-party import. Flag it.
            if (mod not in self_aliases and mod not in _AUTH_ALIASES
                    and _missing_in_project_module(mod, modules, all_paths)):
                for a in node.names:
                    if a.name == "*" or a.name.startswith("__"):
                        continue
                    findings.append({"file": filepath, "line": node.lineno,
                                     "module": mod, "symbol": a.name,
                                     "available": [], "missing_module": True})
            continue                                      # out-of-project / self -> skip
        exports = _module_exports(modules[mod])
        if exports is None:
            continue                                      # opaque -> never flag
        for a in node.names:
            y = a.name
            if y == "*" or y.startswith("__"):
                continue
            if y in exports:
                continue
            if f"{mod}.{y}" in all_paths:                 # `from pkg import submodule`
                continue
            findings.append({"file": filepath, "line": node.lineno, "module": mod,
                             "symbol": y, "available": sorted(exports)})
    return findings


# ---------------------------------------------------------------- attribute resolution (FIX #19)
# NO ATTRIBUTE: the 3rd most common structural LLM codegen error (after wrong imports/#16
# and syntax/#17). Code accesses a field/method that does not exist on the class it uses —
# e.g. `Order.total_amonut` (typo) or `MenuItem.total_amount` (a field models.py never
# defines; the CONTEXT §"KNOWN-OPEN" example). This is a DIFFERENT mechanism than #16: #16
# checks module-level IMPORTS; #19 checks ATTRIBUTE ACCESS resolves to a real attribute of
# a known in-project class.
#
# SLICE 1 — CLASS-NAME access only (`ClassName.attr`): the type is the named class, so NO
# instance type-inference is needed (that is where false positives live; deferred to a
# later slice). HARD REQUIREMENT — zero false positives. `ClassName.attr` is flagged ONLY
# when the class is an ENUMERABLE in-project class (its full attribute surface is known)
# AND `attr` is neither a body attribute, an inherited framework attribute (SQLAlchemy /
# Pydantic curated surface), nor a dunder. A class is treated as OPEN (never flagged) if it
# is dynamic (`__getattr__`/`setattr`), has any base we cannot fully enumerate, or is not
# in-project. Instance access (`x.attr`), chained access, module-qualified access, and
# stored/assigned targets are all OUT OF SCOPE for slice 1 -> skipped.


def _alt_module_spelling(mod: str) -> str | None:
    """backend.app.x <-> app.x (the two spellings the same file answers to)."""
    if mod.startswith("backend.app"):
        return mod[len("backend."):]
    if mod == "app" or mod.startswith("app."):
        return "backend." + mod
    return None


def _lookup_class(name: str, module: str, index: dict) -> tuple[str, str] | None:
    """Resolve a class NAME as referenced inside `module` to the (dotted module, ClassName)
    where it is DEFINED — via a class defined in that module or imported into it from an
    in-project module. None if it is not an enumerable in-project class."""
    classes = index.get("classes", {})
    if name in classes.get(module, {}):
        return module, name
    tgt = index.get("class_imports", {}).get(module, {}).get(name)
    if tgt:
        tmod, tname = tgt
        for cand in (tmod, _alt_module_spelling(tmod)):
            if cand and tname in classes.get(cand, {}):
                return cand, tname
    return None


def _resolve_class_attrs(module: str, name: str, index: dict, seen: set | None = None) -> set | None:
    """The FULL attribute surface of an in-project class, or None if the class is OPEN and
    must never be flagged (dynamic, or any base we cannot fully enumerate). ORM models
    (identified by `__tablename__`) get the curated SQLAlchemy surface; Pydantic models
    (base `BaseModel`) get the Pydantic surface; in-project base classes are unioned
    recursively; any other base -> open."""
    seen = seen or set()
    if (module, name) in seen:                             # inheritance cycle -> give up safely
        return None
    seen.add((module, name))
    raw = index.get("classes", {}).get(module, {}).get(name)
    if raw is None or raw["dynamic"]:
        return None
    attrs = set(raw["attrs"])
    if raw["tablename"]:                                   # SQLAlchemy ORM model
        return attrs | _SQLA_MODEL_ATTRS
    if raw["open_base"]:
        return None
    for base in raw["bases"]:
        if base == "BaseModel":
            attrs |= _PYDANTIC_MODEL_ATTRS
            continue
        if base == "object":
            continue
        tgt = _lookup_class(base, module, index)
        if tgt is None:                                    # base not enumerable in-project -> open
            return None
        sub = _resolve_class_attrs(tgt[0], tgt[1], index, seen)
        if sub is None:
            return None
        attrs |= sub
    return attrs


def _stored_names(tree: ast.AST) -> set:
    """Every name that is ASSIGNED or bound as a parameter anywhere in the file. A class
    name that is also a local variable/param is ambiguous, so it is excluded from the
    class map (conservative — suppresses a possible flag, never adds a false one)."""
    out: set = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = n.args
            for a in (list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
                      + ([args.vararg] if args.vararg else [])
                      + ([args.kwarg] if args.kwarg else [])):
                out.add(a.arg)
    return out


def attribute_access_mismatches(content: str, filepath: str, index: dict) -> list[dict]:
    """Structured findings for every `ClassName.attr` in a generated backend `.py` whose
    `attr` does not exist on that enumerable in-project class (FIX #19, slice 1). Zero
    false positives by construction (see the module docstring). Each finding:
    {file, line, class, module, attribute, available} — machine-readable for
    `repair_instructions` (an ATTRIBUTE_RESOLUTION_FAILURE)."""
    if not filepath.endswith(".py"):
        return []
    try:
        tree = ast.parse(content or "")
    except SyntaxError:
        return []                                          # syntax is its own finding (#17)
    aliases = _dotted_aliases(filepath)[0]
    all_classes = index.get("classes", {})
    module = next((a for a in aliases if a in all_classes), (aliases or [""])[0])

    own_classes, own_imports = _module_class_index(content)
    shadowed = _stored_names(tree)
    # name -> (defining module, ClassName) for every enumerable in-project class this file
    # can refer to by a bare name, minus anything shadowed by a local variable/param.
    classmap: dict[str, tuple] = {}
    for cname in own_classes:
        if cname not in shadowed:
            classmap[cname] = (module, cname)
    for local, (tmod, tname) in own_imports.items():
        if local in shadowed or local in classmap:
            continue
        for cand in (tmod, _alt_module_spelling(tmod)):
            if cand and tname in all_classes.get(cand, {}):
                classmap[local] = (cand, tname)
                break

    findings: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or not isinstance(node.ctx, ast.Load):
            continue                                       # only attribute READS on a bare name
        if not isinstance(node.value, ast.Name):
            continue                                       # single-level `ClassName.attr` only
        cls = node.value.id
        if cls not in classmap:
            continue
        attr = node.attr
        if attr.startswith("__") and attr.endswith("__"):  # dunders: skip
            continue
        cmod, cname = classmap[cls]
        surface = _resolve_class_attrs(cmod, cname, index)
        if surface is None:                                # open class -> never flag
            continue
        if attr in surface:
            continue
        body_attrs = index["classes"][cmod][cname]["attrs"]
        findings.append({
            "file": filepath, "line": node.lineno, "class": cname, "module": cmod,
            "attribute": attr,
            "available": sorted(a for a in body_attrs if not a.startswith("__"))})
    return findings


# ---------------------------------------------------------------- syntax / AST (FIX #17)
# SYNTAX (project 1071): a fresh generation of `routes/order_be_3.py` put a non-default
# parameter (`order_update: OrderUpdateRequest`) AFTER a defaulted one
# (`order_id: int = Path(...)`) — a hard Python `SyntaxError` at import, so the app never
# boots. Only smoke_boot caught it, after the WHOLE build, and only routed to a blind
# retry. This gate makes an unparseable backend file a first-class build-gate finding
# with a targeted, bounded repair — the most fundamental Level-1 check of the Code
# Integrity Engine. Zero false positives BY CONSTRUCTION: valid Python parses, invalid
# does not (`ast.parse` is exactly what the interpreter uses).


def python_syntax_error(content: str, filepath: str) -> dict | None:
    """Structured finding if a generated PYTHON file does not parse, else None. Only
    for `.py` files — frontend `.tsx` truncation is handled structurally by
    `frontend_incomplete` (fix #15); there is no Node toolchain here for real TS syntax.
    Returns {file, line, offset, message, text} — machine-readable so the bounded retry
    can build a precise SYNTAX_ERROR repair (see `repair_instructions`)."""
    if not filepath.endswith(".py"):
        return None
    try:
        ast.parse(content or "")
        return None
    except SyntaxError as e:
        return {"file": filepath, "line": e.lineno, "offset": e.offset,
                "message": e.msg, "text": (e.text or "").rstrip()}


def repair_instructions(result: dict) -> str:
    """Turn a gate result's structured findings into a precise, bounded repair prompt for
    the Developer agent's retry — a targeted SYNTAX_ERROR / IMPORT_RESOLUTION_FAILURE
    ticket, NOT the blind 'take a different approach' regenerate that churned other files
    into a non-booting state on projects 1038/1039. Empty string if there is nothing
    structured to repair."""
    parts: list[str] = []

    # SYNTAX_ERROR (fix #17) — first, because an unparseable file blocks everything else.
    syn = result.get("syntax_error")
    if syn:
        loc = f"line {syn.get('line')}" + (f", col {syn['offset']}" if syn.get("offset") else "")
        offending = f"\nOffending source: {syn['text']}" if syn.get("text") else ""
        parts.append(
            "\n=== SYNTAX_ERROR — repair ONLY this file, do not touch any other file ===\n"
            f"File: {syn['file']}\n"
            f"Python could not parse this file ({loc}): {syn.get('message')}"
            f"{offending}\n"
            "Repair: fix the syntax so the file parses. For a 'parameter without a default "
            "follows parameter with a default' error, reorder the function signature so "
            "every parameter WITHOUT a default comes before any parameter WITH a default "
            "(or give the offending parameter a default, e.g. FastAPI `Body(...)`). Keep "
            "the file's behaviour and its public names unchanged."
        )

    # IMPORT_RESOLUTION_FAILURE (fix #16).
    repairs = result.get("symbol_repairs") or []
    if repairs:
        parts.append("\n=== IMPORT_RESOLUTION_FAILURE — repair ONLY this file, do not "
                     "touch any other file ===")
        for r in repairs:
            if r.get("missing_module"):
                parts.append(
                    f"\nModule: {r['module']} — this in-project module DOES NOT EXIST "
                    f"(no such file was generated).\n"
                    f"Requested: {r['symbol']}  (line {r.get('line')})\n"
                    f"Repair: implement `{r['symbol']}` INLINE in this file, or import it "
                    f"from a module that actually exists. Do NOT import from "
                    f"`{r['module']}` — it was never created.")
                continue
            avail = ", ".join(r.get("available") or []) or "(none — the module exports nothing)"
            parts.append(
                f"\nModule: {r['module']}\n"
                f"Requested symbol (does NOT exist): {r['symbol']}  (line {r.get('line')})\n"
                f"Available symbols in that module: {avail}\n"
                f"Repair: import one of the available symbols above, or implement the needed "
                f"behaviour INLINE in this file. Do NOT invent a symbol the module does not "
                f"export, and do NOT modify the imported module."
            )

    # ATTRIBUTE_RESOLUTION_FAILURE (fix #19).
    attrs = result.get("attribute_repairs") or []
    if attrs:
        parts.append("\n=== ATTRIBUTE_RESOLUTION_FAILURE — repair ONLY this file, do not "
                     "touch any other file ===")
        for r in attrs:
            avail = ", ".join(r.get("available") or []) or "(the class defines no fields of its own)"
            parts.append(
                f"\nClass: {r['class']}  (defined in {r['module']})\n"
                f"Accessed attribute (does NOT exist on that class): {r['class']}."
                f"{r['attribute']}  (line {r.get('line')})\n"
                f"Real attributes of {r['class']}: {avail}\n"
                f"Repair: use a real attribute/field from the list above (this is usually a "
                f"typo or a wrong field name), or add the field to the class ONLY if this file "
                f"owns that class's definition. Do NOT modify the class's module from here."
            )

    # HTTP_EXCEPTION_SWALLOW (fix #24).
    swallows = result.get("http_swallow_repairs") or []
    if swallows:
        parts.append("\n=== HTTP_EXCEPTION_SWALLOW — repair ONLY this file, do not "
                     "touch any other file ===")
        for r in swallows:
            parts.append(
                f"\nFunction: {r['function']}  (broad handler at line {r.get('line')})\n"
                f"Problem: {r.get('detail')}.\n"
                f"FastAPI runs the whole request INSIDE this generator's `yield`, so a "
                f"framework `HTTPException(401/404/422/…)` raised downstream is caught by "
                f"the broad `except` and re-raised as a 500 — masking every intended 4xx on "
                f"every endpoint that depends on it.\n"
                f"Repair: let framework HTTPExceptions propagate UNCHANGED. Either drop the "
                f"broad try/except entirely (the plain `async with async_session() as "
                f"session: yield session` is correct), or re-raise HTTPException first "
                f"(`except HTTPException: raise`) and only map genuinely-unexpected errors — "
                f"prefer catching a specific `SQLAlchemyError` rather than broad `Exception`. "
                f"NEVER turn a caught exception into `HTTPException(500)` unconditionally."
            )
    return "\n".join(parts)


# ---------------------------------------------------------------- frontend completeness
# TRUNCATION (project 1007): the generated `admin/menu/review/page.tsx` was cut off
# mid-JSX (LLM output hit its length limit), leaving `styles`/`inputStyle` undefined
# and the component unclosed — invalid TSX. It passed the build and QA (whose full
# `next build` is opt-in and off) and only died at the deploy's real `next build`.
# There is no Node toolchain at build time, so instead of SWC/tsc we parse the file
# STRUCTURALLY in Python: strip comments / strings / template-literals / regex
# literals, then check that {}()[] are balanced and no string/comment is left open.
# A truncated file leaves unclosed openers or an unterminated string — caught here,
# before the security review, deploy, or a human ever sees it.
_FRONTEND_CODE_EXT = (".tsx", ".ts", ".jsx", ".js", ".mjs", ".cjs")
_REGEX_PREV_CHARS = set("([{,;=:?!&|^~%*+-<>")
_REGEX_PREV_WORDS = {"return", "typeof", "instanceof", "in", "of", "case", "do",
                     "else", "yield", "await", "void", "delete", "throw", "new"}


def _regex_context(out: list) -> bool:
    """Is a `/` here the start of a regex literal (vs a division operator)? Standard
    heuristic: regex follows an operator/opening-delimiter or a regex-context keyword;
    division follows a value/identifier/closing-delimiter."""
    j = len(out) - 1
    while j >= 0 and out[j] in " \t\r\n":
        j -= 1
    if j < 0:
        return True
    c = out[j]
    if c in _REGEX_PREV_CHARS:
        return True
    if c.isalnum() or c == "_":
        k = j
        while k >= 0 and (out[k].isalnum() or out[k] == "_"):
            k -= 1
        return "".join(out[k + 1:j + 1]) in _REGEX_PREV_WORDS
    return False


def _strip_code(src: str) -> tuple[str, bool]:
    """(structural code with comments/strings/template-literals/regex removed, ok).
    ok is False if the source ended INSIDE an unterminated string or block comment —
    itself a truncation signal."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            i += 2
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and nxt == "*":
            i += 2
            while i < n and not (src[i] == "*" and i + 1 < n and src[i + 1] == "/"):
                i += 1
            if i >= n:
                return "".join(out), False           # unterminated block comment
            i += 2
            continue
        if c in ("'", '"', "`"):
            i += 1
            while i < n and src[i] != c:
                i += 2 if src[i] == "\\" else 1
            if i >= n:
                return "".join(out), False           # unterminated string/template
            i += 1
            continue
        if c == "/" and _regex_context(out):
            start = i
            i += 1
            in_class, closed = False, False
            while i < n and src[i] != "\n":
                ch = src[i]
                if ch == "\\":
                    i += 2
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    i += 1
                    closed = True
                    break
                i += 1
            if not closed:                            # not a regex after all -> division
                out.append("/")
                i = start + 1
            continue
        out.append(c)
        i += 1
    return "".join(out), True


def frontend_incomplete(rel: str, content: str) -> str | None:
    """Reason string if a generated JS-family frontend file (`rel` ends .tsx/.ts/...)
    looks TRUNCATED or structurally invalid — an unterminated string/comment or
    unbalanced {}()[] (project 1007's cut-off review page). None for a complete file
    or a non-JS file. Deterministic, no Node needed."""
    if not rel.endswith(_FRONTEND_CODE_EXT):
        return None
    code, ok = _strip_code(content or "")
    if not ok:
        return "truncated — ends inside an unterminated string or comment"
    close_of = {"}": "{", ")": "(", "]": "["}
    opens = {"{", "(", "["}
    stack = []
    for ch in code:
        if ch in opens:
            stack.append(ch)
        elif ch in close_of and stack and stack[-1] == close_of[ch]:
            stack.pop()
        # a stray closer with no opener is ignored (regex/edge tolerance)
    if stack:
        return (f"truncated/incomplete — {len(stack)} unclosed "
                f"{'/'.join(sorted(set(stack)))} at end of file")
    return None


# ---------------------------------------------------------------- frontend deps + CSS-leak
# NPM DEPENDENCY COMPLETENESS (run 1614): payment/page.tsx did `import debounce from
# 'lodash.debounce'`, but lodash.debounce was never added to package.json, so
# `next build` died with "Module not found". The Python analogue of the assembly's
# third-party install: every BARE import a frontend file makes must be a declared
# dependency. Deterministic, no Node needed.
_IMPORT_FROM_RE = re.compile(r"""import\s+(?:[^'"]+?\s+from\s+)?['"]([^'"]+)['"]""")
_REQUIRE_RE = re.compile(r"""(?:require|import)\(\s*['"]([^'"]+)['"]\s*\)""")


def _pkg_of_specifier(spec: str) -> str | None:
    """The npm PACKAGE name a bare import specifier resolves to, or None for a local/
    alias import. `lodash/debounce` -> `lodash`; `lodash.debounce` -> `lodash.debounce`
    (a distinct package); `@scope/pkg/sub` -> `@scope/pkg`; `./x`, `/x`, `@/x` -> None."""
    if not spec or spec[0] in "./" or spec.startswith("@/"):
        return None                      # relative, absolute, or Next '@/' path alias
    parts = spec.split("/")
    if spec.startswith("@"):
        return "/".join(parts[:2]) if len(parts) >= 2 else None
    return parts[0]


def frontend_import_packages(content: str) -> set[str]:
    """The set of npm PACKAGE names a frontend file imports (bare specifiers only)."""
    out: set[str] = set()
    for m in _IMPORT_FROM_RE.finditer(content or ""):
        pkg = _pkg_of_specifier(m.group(1))
        if pkg:
            out.add(pkg)
    for m in _REQUIRE_RE.finditer(content or ""):
        pkg = _pkg_of_specifier(m.group(1))
        if pkg:
            out.add(pkg)
    return out


def _declared_dependencies(package_json: str) -> set[str]:
    try:
        pj = json.loads(package_json or "{}")
    except (ValueError, TypeError):
        return set()
    deps: set[str] = set()
    for k in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        v = pj.get(k)
        if isinstance(v, dict):
            deps |= set(v.keys())
    return deps


def frontend_missing_deps(files: list[dict]) -> list[str]:
    """Bare npm packages imported by the frontend but NOT declared in package.json
    (run 1614: `lodash.debounce`). Sorted, deduped. Empty if there is no package.json
    (a different, missing-file problem) or nothing is missing. Node built-ins are not
    importable in a browser bundle, so they are treated as real missing deps too."""
    pkg_json = None
    imported: set[str] = set()
    for f in files:
        rel = f.get("filepath") or f.get("filename") or ""
        if rel.endswith("package.json"):
            pkg_json = f.get("content") or ""
        elif rel.endswith(_FRONTEND_CODE_EXT):
            imported |= frontend_import_packages(f.get("content") or "")
    if pkg_json is None:
        return []
    declared = _declared_dependencies(pkg_json)
    return sorted(imported - declared)


# CSS-IN-TSX (run 1614): app/page.tsx appended raw CSS after the component —
# `.container { max-width: 640px; }` at module top level — a JS SyntaxError
# ("Expression expected") that only `next build` (Node) catches, NOT the balance check
# above. Signal: at brace-depth 0, a `.class`/`#id` SELECTOR immediately followed by
# `{`. That is always invalid JS (a statement can't start with `.`), and a JS method
# chain (`obj\n  .then(...)`) never has `{` right after the selector — so this does not
# false-positive on fluent chains.
_CSS_SELECTOR_RE = re.compile(
    r"[.#][A-Za-z][\w-]*(?:\s*[,>+~]\s*[.#]?[A-Za-z][\w-]*)*\s*$")


def frontend_css_leak(rel: str, content: str) -> str | None:
    """Reason if a JS-family frontend file has raw CSS at the TOP LEVEL (run 1614's
    page.tsx). Strips strings/comments first (so CSS inside a template literal / a
    styled-component is NOT flagged), then flags a `.`/`#` CSS selector followed by `{`
    at brace-depth 0 — invalid JS that only `next build` would otherwise catch."""
    if not rel.endswith(_FRONTEND_CODE_EXT):
        return None
    code, _ok = _strip_code(content or "")
    depth = 0
    seg_start = 0
    for i, ch in enumerate(code):
        if ch == "{":
            if depth == 0:
                # The would-be "selector" is the text since the last statement boundary.
                seg = re.split(r"[;{}]", code[seg_start:i])[-1]
                seg = seg.strip().splitlines()[-1].strip() if seg.strip() else ""
                if _CSS_SELECTOR_RE.fullmatch(seg):
                    return (f"raw CSS at top level — `{seg} {{ … }}` is not valid "
                            f"JS/TSX (put styles in a .css/.module.css file or a style "
                            f"object). `next build` fails with 'Expression expected'.")
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
            seg_start = i + 1
        elif ch == ";" and depth == 0:
            seg_start = i + 1
    return None


# FRONTEND LOGIN MISSING (run 1614): the app deployed live, the backend correctly
# returned 401 on every protected endpoint, but the generated frontend implemented NO
# login flow (no Auth0 sign-in, no token) — so every gated feature was a dead 401 and the
# app was unusable. Deterministic whole-app check: if the BACKEND gates endpoints (a real
# auth dependency) AND there is a web frontend, the frontend MUST show login evidence.
_AUTH_DEP_RE = re.compile(r"Depends\(\s*get_current_\w+")
# Genuine login evidence: Auth0 SDK usage OR attaching a Bearer token to API calls.
# Deliberately NOT `/authorize` — Stripe Connect uses that URL too (false positive).
_LOGIN_EVIDENCE_RE = re.compile(
    r"@auth0/|loginWithRedirect|Auth0Provider|getAccessTokenSilently|useAuth0|"
    r"Bearer\s|Bearer\$|Authorization[\"'`]?\s*:", re.I)


def frontend_missing_login(files: list[dict]) -> str | None:
    """Reason if the backend gates endpoints (auth required) but NO frontend file
    implements a login flow (run 1614) — so a user can never authenticate and every
    protected feature is an unreachable 401. None if there is no gated backend, no web
    frontend, or the frontend does implement login. Deterministic, no Node needed."""
    backend_gated = any(
        (f.get("filepath") or f.get("filename") or "").endswith(".py")
        and _AUTH_DEP_RE.search(f.get("content") or "")
        for f in files)
    if not backend_gated:
        return None
    fe = [f for f in files
          if (f.get("filepath") or f.get("filename") or "").endswith(_FRONTEND_CODE_EXT)]
    if not fe:
        return None                                   # no web frontend -> not applicable
    if any(_LOGIN_EVIDENCE_RE.search(f.get("content") or "") for f in fe):
        return None                                   # a login flow is present
    return ("the backend gates endpoints (auth required) but the frontend implements NO "
            "login flow — no Auth0 sign-in and no Authorization: Bearer token — so a user "
            "can never authenticate and every protected feature returns 401. Add a login "
            "flow (Auth0 via @auth0/auth0-react using NEXT_PUBLIC_AUTH0_*), wrap the app in "
            "Auth0Provider, and attach the access token to protected API calls.")


def _stub(agent_type: str, ticket: dict) -> dict:
    """Placeholder when generation produced NOTHING usable — the LLM was
    unavailable (e.g. a provider quota outage) or returned nothing on every
    attempt. This is NOT the same as `needs_review`, where a real file was
    generated but failed self-review; this file is pure TODO text and is not
    even valid code. Carries STUB_STATUS so the build stage can refuse to call a
    run 'built' when any ticket produced no code — see developers/orchestrator."""
    fn = f"{ticket.get('id', 'ticket').lower()}.txt"
    return {
        "filename": fn,
        "filepath": f"{agent_type}/{fn}",
        "content": f"// TODO ({agent_type}): {ticket.get('title')}\n"
                   f"// {ticket.get('description')}\n",
    }


async def build_ticket(
    ticket: dict, model: str, existing: list[dict], contract: str = "", repair: str = ""
) -> dict:
    """Run the 5-step process for one ticket. Returns a file dict with a
    'status' of 'generated' or 'needs_review'.

    `repair` (optional) is a targeted, structured repair instruction from the build
    gate — e.g. an IMPORT_RESOLUTION_FAILURE (fix #16). When present it is prepended
    to the prompt for every attempt of THIS invocation, so a re-generation fixes the
    exact deterministic finding instead of blindly rewriting the file."""
    agent_type = ticket.get("assigned_to", "backend")
    prompt = _base_prompt(ticket, existing, contract)
    if repair:
        prompt += repair
    last: dict | None = None

    for attempt in range(1, MAX_TRIES + 1):
        if attempt == 2:
            prompt += "\nThe previous attempt was insufficient — take a DIFFERENT approach."
        elif attempt == 3:
            prompt += "\nProduce a MINIMAL but working version that covers the core of the ticket."

        file = await _generate(agent_type, model, prompt)
        if file is None:
            continue  # generation failed -> retry
        file = _pin_path(file, ticket)
        last = file
        ok, issues = await _self_review(model, ticket, file)
        if ok:
            return {**file, "agent_type": agent_type, "ticket_id": ticket.get("id"),
                    "status": "generated"}
        prompt += f"\nReviewer feedback: {issues}"

    # Exhausted retries — never silently fail.
    if last is not None:
        return {**last, "agent_type": agent_type, "ticket_id": ticket.get("id"),
                "status": "needs_review"}
    stub = _pin_path(_stub(agent_type, ticket), ticket)
    return {**stub, "agent_type": agent_type, "ticket_id": ticket.get("id"),
            "status": STUB_STATUS}
