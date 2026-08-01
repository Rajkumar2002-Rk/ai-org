"""Cost Tracker (#15) — daily actual + projected spend vs the user's budget.

The projection/budget/alert math is pure and proven synthetically. The REAL AWS
Cost Explorer poll is written but GATED OFF (`aws_cost_explorer_enabled=False`):
CE data lags 24-48h and each call costs ~$0.01, so a live call would return little
for the money while nothing stays deployed between sessions. In production this
runs once per day (a cron / scheduled job); for testing it is triggered manually
with recorded readings.
"""
import calendar
import logging
import re
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import CostLog, Deployment, Project

logger = logging.getLogger("background.cost_tracker")


def parse_budget(summary: dict) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", str(summary.get("budget") or "").replace(",", ""))
    return float(m.group(1)) if m else None


def project_month_end(actual_mtd: float, day_of_month: int, days_in_month: int) -> float:
    """Straight-line projection from month-to-date spend."""
    if day_of_month <= 0:
        return round(actual_mtd, 2)
    return round(actual_mtd / day_of_month * days_in_month, 2)


async def _budget(project_id: int) -> float | None:
    async with async_session() as db:
        project = await db.get(Project, project_id)
    import json
    summary = json.loads(project.summary_json) if project and project.summary_json else {}
    return parse_budget(summary)


async def record(project_id: int, actual_cost_usd: float,
                 on_date: date | None = None) -> CostLog:
    """Store a cost reading with projection + budget + over-budget flag. This is
    the manual/testable path; `poll()` feeds it from Cost Explorer when enabled."""
    on_date = on_date or date.today()
    days_in_month = calendar.monthrange(on_date.year, on_date.month)[1]
    projected = project_month_end(actual_cost_usd, on_date.day, days_in_month)
    budget = await _budget(project_id)
    over = bool(budget is not None and projected > budget * settings.cost_budget_alert_ratio)
    log = CostLog(project_id=project_id, date=on_date.isoformat(),
                  actual_cost_usd=round(actual_cost_usd, 2),
                  projected_monthly_usd=projected, budget_usd=budget,
                  over_budget=over)
    async with async_session() as db:
        db.add(log)
        await db.commit()
        await db.refresh(log)
    return log


def _ce_actual_month_to_date(project_id: int) -> float:
    """REAL AWS Cost Explorer month-to-date for this app, filtered by tag.

    GATED: only called when aws_cost_explorer_enabled is True. Not yet run live
    (CE lags 24-48h and costs ~$0.01/call) — real code, verified by inspection,
    pending a shakeout the same way the AWS deploy driver was.
    """
    import boto3
    today = date.today()
    start = today.replace(day=1).isoformat()
    end = (today + timedelta(days=1)).isoformat()   # End is exclusive; must be > Start
    ce = boto3.client("ce", region_name="us-east-1")  # Cost Explorer is us-east-1
    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end}, Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        Filter={"Tags": {"Key": "project_id", "Values": [str(project_id)]}},
    )
    return sum(float(r["Total"]["UnblendedCost"]["Amount"])
               for r in resp.get("ResultsByTime", []))


async def poll(project_id: int) -> CostLog | None:
    """Daily poll. With CE enabled + an AWS deployment, reads real month-to-date
    spend and records it. Otherwise returns None (honest — no fabricated cost)."""
    async with async_session() as db:
        dep = (await db.execute(
            select(Deployment).where(Deployment.project_id == project_id)
            .order_by(Deployment.id.desc()).limit(1)
        )).scalar_one_or_none()
    if not settings.aws_cost_explorer_enabled or dep is None or dep.target != "aws":
        logger.info("Cost Explorer poll skipped (gated off or not an AWS deploy) "
                    "for project %s", project_id)
        return None
    try:
        actual = _ce_actual_month_to_date(project_id)
    except Exception:  # pragma: no cover - never let cost polling break anything
        logger.exception("Cost Explorer poll failed for project %s", project_id)
        return None
    return await record(project_id, actual)


async def summary(project_id: int) -> dict | None:
    """Latest cost picture for the dashboard. None if no reading yet (honest)."""
    async with async_session() as db:
        log = (await db.execute(
            select(CostLog).where(CostLog.project_id == project_id)
            .order_by(CostLog.id.desc()).limit(1)
        )).scalar_one_or_none()
    if log is None:
        return None
    actual = float(log.actual_cost_usd)
    projected = float(log.projected_monthly_usd) if log.projected_monthly_usd is not None else None
    budget = float(log.budget_usd) if log.budget_usd is not None else None
    if budget is None:
        status_text = "No budget on file, so we can't compare to one yet."
    elif log.over_budget:
        status_text = "Heads up — trending over budget"
    else:
        status_text = "You are on track ✓"
    return {
        "this_month_so_far": round(actual, 2),
        "projected_month_end": projected,
        "budget": budget,
        "over_budget": bool(log.over_budget),
        "status_text": status_text,
        "as_of": log.date,
    }
