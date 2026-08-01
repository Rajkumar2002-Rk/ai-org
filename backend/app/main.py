import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import design_explain
from app.architect import graph as architect_graph
from app.ba import controller
from app.ba import graph
from app.ba import state as st
from app.database import async_session, engine, get_db
from app.developers import orchestrator
from app.models import (
    Blueprint,
    Conversation,
    Document,
    GeneratedFile,
    PipelineStatus,
    ProductReview,
    Project,
)
from app.product_intel import graph as pi_graph
from app.qa import graph as qa_graph
from app.reviewer import orchestrator as reviewer_orchestrator
from app.devops import graph as devops_graph
from app.documentation import graph as documentation_graph
from sqlalchemy import func as sqlfunc, select
from app.redis_client import redis_client
from app.schemas import (
    BuildStatusResponse,
    DeployStatusResponse,
    DocumentsStatusResponse,
    DesignExplanationResponse,
    SecurityStatusResponse,
    MessageRequest,
    MessageResponse,
    PipelineStartRequest,
    PipelineStatusResponse,
    QAStatusResponse,
    ResearchStatusResponse,
    ReviewResponse,
    StartResponse,
)

logger = logging.getLogger("app.main")


def _pipeline_key(project_id: int) -> str:
    return f"pipeline:status:{project_id}"


async def _run_pipeline(project_id: int, summary: dict) -> None:
    """Background job: run the Architect, store the blueprint, and prepare a
    plain-English design explanation for the user."""
    try:
        blueprint = await architect_graph.run(summary)
        async with async_session() as db:
            db.add(
                Blueprint(project_id=project_id, blueprint_json=json.dumps(blueprint))
            )
            project = await db.get(Project, project_id)
            if project is not None:
                project.status = "designed"
            await db.commit()
        # Plain-English "what we designed & why" for the collapsible message.
        explain = {
            "headline": design_explain.headline(summary),
            "explanation": await design_explain.explanation(summary, blueprint),
        }
        await redis_client.set(
            f"design_explain:{project_id}", json.dumps(explain), ex=86400
        )
        await redis_client.set(_pipeline_key(project_id), "done", ex=86400)
    except Exception:  # pragma: no cover
        logger.exception("Architect pipeline failed for project %s", project_id)
        await redis_client.set(_pipeline_key(project_id), "error", ex=86400)


