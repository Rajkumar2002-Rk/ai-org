"""Auto-fix agent (#14) — self-heal safely, or escalate honestly.

Triggered when Monitoring detects a problem. Safe Mode is mandatory: a snapshot
of deployment state is taken BEFORE any fix, so a fix that makes things worse can
be rolled back.

Level 1 (silent self-heal): a transient infrastructure fault (app not responding,
memory pressure, DB connection dropped) -> RESTART. This REUSES the Week-7 DevOps
`driver.restart(req)` primitive (docker restart / SSM compose restart) — the same
infra-only action that structurally cannot touch generated code or security config.
There is no second restart path.

Level 2 (fixed, notify after): a self-heal that worked but caused noticeable
downtime -> log + plain-English notification.

Level 3 (needs the user): anything not restart-fixable (app-code error, a security
control refusing, missing configuration/keys, or a restart that didn't help) ->
a user_issue with plain-English step-by-step instructions. Auto-fix NEVER weakens
the app to force it up (the defect-#6 lesson, carried into ops).
"""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.devops import health
from app.devops.drivers.base import DeployRequest
from app.devops.orchestrator import _get_driver
from app.background.monitor import check_once
from app.models import (Deployment, DeploymentSnapshot, FixLog, Project,
                        UserIssue)

logger = logging.getLogger("background.autofix")


def _project_name(summary: dict) -> str:
    return (summary.get("business_name") or summary.get("build") or "app")


async def _load(project_id: int):
    async with async_session() as db:
        project = await db.get(Project, project_id)
        summary = (json.loads(project.summary_json)
                   if project and project.summary_json else {})
        dep = (await db.execute(
            select(Deployment).where(Deployment.project_id == project_id)
            .order_by(Deployment.id.desc()).limit(1)
        )).scalar_one_or_none()
    return project, summary, dep


def _make_request(project_id: int, project_name: str, dep: Deployment) -> DeployRequest:
    from app.devops import naming
    names = naming.names(project_id, project_name)
    return DeployRequest(project_id=project_id, project_name=project_name, files=[],
                         names=names, subdomain=names["subdomain"], env={},
                         sizing=None, root="")


async def _snapshot(project_id: int, dep: Deployment, reason: str,
                    health_before: bool) -> int:
    """Safe Mode: record restorable state BEFORE any fix."""
    state = {
        "deployment_id": dep.id,
        "image_backend_ref": dep.image_backend_ref,
        "image_frontend_ref": dep.image_frontend_ref,
        "status": dep.status,
        "server_type": dep.server_type,
        "target": dep.target,
        "live_url": dep.live_url,
        "health_before": health_before,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }
    async with async_session() as db:
        snap = DeploymentSnapshot(project_id=project_id, deployment_id=dep.id,
                                  state_json=json.dumps(state), reason=reason)
        db.add(snap)
        await db.commit()
        await db.refresh(snap)
        return snap.id


_LEVEL3_INSTRUCTIONS = {
    health.MISSING_CONFIG: (
        "Your app needs a setting or key connected before it can run properly.",
        ["Open your app dashboard.",
         "Go to Settings.",
         "Connect the missing key or setting it's asking for.",
         "If you're not sure which one, use 'Make a change to my app' and we'll help."]),
    health.SECURITY_REFUSAL: (
        "A built-in safety check is holding your app back until it's reviewed — we "
        "won't bypass it.",
        ["No action needed from you to stay safe — your app is paused, not exposed.",
         "Use 'Make a change to my app' to have the safety issue reviewed and fixed."]),
    health.APP_ERROR: (
        "Something inside your app hit a snag that needs a closer look.",
        ["Your data is safe.",
         "Use 'Make a change to my app' to have it looked at and corrected."]),
    health.UNKNOWN: (
        "Your app ran into a problem we couldn't fix on our own.",
        ["Your data is safe.",
         "Use 'Make a change to my app' and we'll investigate."]),
}


