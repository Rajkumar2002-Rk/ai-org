"""Parallel Developer-agent orchestrator (Week 4).

Runs the blueprint's sprint tickets in dependency order using asyncio:
tickets whose dependencies are all satisfied run SIMULTANEOUSLY; tickets
that depend on others wait for those first. Each finished file is stored
in generated_files; pipeline_status tracks the build stage.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select

from app import usage
from app.database import async_session
from app.developers import agents
from app.models import GeneratedFile, PipelineStatus, Project

logger = logging.getLogger("developers.orchestrator")


def _model_for(ticket: dict, routing: dict) -> str:
    key = f"{ticket.get('assigned_to', 'backend')}_developer"
    return routing.get(key, "gpt-4o")


def _contract_text(blueprint: dict) -> str:
    """The binding interface contract every Developer agent must build against.

    Freezing the Architect's schema + endpoints + module layout is what stops
    agents inventing their own field names and imports.
    """
    lines = ["=== BINDING PROJECT CONTRACT — follow EXACTLY, do not invent ==="]

    lines.append("\nDATABASE SCHEMA (use these exact table & column names):")
    for t in blueprint.get("database_schema", []):
        cols = ", ".join(
            f"{c.get('name')}:{c.get('type')}" for c in t.get("columns", [])
        )
        lines.append(f"  - table {t.get('table')}({cols})")
        for rel in t.get("relationships", []) or []:
            lines.append(f"      relationship: {rel}")

    lines.append("\nAPI ENDPOINTS (use these exact methods & paths):")
    for e in blueprint.get("api_endpoints", []):
        lines.append(f"  - {e.get('method')} {e.get('path')} — {e.get('purpose')}")

    # A CONCRETE map of every module that will exist in this project, at its
    # EXACT assigned path. The old contract described the layout generically
    # ("integrations/ -> third-party wrappers"), so a router guessed
    # `backend.app.integrations.stripe` while the real file was the slug
    # `integrations/integrate_stripe_connect_for_payments.py` — the app failed to
    # boot on ModuleNotFoundError. Filepaths are assigned deterministically by
    # architect.builder._assign_filepaths BEFORE this runs, so the exact path of
    # every module is known and can be declared. This closes the whole family of
    # cross-file import mismatches: no agent has to guess another module's path.
    backend_mods, frontend_mods = [], []
    for t in blueprint.get("sprint_tickets", []):
        fp = (t.get("filepath") or "").strip()
        if not fp:
            continue
        purpose = (t.get("title") or t.get("id") or "").strip()
        if fp.endswith(".py"):
            dotted = fp[:-3].replace("/", ".")
            backend_mods.append(f"  - {dotted}  ->  {purpose}")
        else:
            frontend_mods.append(f"  - {fp}  ->  {purpose}")

    lines.append(
        "\nGENERATED MODULE MAP — these are the ONLY modules this project has, "
        "each at its EXACT import path. To use another part of the project, "
        "import it from the EXACT path listed here.")
    if backend_mods:
        lines.append("Backend (import as e.g. `from <dotted.path> import ...`):")
        lines.extend(backend_mods)
    if frontend_mods:
        lines.append("Frontend/mobile files:")
        lines.extend(frontend_mods)

    lines.append(
        "\nIMPORT RULES — the app fails to boot if these are broken:\n"
        "  - NEVER import a module path that is not in the map above. In "
        "particular do NOT assume conventional names like "
        "`backend.app.integrations.stripe` or `backend.app.routes.menu` — use "
        "the EXACT paths listed, which are longer/less obvious.\n"
        "  - If functionality you need is not covered by any module in the map, "
        "implement it INLINE in your own file. Never import a module that is not "
        "in the map.\n"
        "  - backend/app/models.py has ALL SQLAlchemy models and "
        "backend/app/database.py has Base, async_session and get_db — import "
        "them, never redefine them.\n"
        "  - backend is FastAPI + async SQLAlchemy (never Flask). Read all "
        "secrets from environment variables. Only import third-party packages "
        "that really exist on PyPI/npm."
    )
    return "\n".join(lines)


def _waves(tickets: list[dict]) -> list[list[dict]]:
    """Group tickets into dependency waves (each wave runs in parallel).

    Foundation (FND-*) always runs first so its real code can be handed to
    every later agent.
    """
    foundation = [t for t in tickets if str(t.get("id", "")).startswith("FND-")]
    rest = [t for t in tickets if not str(t.get("id", "")).startswith("FND-")]
    waves: list[list[dict]] = []
    done: set = set()
    if foundation:
        waves.append(foundation)
        done.update(t.get("id") for t in foundation)

    by_id = {t.get("id"): t for t in rest}
    remaining = list(rest)
    while remaining:
        ready = [
            t for t in remaining
            # a dependency we don't know about is treated as satisfied
            if all(dep in done or dep not in by_id for dep in (t.get("dependencies") or []))
        ]
        if not ready:  # dependency cycle / unresolved -> run the rest anyway
            ready = remaining
        waves.append(ready)
        for t in ready:
            done.add(t.get("id"))
        remaining = [t for t in remaining if t not in ready]
    return waves


def _collect_stubs(built: list, blueprint: dict, project_id: int) -> list:
    """Return the built results the build gate rejects — a file that is not really
    'built'. Beyond a whole-file placeholder, three real-code-but-wrong problems
    (all found only late, some only over real HTTP) are caught here and marked
    STUB_STATUS so they flow through the same retry-then-fail gate:

      * a CORE work function left unimplemented (888: `parse_menu_items` = `return []`
        → extraction did nothing while endpoints answered 200);
      * `Depends(async_session)` instead of `Depends(get_db)` (888: every request 422s);
      * a generated model that renamed a contract column (888: schema `source` became
        `source_name` → a 500 once rows exist);
      * a TRUNCATED/invalid frontend file (1007: `admin/menu/review/page.tsx` was cut
        off mid-JSX → the deploy's `next build` failed four stages later);
      * an import of a symbol a real in-project module does NOT export (fix #16 —
        1038: `from backend.app.auth import require_admin`, but auth exports only
        get_current_user/get_current_admin_user → ImportError at boot);
      * a backend `.py` that does not PARSE at all (fix #17 — 1071: `order_be_3.py` put a
        non-default parameter after a defaulted one → hard SyntaxError, app never boots);
      * a `get_db`-style dependency generator whose broad `except` around its `yield`
        re-raises framework HTTPExceptions as a 500 (fix #24 — 1289: every 401/404/422 on
        every DB endpoint became "Internal server error").
      The failure is attached STRUCTURALLY (`syntax_error` / `symbol_repairs`) so the
      retry can repair it precisely.
    """
    schema = (blueprint or {}).get("database_schema") or []
    # Build the in-project symbol table ONCE from the whole file set, then resolve
    # every backend file's imports against it (fix #16).
    sym_index = agents.build_symbol_index(built)
    for r in built:
        if r.get("status") == agents.STUB_STATUS:
            continue
        content = r.get("content") or ""
        rel = r.get("filepath") or r.get("filename") or ""
        problems = []
        # Syntax FIRST — an unparseable file blocks every other check (and the other
        # AST detectors already no-op on a SyntaxError), so it must own the finding.
        syn = agents.python_syntax_error(content, rel)
        if syn:
            r["syntax_error"] = syn
            problems.append(
                f"python syntax error (line {syn.get('line')}): {syn.get('message')}")
        stub_fns = agents.stub_functions(content)
        if stub_fns:
            problems.append(f"placeholder work function(s) {stub_fns}")
        if agents.bad_session_dependency(content):
            problems.append("Depends(async_session) — must be Depends(get_db)")
        if "__tablename__" in content:
            miss = agents.model_schema_mismatches(content, schema)
            if miss:
                problems.append(f"model renamed/omitted contract column(s) {miss}")
        fe = agents.frontend_incomplete(rel, content)
        if fe:
            problems.append(f"frontend file {fe}")
        sym = agents.import_symbol_mismatches(content, rel, sym_index)
        if sym:
            r["symbol_repairs"] = sym
            problems.append("unresolved import symbol(s) " + ", ".join(
                f"{s['module']}.{s['symbol']}" for s in sym))
        attr = agents.attribute_access_mismatches(content, rel, sym_index)
        if attr:
            r["attribute_repairs"] = attr
            problems.append("unresolved attribute access " + ", ".join(
                f"{a['class']}.{a['attribute']}" for a in attr))
        hx = agents.http_exception_swallow(content, rel)
        if hx:
            r["http_swallow_repairs"] = hx
            problems.append("dependency generator swallows HTTPException into 500 " +
                            ", ".join(f"{h['function']}()" for h in hx))
        if problems:
            r["status"] = agents.STUB_STATUS
            r["gate_problems"] = problems
            logger.warning("Build %s: ticket %s rejected by the build gate: %s",
                           project_id, r.get("ticket_id"), "; ".join(problems))
    return [r for r in built if r.get("status") == agents.STUB_STATUS]


async def repair_import_errors(project_id: int, blueprint: dict,
                               import_errors: list[dict]) -> bool:
    """Regenerate the file(s) with a wrong THIRD-PARTY import path/symbol (run 1496:
    `from stripe.api_resources import PaymentIntent`), using a targeted repair, and
    persist. Returns True if any file was rewritten. Runs AFTER smoke_boot (the venv
    is where the error is detectable); the caller bounds the retries. Mirrors the
    _collect_stubs flag→structured-repair→retry pattern, but for the venv-only class."""
    if not import_errors:
        return False
    from app.qa import assembly as qa_assembly  # local: avoid a load cycle
    tickets = blueprint.get("sprint_tickets", [])
    routing = blueprint.get("llm_routing", {})
    contract = _contract_text(blueprint)

    async with async_session() as db:
        rows = (await db.execute(select(GeneratedFile).where(
            GeneratedFile.project_id == project_id))).scalars().all()
        existing = [{"ticket_id": r.ticket_id, "filename": r.filename,
                     "filepath": r.filepath, "content": r.content,
                     "agent_type": r.agent_type} for r in rows]

    by_file: dict[str, list] = {}
    for e in import_errors:
        by_file.setdefault(e["file"], []).append(e)

    def _ticket_for(path: str):
        for t in tickets:
            if (t.get("filepath") or "") == path:
                return t
        for t in tickets:
            tp = t.get("filepath") or ""
            if tp and (tp.endswith(path) or path.endswith(tp)):
                return t
        return None

    changed = False
    for filepath, errs in by_file.items():
        ticket = _ticket_for(filepath)
        if ticket is None:
            logger.warning("Import-repair: no ticket owns %s (project %s)",
                           filepath, project_id)
            continue
        reasons = "\n".join(qa_assembly._import_error_reason(e) for e in errs)
        repair = ("\n=== THIRD_PARTY_IMPORT — repair ONLY this file, do not touch any "
                  "other file ===\n" + reasons + "\nRepair: import each symbol from the "
                  "package's correct PUBLIC location — usually the package top level "
                  "(e.g. `from stripe import PaymentIntent`), NOT a guessed internal "
                  "submodule. Keep the file's behaviour and public names unchanged.")
        new = await agents.build_ticket(ticket, _model_for(ticket, routing),
                                        existing, contract, repair)
        if not new or new.get("status") == agents.STUB_STATUS or not new.get("content"):
            continue
        tid = new.get("ticket_id") or ticket.get("id") or ""
        async with async_session() as db:
            row = (await db.execute(select(GeneratedFile).where(
                GeneratedFile.project_id == project_id,
                GeneratedFile.ticket_id == tid))).scalars().first()
            if row is not None:
                row.content = new["content"]
                row.status = new.get("status", "generated")
                await db.commit()
                changed = True
                logger.info("Import-repair: rewrote %s (ticket %s) for project %s",
                            filepath, tid, project_id)
        for e2 in existing:                       # reflect for the next file's context
            if e2.get("ticket_id") == tid:
                e2["content"] = new["content"]
    return changed


_ROUTE_DECORATOR_RE = re.compile(
    r"@\s*\w+\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]", re.I)
_ROUTER_PREFIX_RE = re.compile(
    r"APIRouter\([^)]*?prefix\s*=\s*['\"]([^'\"]+)['\"]", re.S)


def _routes_in(content: str) -> list[str]:
    """Full normalised route paths a generated file defines (decorator path with any
    APIRouter(prefix=...) prepended). Used to attribute a MISSING endpoint to the
    route file that already owns that resource."""
    from app.qa.assembly import _norm_path
    prefix_m = _ROUTER_PREFIX_RE.search(content or "")
    prefix = prefix_m.group(1).rstrip("/") if prefix_m else ""
    out = []
    for _method, path in _ROUTE_DECORATOR_RE.findall(content or ""):
        out.append(_norm_path(prefix + path))
    return out


def _shared_segments(a: str, b: str) -> int:
    sa, sb = a.strip("/").split("/"), b.strip("/").split("/")
    n = 0
    for x, y in zip(sa, sb):
        if x != y:
            break
        n += 1
    return n


async def repair_missing_endpoints(project_id: int, blueprint: dict,
                                   missing_paths: list[str]) -> bool:
    """Regenerate the route file(s) that SHOULD own a designed endpoint the booted app
    is missing (run 1557: GET /orders/{order_id} was never generated), instructing the
    developer to ADD the missing endpoint(s) while keeping the existing ones. Attributes
    each missing path to the route file sharing the longest path-prefix with it. Returns
    True if any file was rewritten. Caller bounds the retries."""
    if not missing_paths:
        return False
    from app.qa.assembly import _norm_path
    tickets = blueprint.get("sprint_tickets", [])
    routing = blueprint.get("llm_routing", {})
    contract = _contract_text(blueprint)
    endpoints = blueprint.get("api_endpoints", []) or []
    # path -> (method, purpose) from the design, so the repair is specific.
    meta = {_norm_path(e.get("path", "")): (e.get("method", ""), e.get("purpose", ""),
                                            e.get("path", ""))
            for e in endpoints}

    async with async_session() as db:
        rows = (await db.execute(select(GeneratedFile).where(
            GeneratedFile.project_id == project_id))).scalars().all()
        existing = [{"ticket_id": r.ticket_id, "filename": r.filename,
                     "filepath": r.filepath, "content": r.content,
                     "agent_type": r.agent_type} for r in rows]

    # Attribute each missing endpoint to the best-matching route file.
    route_files = [f for f in existing if (f.get("filepath") or "").endswith(".py")
                   and _routes_in(f.get("content") or "")]
    by_file: dict[str, list] = {}
    for mp in missing_paths:
        nmp = _norm_path(mp)
        best, best_score = None, 0
        for f in route_files:
            score = max((_shared_segments(nmp, r) for r in _routes_in(f["content"])),
                        default=0)
            if score > best_score or (score == best_score and score > 0 and best
                                      and len(_routes_in(f["content"]))
                                      < len(_routes_in(best["content"]))):
                best, best_score = f, score
        if best is not None and best_score > 0:
            by_file.setdefault(best["filepath"], []).append(mp)

    def _ticket_for(path: str):
        for t in tickets:
            if (t.get("filepath") or "") == path:
                return t
        return None

    changed = False
    for filepath, mps in by_file.items():
        ticket = _ticket_for(filepath)
        if ticket is None:
            continue
        lines = []
        for mp in mps:
            method, purpose, orig = meta.get(_norm_path(mp), ("", "", mp))
            lines.append(f"- {method or 'the designed method'} {orig or mp}"
                         + (f"  ({purpose})" if purpose else ""))
        repair = ("\n=== MISSING_ENDPOINT — repair ONLY this file, do not touch any "
                  "other file ===\nThe booted app is missing these designed endpoint(s), "
                  "which this file should serve:\n" + "\n".join(lines) +
                  "\nRepair: ADD the missing endpoint(s) with a real, working "
                  "implementation, keeping ALL existing endpoints and the same router. "
                  "Use the EXACT path shown (including the path parameter name).")
        new = await agents.build_ticket(ticket, _model_for(ticket, routing),
                                        existing, contract, repair)
        if not new or new.get("status") == agents.STUB_STATUS or not new.get("content"):
            continue
        tid = new.get("ticket_id") or ticket.get("id") or ""
        async with async_session() as db:
            row = (await db.execute(select(GeneratedFile).where(
                GeneratedFile.project_id == project_id,
                GeneratedFile.ticket_id == tid))).scalars().first()
            if row is not None:
                row.content = new["content"]
                row.status = new.get("status", "generated")
                await db.commit()
                changed = True
                logger.info("Endpoint-repair: rewrote %s to add %s (project %s)",
                            filepath, mps, project_id)
        for e2 in existing:
            if e2.get("ticket_id") == tid:
                e2["content"] = new["content"]
    return changed


async def run(project_id: int, blueprint: dict) -> dict:
    """Build all tickets. Records a pipeline_status 'building' stage.

    Returns {"status": "built"|"build_failed", "total": int, "stubbed": [ids]}.
    "build_failed" means at least one ticket produced only a placeholder stub —
    the caller MUST NOT report the build as done in that case (see _run_build).
    """
    # Attribute this stage's token spend (see app/usage.py).
    usage.set_run_context(project_id=project_id, stage="developers")
    tickets = blueprint.get("sprint_tickets", [])
    routing = blueprint.get("llm_routing", {})

    async with async_session() as db:
        stage = PipelineStatus(project_id=project_id, stage="building", status="running")
        db.add(stage)
        await db.commit()
        await db.refresh(stage)
        stage_id = stage.id

    contract = _contract_text(blueprint)
    built: list[dict] = []
    # Last line of defence against two tickets writing the same file. The
    # Architect now assigns unique paths and the Developer is pinned to them, but
    # a blueprint predating that fix — or a path arriving from anywhere else —
    # must still never silently destroy another ticket's work.
    owner_of: dict[str, str] = {}
    try:
        for wave in _waves(tickets):
            results = await asyncio.gather(
                *[
                    agents.build_ticket(t, _model_for(t, routing), built, contract)
                    for t in wave
                ]
            )
            async with async_session() as db:
                for r in results:
                    path = r.get("filepath") or r["filename"]
                    ticket_id = r.get("ticket_id") or ""
                    if owner_of.get(path, ticket_id) != ticket_id:
                        stem, dot, ext = path.rpartition(".")
                        moved = (f"{stem}_{ticket_id.lower()}.{ext}" if dot
                                 else f"{path}_{ticket_id.lower()}")
                        logger.warning(
                            "Ticket %s would have overwritten %s (owned by %s); "
                            "wrote %s instead — neither ticket's work is lost.",
                            ticket_id, path, owner_of[path], moved,
                        )
                        path = moved
                        r["filepath"] = path
                    owner_of[path] = ticket_id
                    db.add(GeneratedFile(
                        project_id=project_id,
                        ticket_id=ticket_id,
                        filename=path.rpartition("/")[2],
                        filepath=path,
                        content=r["content"],
                        agent_type=r.get("agent_type", "backend"),
                        status=r.get("status", "generated"),
                    ))
                await db.commit()
            built.extend(results)

        # A stub means a ticket produced NO code — the LLM was unavailable or
        # returned nothing on every attempt (this is how an OpenAI quota outage
        # once put 8 TODO-text files past the build stage, where Opus then
        # "certified" them and only QA caught it via syntax errors). A build
        # that is partly placeholder text has not been built, and must not flow
        # into the security review as if it had. Same rule as the driver's
        # require_done: an unknown/empty state must never read as success.
        stubbed = _collect_stubs(built, blueprint, project_id)

        # ONE targeted retry before giving up. A stub is usually a TRANSIENT
        # single-ticket generation flake — the model returned nothing usable on
        # every attempt for that one ticket — not a systemic outage. Aborting the
        # whole build on it discards ~19 good files to one ticket's bad luck
        # (real: a baseline run stubbed 1 of 20 and lost the run). Regenerate
        # ONLY the stubbed tickets once more, against the now-complete set of
        # sibling files. A stub that SURVIVES the retry still fails the build —
        # placeholder text is never certified.
        if stubbed:
            by_ticket = {t.get("id"): t for t in tickets}
            retry_ids = [str(r.get("ticket_id")) for r in stubbed]
            # A structured, targeted repair per stubbed ticket where the gate produced
            # one (fix #16). Blank for the other gate classes — build_ticket then falls
            # back to its ordinary retry guidance. This is what keeps a repair BOUNDED
            # and precise instead of the blind regenerate that broke 1038/1039.
            repair_by_ticket = {str(r.get("ticket_id")): agents.repair_instructions(r)
                                for r in stubbed}
            logger.warning("Build %s: %d stubbed ticket(s) %s — one retry pass "
                           "before aborting", project_id, len(stubbed), retry_ids)
            retry_tickets = [by_ticket[i] for i in retry_ids if i in by_ticket]
            retry_results = await asyncio.gather(*[
                agents.build_ticket(t, _model_for(t, routing), built, contract,
                                    repair_by_ticket.get(str(t.get("id")), ""))
                for t in retry_tickets
            ])
            async with async_session() as db:
                for r in retry_results:
                    if r.get("status") == agents.STUB_STATUS:
                        continue  # still nothing — leave the stub in place
                    tid = r.get("ticket_id") or ""
                    row = (await db.execute(select(GeneratedFile).where(
                        GeneratedFile.project_id == project_id,
                        GeneratedFile.ticket_id == tid))).scalars().first()
                    if row is not None:      # overwrite the stub with real code
                        row.content = r["content"]
                        row.status = r.get("status", "generated")
                    for b in built:          # reflect it in the in-memory set
                        if b.get("ticket_id") == tid:
                            b["content"] = r["content"]
                            b["status"] = r.get("status", "generated")
                    logger.info("Build %s: ticket %s recovered on retry", project_id, tid)
                await db.commit()
            stubbed = _collect_stubs(built, blueprint, project_id)

        async with async_session() as db:
            st = await db.get(PipelineStatus, stage_id)
            project = await db.get(Project, project_id)
            if stubbed:
                ids = ", ".join(sorted(str(r.get("ticket_id")) for r in stubbed))
                msg = (f"{len(stubbed)} of {len(built)} tickets produced no code "
                       f"(placeholder stubs): {ids}. The most common cause is an "
                       f"LLM provider outage/quota error. Not certifiable.")
                logger.error("Build for project %s incomplete — %s", project_id, msg)
                st.status = "error"
                st.error_message = msg
                if project is not None:
                    project.status = "build_failed"
            else:
                st.status = "done"
                if project is not None:
                    project.status = "built"
            st.completed_at = datetime.now(timezone.utc)
            await db.commit()

        return {
            "status": "build_failed" if stubbed else "built",
            "total": len(built),
            "stubbed": sorted(str(r.get("ticket_id")) for r in stubbed),
        }
    except Exception as exc:  # pragma: no cover
        logger.exception("Build failed for project %s", project_id)
        async with async_session() as db:
            st = await db.get(PipelineStatus, stage_id)
            if st is not None:
                st.status = "error"
                st.error_message = str(exc)
                st.completed_at = datetime.now(timezone.utc)
                await db.commit()
        raise
