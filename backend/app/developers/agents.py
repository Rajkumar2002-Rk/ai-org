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
    ) if agent_type == "backend" else ""
    return (
        f"You are a senior {agent_type} developer. Generate ONE complete, "
        f"production-quality code file for the given ticket. Stack: "
        f"{_STACK.get(agent_type, 'the project stack')} Write it in order: a "
        f"clear skeleton, then the real logic, then error handling. Include "
        f"input validation and sensible error handling. You MUST obey the "
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
    ticket: dict, model: str, existing: list[dict], contract: str = ""
) -> dict:
    """Run the 5-step process for one ticket. Returns a file dict with a
    'status' of 'generated' or 'needs_review'."""
    agent_type = ticket.get("assigned_to", "backend")
    prompt = _base_prompt(ticket, existing, contract)
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
