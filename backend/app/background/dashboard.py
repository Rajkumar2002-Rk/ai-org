"""Post-launch dashboard aggregator — the four sections the user sees.

Read-only over real tables: deployment (status), cost_logs (spend vs budget),
monitoring_logs (recent activity), user_issues (open issues). Honest: missing
data reads as "not available yet", never a fabricated ✓.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.background import cost_tracker
from app.background.monitor import _week_metrics
from app.config import settings
from app.database import async_session
from app.models import Deployment, MonitoringLog, UserIssue


async def build(project_id: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    async with async_session() as db:
        dep = (await db.execute(
            select(Deployment).where(Deployment.project_id == project_id)
            .order_by(Deployment.id.desc()).limit(1)
        )).scalar_one_or_none()
        logs = list((await db.execute(
            select(MonitoringLog).where(MonitoringLog.project_id == project_id,
                                        MonitoringLog.checked_at >= since)
        )).scalars().all())
        issues = list((await db.execute(
            select(UserIssue).where(UserIssue.project_id == project_id,
                                    UserIssue.status == "open")
            .order_by(UserIssue.id.desc())
        )).scalars().all())

    cost = await cost_tracker.summary(project_id)
    metrics = _week_metrics(logs, settings.monitoring_interval_seconds) if logs else None

    is_live = bool(dep and dep.status == "live")
    if not is_live:
        app_status = "not_live"
    elif issues:
        app_status = "issue_detected"
    else:
        app_status = "live"

    return {
        # 1. App status
        "app_status": app_status,
        "live_url": dep.live_url if is_live else None,
        # 2. This month cost
        "cost": cost,   # None if no reading yet
        # 3. Recent activity
        "activity": ({"uptime_pct": metrics["uptime_pct"],
                      "avg_response_ms": metrics["avg_response_ms"],
                      "error_count": metrics["error_count"],
                      "checks": metrics["checks"]} if metrics else None),
        # 4. Open issues needing the user (drives the "issue detected" state)
        "issues": [{"title": i.title, "instructions": i.instructions,
                    "created_at": i.created_at.isoformat()} for i in issues],
    }
