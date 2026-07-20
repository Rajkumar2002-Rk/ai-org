"""Runs the Code Reviewer over every generated file and issues a security
certificate. Records a pipeline_status 'security_review' stage."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session
from app.models import CodeReview, GeneratedFile, PipelineStatus, Project
from app.reviewer import reviewer

logger = logging.getLogger("reviewer.orchestrator")

# Limit concurrency — Opus is rate-limited and expensive.
_CONCURRENCY = 3


async def run(project_id: int, blueprint: dict) -> dict:
    """Review all files; return the security certificate."""
    general_model = blueprint.get("llm_routing", {}).get("code_reviewer", "gpt-4o-mini")

    async with async_session() as db:
        stage = PipelineStatus(project_id=project_id, stage="security_review", status="running")
        db.add(stage)
        result = await db.execute(
            select(GeneratedFile.id, GeneratedFile.filename, GeneratedFile.filepath,
                   GeneratedFile.content, GeneratedFile.agent_type, GeneratedFile.ticket_id)
            .where(GeneratedFile.project_id == project_id).order_by(GeneratedFile.id)
        )
        files = [
            {"id": r[0], "filename": r[1], "filepath": r[2], "content": r[3],
             "agent_type": r[4], "ticket_id": r[5]}
            for r in result.all()
        ]
        await db.commit()
        await db.refresh(stage)
        stage_id = stage.id

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(f):
        async with sem:
            return await reviewer.review_file(f, general_model)

    total_found = total_fixed = 0
    all_secure = True
    try:
        reviews = await asyncio.gather(*[_one(f) for f in files])
        async with async_session() as db:
            for rev in reviews:
                total_found += rev["issues_found"]
                total_fixed += rev["issues_fixed"]
                all_secure = all_secure and rev["security_passed"]
                db.add(CodeReview(
                    project_id=project_id,
                    file_id=rev["file_id"],
                    issues_found=rev["issues_found"],
                    issues_fixed=rev["issues_fixed"],
                    security_passed=rev["security_passed"],
                    reviewed_by_model=rev["reviewed_by_model"],
                ))
                if rev["new_content"] is not None:
                    gf = await db.get(GeneratedFile, rev["file_id"])
                    if gf is not None:
                        gf.content = rev["new_content"]
            st = await db.get(PipelineStatus, stage_id)
            st.status = "done" if all_secure else "error"
            st.completed_at = datetime.now(timezone.utc)
            if not all_secure:
                st.error_message = "Critical security issue could not be auto-resolved"
            project = await db.get(Project, project_id)
            if project is not None:
                project.status = "secured" if all_secure else "security_blocked"
            await db.commit()
    except Exception as exc:  # pragma: no cover
        logger.exception("Security review failed for project %s", project_id)
        async with async_session() as db:
            st = await db.get(PipelineStatus, stage_id)
            if st is not None:
                st.status = "error"
                st.error_message = str(exc)
                st.completed_at = datetime.now(timezone.utc)
                await db.commit()
        raise

    return {
        "passed": all_secure,
        "model_used": reviewer.SECURITY_MODEL,
        "issues_found": total_found,
        "issues_fixed": total_fixed,
        "files_reviewed": len(files),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