async def _escalate(project_id: int, fault: health.Fault, snapshot_id: int,
                    problem: str, outcome: str = "escalated",
                    downtime: int | None = None) -> dict:
    title, steps = _LEVEL3_INSTRUCTIONS.get(fault.kind,
                                            _LEVEL3_INSTRUCTIONS[health.UNKNOWN])
    instructions = title + "\n\nWhat to do:\n" + "\n".join(f"- {s}" for s in steps)
    async with async_session() as db:
        db.add(UserIssue(project_id=project_id, title=title, instructions=instructions))
        db.add(FixLog(project_id=project_id, level=3, problem=problem,
                      action="escalated", snapshot_id=snapshot_id, outcome=outcome,
                      downtime_seconds=downtime, notified=True,
                      notification=title))
        await db.commit()
    return {"level": 3, "outcome": outcome, "notified": True, "message": title}


async def handle(project_id: int, problem: str,
                 detected_at: datetime | None = None) -> dict:
    """Snapshot -> classify -> Level 1 restart (reused) -> notify/escalate; roll
    back if the fix made things worse. Returns a plain summary of what happened."""
    project, summary, dep = await _load(project_id)
    if dep is None or dep.status != "live":
        return {"level": 0, "outcome": "no_live_deployment"}

    detected_at = detected_at or datetime.now(timezone.utc)
    fault = health.classify(problem)
    snapshot_id = await _snapshot(project_id, dep, reason=fault.kind,
                                  health_before=False)

    # Not restart-fixable -> straight to Level 3 (never weaken the app).
    if not fault.autofixable:
        return await _escalate(project_id, fault, snapshot_id, problem)

    # Level 1: reuse the DevOps restart primitive.
    driver = _get_driver(dep.target)
    req = _make_request(project_id, _project_name(summary), dep)
    try:
        await driver.restart(req)
    except Exception as exc:  # pragma: no cover - driver failure -> escalate
        logger.warning("restart failed for project %s: %s", project_id, exc)
        return await _escalate(project_id, fault, snapshot_id, problem)

    after = await check_once(project_id, dep.live_url)
    downtime = int((datetime.now(timezone.utc) - detected_at).total_seconds())

    if after.is_healthy:
        if downtime <= settings.autofix_notify_downtime_seconds:
            # Level 1: silent self-heal.
            async with async_session() as db:
                db.add(FixLog(project_id=project_id, level=1, problem=problem,
                              action="restart", snapshot_id=snapshot_id,
                              outcome="healed", downtime_seconds=downtime,
                              notified=False))
                await db.commit()
            return {"level": 1, "outcome": "healed", "notified": False,
                    "downtime_seconds": downtime}
        # Level 2: fixed, but notify the user after.
        mins = max(1, round(downtime / 60))
        msg = (f"We detected a small issue and fixed it automatically. Your app was "
               f"affected for about {mins} minute(s). Everything is back to normal.")
        async with async_session() as db:
            db.add(FixLog(project_id=project_id, level=2, problem=problem,
                          action="restart", snapshot_id=snapshot_id,
                          outcome="notified", downtime_seconds=downtime,
                          notified=True, notification=msg))
            await db.commit()
        return {"level": 2, "outcome": "notified", "notified": True,
                "downtime_seconds": downtime, "message": msg}

    # Restart didn't restore health. If it made things WORSE, roll back to the
    # snapshot first; either way this now needs the user (Level 3).
    outcome = "escalated"
    if not after.is_healthy:  # (still down) — attempt rollback to known-good state
        try:
            await driver.restart(req)  # restore: re-apply the snapshot's stack
            outcome = "rolled_back"
        except Exception:  # pragma: no cover
            logger.warning("rollback restart failed for project %s", project_id)
    return await _escalate(project_id, fault, snapshot_id, problem,
                           outcome=outcome, downtime=downtime)
