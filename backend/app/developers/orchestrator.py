"""Parallel Developer-agent orchestrator (Week 4).

Runs the blueprint's sprint tickets in dependency order using asyncio:
tickets whose dependencies are all satisfied run SIMULTANEOUSLY; tickets
that depend on others wait for those first. Each finished file is stored
in generated_files; pipeline_status tracks the build stage.
"""
import asyncio
import logging
from datetime import datetime, timezone

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

    lines.append(
        "\nMODULE LAYOUT (import from these — never redefine):\n"
        "  - backend/app/models.py     -> ALL SQLAlchemy models (import them)\n"
        "  - backend/app/database.py   -> Base, async_session, get_db (import them)\n"
        "  - backend/app/integrations/ -> third-party service wrappers\n"
        "  - frontend/app/<route>/page.tsx -> Next.js App Router pages\n"
        "  - mobile/src/screens/       -> React Native screens\n"
        "RULES: backend is FastAPI + async SQLAlchemy (never Flask). Read all "
        "secrets from environment variables. Only import packages that really "
        "exist. Do NOT redefine models or the DB session — import them."
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


async def run(project_id: int, blueprint: dict) -> None:
    """Build all tickets. Records a pipeline_status 'building' stage."""
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

        async with async_session() as db:
            st = await db.get(PipelineStatus, stage_id)
            st.status = "done"
            st.completed_at = datetime.now(timezone.utc)
            project = await db.get(Project, project_id)
            if project is not None:
                project.status = "built"
            await db.commit()
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
