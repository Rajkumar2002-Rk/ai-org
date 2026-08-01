"""Documentation orchestrator (Week 8).

gather real facts (read-only) -> generate 4 documents -> store them in the
`documents` table. The ONLY thing this agent writes anywhere is `documents` rows;
it never touches code, certificates, or deployment state.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from app import usage
from app.database import async_session
from app.documentation import datasource, generators
from app.models import Document, Project

logger = logging.getLogger("documentation.orchestrator")

DOC_TYPES = ("user_guide", "demo_script", "maintenance_guide", "handoff_summary")


async def run(project_id: int) -> dict:
    """Generate + store the four documents for a project. Returns a plain summary
    for the completion screen (counts + honest status, no technical detail)."""
    run_id = uuid.uuid4().hex
    token = usage.set_run_context(run_id=run_id, project_id=project_id,
                                  stage="documentation")
    try:
        facts = await datasource.gather(project_id)

        # Generate (prose via Gemini + deterministic fallbacks; handoff is pure data).
        user_guide_md = await generators.user_guide(facts)
        demo_script_obj = await generators.demo_script(facts)
        maintenance_md = await generators.maintenance_guide(facts)
        handoff_obj = generators.handoff_summary(facts)

        contents = {
            "user_guide": user_guide_md,
            "demo_script": json.dumps(demo_script_obj, indent=2),
            "maintenance_guide": maintenance_md,
            "handoff_summary": json.dumps(handoff_obj, indent=2),
        }

        async with async_session() as db:
            for doc_type in DOC_TYPES:
                db.add(Document(project_id=project_id, doc_type=doc_type,
                                content=contents[doc_type]))
            await db.commit()

        dep = facts["deployment"]
        sec = facts["security"]
        qa = facts["qa"]
        # Completion-screen summary — real values only.
        return {
            "status": "done",
            "run_id": run_id,
            "documents_generated": list(DOC_TYPES),
            "business_name": facts["business_name"],
            "live_url": dep["live_url"] if dep else None,
            "is_live": bool(dep and dep["is_live"]),
            "security_passed": sec["passed"],
            "security_status": sec["status"],
            "tests_available": qa["available"],
            "tests_passed": qa["passed"],
            "tests_total": qa["total"],
            "tests_failed": qa["failed"],
            "monthly_cost_estimate": (dep["monthly_cost_estimate"] if dep else None),
            "cost_basis": dep["cost_basis"] if dep else None,
            "user_guide_ready": True,
            "demo_script_ready": True,
            "maintenance_guide_ready": True,
            "handoff_ready": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:  # pragma: no cover - never crash the pipeline
        logger.exception("Documentation run failed for project %s", project_id)
        return {"status": "error", "reason": str(exc)[:400], "run_id": run_id}
    finally:
        usage.reset_run_context(token)
