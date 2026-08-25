"""Runs the Code Reviewer over every generated file and issues a security
certificate. Records a pipeline_status 'security_review' stage."""
import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app import usage
from app.database import async_session
from app.developers import agents as dev_agents
from app.models import CodeReview, GeneratedFile, PipelineStatus, Project
from app.reviewer import reviewer

logger = logging.getLogger("reviewer.orchestrator")


def _accept_or_reject_fix(gf, new_content: str, files: list[dict],
                          schema: list | None) -> str:
    """Re-validate an Opus security auto-fix BEFORE committing it (fix #42).

    The build gate already certified the ORIGINAL file as clean. If the security 'fix'
    REINTRODUCES a deterministic build-gate defect the original did not have (run 1914:
    Opus wrapped `get_db` in the fix-#24 HTTPException-swallow, turning every endpoint
    into a masked 500), keep the certified original rather than ship a security hardening
    that broke correctness. Returns the content to store."""
    fp = gf.filepath or gf.filename or ""
    new_problems = dev_agents.rewrite_integrity_gate(new_content, fp, files, schema, file_id=gf.id)
    if not new_problems:
        return new_content
    orig_problems = dev_agents.rewrite_integrity_gate(gf.content, fp, files, schema, file_id=gf.id)
    if not orig_problems:
        logger.warning("Reviewer: the security auto-fix for %s reintroduced a build-gate "
                       "defect (%s) the certified original did not have — KEEPING the "
                       "original.", fp, "; ".join(new_problems))
        return gf.content            # reject the unsafe fix
    return new_content               # original was already flawed; the fix is no worse

# Limit concurrency — Opus is rate-limited and expensive.
_CONCURRENCY = 3


def _hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()[:16]


async def file_hashes(project_id: int) -> dict[str, str]:
    """Content fingerprint per file, as of RIGHT NOW.

    Stored on the certificate so anyone can ask "does this certificate still
    describe what is on disk?" — drift is then detectable no matter which stage
    caused it, instead of relying on that stage to declare its own edits.
    """
    async with async_session() as db:
        rows = (await db.execute(
            select(GeneratedFile.id, GeneratedFile.content)
            .where(GeneratedFile.project_id == project_id)
        )).all()
    return {str(r[0]): _hash(r[1]) for r in rows}


async def drifted_files(project_id: int, cert: dict) -> list[int]:
    """File ids whose content no longer matches what the certificate covered.

    FAILS CLOSED. A certificate that carries no fingerprint cannot be shown to
    describe what is on disk, so every file is treated as drifted and re-reviewed
    rather than assumed clean. "We can't tell" must never resolve to "it's fine"
    for a security certificate.
    """
    if not cert:
        return []      # never certified at all — not this function's job
    current = await file_hashes(project_id)
    recorded = cert.get("file_hashes") or {}
    if not recorded:
        return sorted(int(fid) for fid in current)
    return sorted(int(fid) for fid, h in current.items() if recorded.get(fid) != h)


async def skipped_certificate(project_id: int) -> dict:
    """A NON-reviewed 'certificate' for the local codegen-debugging phase
    (`settings.security_review_enabled == False`). It runs NO LLM and makes NO
    security claim: `passed` is True only so the pipeline can proceed to QA/deploy
    LOCALLY, and `security_review_skipped` is set so no reader — or the frontend, or
    the DevOps gate — can mistake it for a real Opus certificate. It DOES carry the
    real `file_hashes` so the drift check still guarantees the deployed bytes are the
    ones QA saw; it just was not security-reviewed. Never produced for an AWS deploy
    (see `main._run_review`)."""
    return {
        "passed": True,
        "security_review_skipped": True,
        "model_used": "skipped (security_review_enabled=False, debug mode)",
        "issues_found": 0,
        "issues_fixed": 0,
        "files_reviewed": 0,
        "file_hashes": await file_hashes(project_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def review_subset(project_id: int, blueprint: dict,
                        file_ids: list[int]) -> dict:
    """Re-run the FULL two-pass review (incl. the always-Opus security pass) on
    a specific set of files.

    Exists because the security certificate must never describe code that no
    longer exists on disk. Any stage that rewrites a file AFTER certification
    (the QA agent's repair loop does) has to come back through here before the
    project may be called secured.
    """
    if not file_ids:
        return {"passed": True, "issues_found": 0, "issues_fixed": 0,
                "files_reviewed": 0}

    general_model = blueprint.get("llm_routing", {}).get("code_reviewer", "gpt-4o-mini")

    async with async_session() as db:
        result = await db.execute(
            select(GeneratedFile.id, GeneratedFile.filename, GeneratedFile.filepath,
                   GeneratedFile.content, GeneratedFile.agent_type, GeneratedFile.ticket_id)
            .where(GeneratedFile.project_id == project_id,
                   GeneratedFile.id.in_(file_ids))
            .order_by(GeneratedFile.id)
        )
        files = [
            {"id": r[0], "filename": r[1], "filepath": r[2], "content": r[3],
             "agent_type": r[4], "ticket_id": r[5]}
            for r in result.all()
        ]

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(f):
        async with sem:
            return await reviewer.review_file(f, general_model)

    reviews = await asyncio.gather(*[_one(f) for f in files])

    found = fixed = 0
    all_secure = True
    async with async_session() as db:
        for rev in reviews:
            found += rev["issues_found"]
            fixed += rev["issues_fixed"]
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
                    gf.content = _accept_or_reject_fix(
                        gf, rev["new_content"], files, (blueprint or {}).get("database_schema"))
        await db.commit()

    return {"passed": all_secure, "issues_found": found, "issues_fixed": fixed,
            "files_reviewed": len(files)}


async def run(project_id: int, blueprint: dict) -> dict:
    """Review all files; return the security certificate."""
    # Attribute this stage's token spend. The Opus half of the cost split is
    # identifiable by model_used regardless, but tagging makes the report
    # readable without relying on model names.
    usage.set_run_context(project_id=project_id, stage="reviewer")
    general_model = blueprint.get("llm_routing", {}).get("code_reviewer", "gpt-4o-mini")
    schema = (blueprint or {}).get("database_schema")

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
                        gf.content = _accept_or_reject_fix(
                            gf, rev["new_content"], files, schema)
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
        # Fingerprint of exactly the code this certificate attests to. If a
        # later stage rewrites a file, this stops matching and the drift is
        # detectable without that stage having to report it.
        "file_hashes": await file_hashes(project_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