async def _run_build(project_id: int) -> None:
    """Background job: run the Developer agents on the stored blueprint."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Blueprint.blueprint_json)
                .where(Blueprint.project_id == project_id)
                .order_by(Blueprint.id.desc()).limit(1)
            )
            row = result.first()
        if row is None:
            await redis_client.set(_build_key(project_id), "error", ex=86400)
            return
        blueprint = json.loads(row[0])
        summary = await orchestrator.run(project_id, blueprint)
        # A build where any ticket produced only a placeholder stub is NOT done —
        # reporting "done" would let a provider outage flow into the security
        # review as if real code had been generated.
        ok = (summary or {}).get("status") == "built"
        await redis_client.set(_build_key(project_id), "done" if ok else "error",
                               ex=86400)
    except Exception:  # pragma: no cover
        logger.exception("Developer build failed for project %s", project_id)
        await redis_client.set(_build_key(project_id), "error", ex=86400)


def _build_key(project_id: int) -> str:
    return f"build:status:{project_id}"


def _secure_key(project_id: int) -> str:
    return f"secure:status:{project_id}"


def _qa_key(project_id: int) -> str:
    return f"qa:status:{project_id}"


def _deploy_key(project_id: int) -> str:
    return f"deploy:status:{project_id}"


async def _run_deploy(project_id: int) -> None:
    """Background job: the DevOps agent (assemble -> build -> deploy -> health).

    Stores the full report and a status of live | failed | blocked. Runs
    silently; the API exposes only the live URL and counts.
    """
    try:
        report = await devops_graph.run(project_id)
        await redis_client.set(
            f"deploy_report:{project_id}", json.dumps(report), ex=86400
        )
        await redis_client.set(
            _deploy_key(project_id), report.get("status", "failed"), ex=86400
        )
    except Exception:  # pragma: no cover
        logger.exception("Deploy failed for project %s", project_id)
        await redis_client.set(_deploy_key(project_id), "failed", ex=86400)


def _document_key(project_id: int) -> str:
    return f"document:status:{project_id}"


async def _run_documentation(project_id: int) -> None:
    """Background job: the Documentation agent (read-only -> 4 documents).

    Reports real stored data only. Stores the completion-screen summary.
    """
    try:
        report = await documentation_graph.run(project_id)
        await redis_client.set(
            f"document_report:{project_id}", json.dumps(report), ex=86400
        )
        await redis_client.set(
            _document_key(project_id), report.get("status", "error"), ex=86400
        )
    except Exception:  # pragma: no cover
        logger.exception("Documentation failed for project %s", project_id)
        await redis_client.set(_document_key(project_id), "error", ex=86400)


async def _run_qa(project_id: int) -> None:
    """Background job: run the QA agent (assemble -> L1 + L2 -> root cause)."""
    try:
        report = await qa_graph.run(project_id)
        await redis_client.set(f"qa_report:{project_id}", json.dumps(report), ex=86400)
        await redis_client.set(
            _qa_key(project_id), "done" if report["all_passed"] else "error", ex=86400
        )
    except Exception:  # pragma: no cover
        logger.exception("QA run failed for project %s", project_id)
        await redis_client.set(_qa_key(project_id), "error", ex=86400)


async def _run_review(project_id: int) -> None:
    """Background job: run the Code Reviewer (general + Opus security passes)."""
    try:
        async with async_session() as db:
            row = (await db.execute(
                select(Blueprint.blueprint_json)
                .where(Blueprint.project_id == project_id)
                .order_by(Blueprint.id.desc()).limit(1)
            )).first()
        if row is None:
            await redis_client.set(_secure_key(project_id), "error", ex=86400)
            return
        blueprint = json.loads(row[0])
        certificate = await reviewer_orchestrator.run(project_id, blueprint)
        await redis_client.set(
            f"security_cert:{project_id}", json.dumps(certificate), ex=86400
        )
        await redis_client.set(
            _secure_key(project_id), "done" if certificate["passed"] else "error", ex=86400
        )
    except Exception:  # pragma: no cover
        logger.exception("Security review failed for project %s", project_id)
        await redis_client.set(_secure_key(project_id), "error", ex=86400)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await redis_client.ping()
    yield
    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(title="Autonomous AI Engineering Organization", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _log(db: AsyncSession, project_id: int, role: str, message: str) -> None:
    db.add(Conversation(project_id=project_id, role=role, message=message))
    await db.commit()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/conversation/start", response_model=StartResponse)
async def start_conversation(db: AsyncSession = Depends(get_db)):
    project = Project(prompt="(in progress)", status="gathering_requirements")
    db.add(project)
    await db.commit()
    await db.refresh(project)

    state = st.BAState(project_id=project.id)
    output = await graph.process_turn(state, message=None, is_first=True)
    await st.save(state)
    await _log(db, project.id, "ba", output["reply"])

    return StartResponse(
        project_id=project.id,
        reply=output["reply"],
        ui=output["ui"],
        stage=state.stage,
    )


@app.post("/conversation/message", response_model=MessageResponse)
async def conversation_message(
    req: MessageRequest, db: AsyncSession = Depends(get_db)
):
    state = await st.load(req.project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await _log(db, req.project_id, "user", req.message)

    output = await graph.process_turn(state, message=req.message)

    # Safety guardrail rejected the idea — mark the project and build nothing.
    if state.stage == st.BLOCKED and not state.fields.get("blocked_logged"):
        project = await db.get(Project, req.project_id)
        if project is not None:
            project.status = "rejected"
            await db.commit()
        state.fields["blocked_logged"] = True

    # On confirmation, lock requirements + design preferences into the DB —
    # exactly once, even if more messages arrive after the conversation ends.
    if (
        state.stage == st.DONE
        and state.fields.get("confirmed")
        and not state.fields.get("persisted")
    ):
        await controller.persist_on_confirm(db, state)
        state.fields["persisted"] = True

    await st.save(state)
    await _log(db, req.project_id, "ba", output["reply"])

    return MessageResponse(
        reply=output["reply"],
        ui=output["ui"],
        stage=state.stage,
        researching=output.get("researching", False),
    )


@app.get(
    "/conversation/{project_id}/research-status",
    response_model=ResearchStatusResponse,
)
async def research_status(project_id: int):
    return ResearchStatusResponse(ready=await controller.ci_ready(project_id))


@app.post("/pipeline/review", response_model=ReviewResponse)
async def pipeline_review(
    req: PipelineStartRequest, db: AsyncSession = Depends(get_db)
):
    """Product Intelligence review-gate: analyse the confirmed summary and
    return recommendations for the user to see before the Architect runs."""
    project = await db.get(Project, req.project_id)
    if project is None or not project.summary_json:
        raise HTTPException(
            status_code=400, detail="Project has no confirmed summary yet"
        )

    summary = json.loads(project.summary_json)
    review = await pi_graph.run(summary)

    # Refine the summary the Architect will read: keep only fitting features,
    # and carry priorities + missing essentials forward.
    summary["competitor_features"] = review.get(
        "features_kept", summary.get("competitor_features", [])
    )
    summary["priorities"] = review.get("priorities", {})
    summary["missing_essentials"] = review.get("missing_essentials", [])
    project.summary_json = json.dumps(summary)
    project.status = "reviewed"
    db.add(ProductReview(project_id=req.project_id, review_json=json.dumps(review)))
    await db.commit()

    return ReviewResponse(review=review)


@app.post("/pipeline/start", response_model=PipelineStatusResponse)
async def pipeline_start(
    req: PipelineStartRequest, db: AsyncSession = Depends(get_db)
):
    """Kick off the Architect for a confirmed project (runs in background)."""
    project = await db.get(Project, req.project_id)
    if project is None or not project.summary_json:
        raise HTTPException(
            status_code=400, detail="Project has no confirmed summary yet"
        )

    # Don't start a second run if one is already underway.
    if await redis_client.get(_pipeline_key(req.project_id)) == "running":
        return PipelineStatusResponse(status="running")

    summary = json.loads(project.summary_json)

    # Budget teeth: if the user chose to start smaller, downgrade the plan
    # to the Product Intelligence recommendation before the Architect sizes it.
    _plan_names = {"quick": "Quick launch", "production": "Production ready",
                   "scale": "Scale ready"}
    if req.plan_override in _plan_names:
        summary["plan"] = {"id": req.plan_override,
                           "name": _plan_names[req.plan_override]}
        project.summary_json = json.dumps(summary)
        await db.commit()
    await redis_client.set(_pipeline_key(req.project_id), "running", ex=86400)
    asyncio.create_task(_run_pipeline(req.project_id, summary))
    return PipelineStatusResponse(status="running")


@app.get("/pipeline/{project_id}/status", response_model=PipelineStatusResponse)
async def pipeline_status(project_id: int):
    status = await redis_client.get(_pipeline_key(project_id)) or "not_started"
    return PipelineStatusResponse(status=status)


@app.get("/pipeline/{project_id}/blueprint")
async def pipeline_blueprint(project_id: int, db: AsyncSession = Depends(get_db)):
    """Return the latest blueprint the Architect produced (for inspection)."""
    result = await db.execute(
        Blueprint.__table__.select()
        .where(Blueprint.project_id == project_id)
        .order_by(Blueprint.id.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="No blueprint yet")
    return json.loads(row.blueprint_json)


@app.get(
    "/pipeline/{project_id}/design-explanation",
    response_model=DesignExplanationResponse,
)
async def design_explanation(project_id: int):
    raw = await redis_client.get(f"design_explain:{project_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Design not ready")
    data = json.loads(raw)
    return DesignExplanationResponse(**data)


@app.post("/pipeline/build", response_model=PipelineStatusResponse)
async def pipeline_build(
    req: PipelineStartRequest, db: AsyncSession = Depends(get_db)
):
    """Kick off the Developer agents on the stored blueprint (background)."""
    result = await db.execute(
        select(Blueprint.id).where(Blueprint.project_id == req.project_id).limit(1)
    )
    if result.first() is None:
        raise HTTPException(status_code=400, detail="No blueprint to build yet")
    if await redis_client.get(_build_key(req.project_id)) == "running":
        return PipelineStatusResponse(status="running")
    await redis_client.set(_build_key(req.project_id), "running", ex=86400)
    asyncio.create_task(_run_build(req.project_id))
    return PipelineStatusResponse(status="running")


@app.get("/pipeline/{project_id}/build-status", response_model=BuildStatusResponse)
async def build_status(project_id: int, db: AsyncSession = Depends(get_db)):
    status = await redis_client.get(_build_key(project_id)) or "not_started"

    # Total tickets from the latest blueprint.
    bp_row = (await db.execute(
        select(Blueprint.blueprint_json)
        .where(Blueprint.project_id == project_id)
        .order_by(Blueprint.id.desc()).limit(1)
    )).first()
    total = 0
    if bp_row is not None:
        total = len(json.loads(bp_row[0]).get("sprint_tickets", []))

    files_rows = (await db.execute(
        select(GeneratedFile.filename, GeneratedFile.status, GeneratedFile.agent_type)
        .where(GeneratedFile.project_id == project_id)
        .order_by(GeneratedFile.id)
    )).all()
    files = [{"filename": f, "status": s, "agent_type": a} for f, s, a in files_rows]

    return BuildStatusResponse(
        status=status, total=total, complete=len(files), files=files
    )


@app.post("/pipeline/secure", response_model=SecurityStatusResponse)
async def pipeline_secure(
    req: PipelineStartRequest, db: AsyncSession = Depends(get_db)
):
    """Kick off the Code Reviewer (general + Opus security passes) in background."""
    result = await db.execute(
        select(GeneratedFile.id).where(GeneratedFile.project_id == req.project_id).limit(1)
    )
    if result.first() is None:
        raise HTTPException(status_code=400, detail="No generated files to review yet")
    if await redis_client.get(_secure_key(req.project_id)) == "running":
        return SecurityStatusResponse(status="running")
    await redis_client.set(_secure_key(req.project_id), "running", ex=86400)
    asyncio.create_task(_run_review(req.project_id))
    return SecurityStatusResponse(status="running")


@app.get("/pipeline/{project_id}/security-status", response_model=SecurityStatusResponse)
async def security_status(project_id: int):
    status = await redis_client.get(_secure_key(project_id)) or "not_started"
    cert_raw = await redis_client.get(f"security_cert:{project_id}")
    cert = json.loads(cert_raw) if cert_raw else None
    return SecurityStatusResponse(status=status, certificate=cert)


@app.post("/pipeline/qa", response_model=QAStatusResponse)
async def pipeline_qa(req: PipelineStartRequest, db: AsyncSession = Depends(get_db)):
    """Kick off the QA agent on the reviewed code (background).

    Assembles a throwaway local instance, runs Level 1 + Level 2 against it,
    traces root causes, and tears the instance down.
    """
    result = await db.execute(
        select(GeneratedFile.id).where(GeneratedFile.project_id == req.project_id).limit(1)
    )
    if result.first() is None:
        raise HTTPException(status_code=400, detail="No generated files to test yet")
    if await redis_client.get(_qa_key(req.project_id)) == "running":
        return QAStatusResponse(status="running")
    await redis_client.set(_qa_key(req.project_id), "running", ex=86400)
    asyncio.create_task(_run_qa(req.project_id))
    return QAStatusResponse(status="running")


@app.get("/pipeline/{project_id}/qa-status", response_model=QAStatusResponse)
async def qa_status(project_id: int):
    """Counts only — the user never sees test names or technical details."""
    status = await redis_client.get(_qa_key(project_id)) or "not_started"
    raw = await redis_client.get(f"qa_report:{project_id}")
    report = json.loads(raw) if raw else {}
    return QAStatusResponse(
        status=status,
        total=report.get("total", 0),
        passed=report.get("passed", 0),
        failed=report.get("failed", 0),
    )


@app.post("/pipeline/deploy", response_model=DeployStatusResponse)
async def pipeline_deploy(req: PipelineStartRequest, db: AsyncSession = Depends(get_db)):
    """Kick off the DevOps agent for a tested, security-certified project.

    Assembles the generated code into real images, deploys an ISOLATED per-project
    stack, injects secrets, stands up HTTPS, and health-checks the live URL. The
    agent refuses to deploy code the security review never saw (fail-closed).
    """
    result = await db.execute(
        select(GeneratedFile.id).where(GeneratedFile.project_id == req.project_id).limit(1)
    )
    if result.first() is None:
        raise HTTPException(status_code=400, detail="No generated files to deploy yet")
    if await redis_client.get(_deploy_key(req.project_id)) == "running":
        return DeployStatusResponse(status="running")
    await redis_client.set(_deploy_key(req.project_id), "running", ex=86400)
    asyncio.create_task(_run_deploy(req.project_id))
    return DeployStatusResponse(status="running")


@app.get("/pipeline/{project_id}/deploy-status", response_model=DeployStatusResponse)
async def deploy_status(project_id: int):
    """The climax screen's data — live URL, badges, honest cost. No code/agent/
    model names, no secret values."""
    status = await redis_client.get(_deploy_key(project_id)) or "not_started"
    raw = await redis_client.get(f"deploy_report:{project_id}")
    report = json.loads(raw) if raw else {}
    return DeployStatusResponse(
        status=status,
        live_url=report.get("live_url"),
        ssl_enabled=report.get("ssl_enabled", False),
        ssl_type=report.get("ssl_type"),
        security_certified=report.get("security_certified", False),
        tests_passed=report.get("tests_passed", 0),
        monthly_cost_estimate=report.get("monthly_cost_estimate"),
        cost_basis=report.get("cost_basis"),
        server_type=report.get("server_type"),
        auto_fixed=report.get("auto_fixed", False),
        reason=report.get("reason"),
    )


@app.post("/pipeline/document", response_model=DocumentsStatusResponse)
async def pipeline_document(req: PipelineStartRequest, db: AsyncSession = Depends(get_db)):
    """Kick off the Documentation agent (read-only -> user guide, demo script,
    maintenance guide, handoff summary). Needs a blueprint to describe."""
    result = await db.execute(
        select(Blueprint.id).where(Blueprint.project_id == req.project_id).limit(1)
    )
    if result.first() is None:
        raise HTTPException(status_code=400, detail="No blueprint to document yet")
    if await redis_client.get(_document_key(req.project_id)) == "running":
        return DocumentsStatusResponse(status="running")
    await redis_client.set(_document_key(req.project_id), "running", ex=86400)
    asyncio.create_task(_run_documentation(req.project_id))
    return DocumentsStatusResponse(status="running")


@app.get("/pipeline/{project_id}/documents-status", response_model=DocumentsStatusResponse)
async def documents_status(project_id: int):
    """The completion screen's data — real values only, no technical words."""
    status = await redis_client.get(_document_key(project_id)) or "not_started"
    raw = await redis_client.get(f"document_report:{project_id}")
    r = json.loads(raw) if raw else {}
    return DocumentsStatusResponse(
        status=status,
        business_name=r.get("business_name"),
        live_url=r.get("live_url"),
        is_live=r.get("is_live", False),
        security_passed=r.get("security_passed", False),
        security_status=r.get("security_status"),
        tests_available=r.get("tests_available", False),
        tests_passed=r.get("tests_passed", 0),
        tests_total=r.get("tests_total", 0),
        monthly_cost_estimate=r.get("monthly_cost_estimate"),
        cost_basis=r.get("cost_basis"),
        user_guide_ready=r.get("user_guide_ready", False),
        demo_script_ready=r.get("demo_script_ready", False),
        maintenance_guide_ready=r.get("maintenance_guide_ready", False),
        handoff_ready=r.get("handoff_ready", False),
        reason=r.get("reason"),
    )


@app.get("/pipeline/{project_id}/documents")
async def documents(project_id: int, db: AsyncSession = Depends(get_db)):
    """Return the latest generated document of each type (for viewing/export)."""
    rows = (await db.execute(
        select(Document.doc_type, Document.content, Document.created_at)
        .where(Document.project_id == project_id)
        .order_by(Document.id.desc())
    )).all()
    latest: dict[str, dict] = {}
    for doc_type, content, created_at in rows:
        if doc_type not in latest:   # rows are newest-first
            latest[doc_type] = {"content": content, "created_at": created_at.isoformat()}
    return latest
