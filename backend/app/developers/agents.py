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
    ) if agent_type == "backend" else ""
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
        + backend_rule
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


def build_symbol_index(project_files: list[dict]) -> dict:
    """Build the in-project symbol index once for a whole build, then reuse it for
    every file (see `import_symbol_mismatches`). Structure:
      - modules: dotted module path -> source content (both spellings; __init__ maps
        to its package path)
      - all_paths: every dotted module/package path that exists (for submodule imports)
      - auth_present: whether an auth.py was actually generated
    """
    modules: dict[str, str] = {}
    all_paths: set[str] = set()
    auth_present = False
    for f in project_files:
        fp = (f.get("filepath") or f.get("filename") or "")
        if not fp.endswith(".py"):
            continue
        aliases, _is_pkg = _dotted_aliases(fp)
        content = f.get("content") or ""
        for a in aliases:
            modules[a] = content
            all_paths.add(a)
        if any(a in _AUTH_ALIASES for a in aliases):
            auth_present = True
    return {"modules": modules, "all_paths": all_paths, "auth_present": auth_present}


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
            avail = ", ".join(r.get("available") or []) or "(none — the module exports nothing)"
            parts.append(
                f"\nModule: {r['module']}\n"
                f"Requested symbol (does NOT exist): {r['symbol']}  (line {r.get('line')})\n"
                f"Available symbols in that module: {avail}\n"
                f"Repair: import one of the available symbols above, or implement the needed "
                f"behaviour INLINE in this file. Do NOT invent a symbol the module does not "
                f"export, and do NOT modify the imported module."
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
