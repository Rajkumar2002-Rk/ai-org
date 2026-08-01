"""Monitoring agent (#13) — ping the live app, record health, summarise honestly.

Runs as a background async task after deployment: every ~60s it hits the live URL,
records is_healthy / response_time_ms / any 4xx-5xx into `monitoring_logs`, and a
weekly summary in plain English is written to `documents` (weekly_report).

Honesty: the summary reports what we ACTUALLY measured — uptime %, checks, average
response time, real error/downtime windows — and it only says "we fixed it" when a
real fix_log backs it. It deliberately does NOT invent an "actions completed"
count (monitoring pings the app; it does not observe app-level user actions).
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from app import codegen
from app.config import settings
from app.database import async_session
from app.models import Deployment, Document, FixLog, MonitoringLog

logger = logging.getLogger("background.monitor")


def monitor_url(live_url: str) -> tuple[str, bool]:
    """(url, verify_tls) to probe. A local deploy publishes on the host, so from
    inside the platform container we reach it via host.docker.internal and skip
    TLS verification (self-signed); a real domain is used as-is with verification."""
    if not live_url:
        return live_url, False
    if "localhost" in live_url:
        return live_url.replace("localhost", "host.docker.internal"), False
    if "host.docker.internal" in live_url:
        return live_url, False
    return live_url, True


async def _latest_live_deployment(project_id: int) -> Deployment | None:
    async with async_session() as db:
        return (await db.execute(
            select(Deployment).where(Deployment.project_id == project_id)
            .order_by(Deployment.id.desc()).limit(1)
        )).scalar_one_or_none()


async def check_once(project_id: int, live_url: str, path: str = "/",
                     verify_tls: bool | None = None) -> MonitoringLog:
    """One health check; records and returns a MonitoringLog row.

    is_healthy = a response with status < 400. A 4xx/5xx records error_code; a
    connection error/timeout records error_message with no code.
    """
    url, derived_verify = monitor_url(live_url)
    verify = derived_verify if verify_tls is None else verify_tls
    is_healthy = True
    response_time_ms: int | None = None
    error_code: int | None = None
    error_message: str | None = None

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(verify=verify,
                                     timeout=settings.monitoring_request_timeout,
                                     follow_redirects=True) as client:
            r = await client.get(f"{url.rstrip('/')}{path}")
        response_time_ms = int((time.monotonic() - start) * 1000)
        if r.status_code >= 400:
            is_healthy = False
            error_code = r.status_code
            error_message = f"HTTP {r.status_code}"
    except Exception as exc:
        response_time_ms = int((time.monotonic() - start) * 1000)
        is_healthy = False
        error_message = f"{type(exc).__name__}: {str(exc)[:200]}"

    log = MonitoringLog(project_id=project_id, is_healthy=is_healthy,
                        response_time_ms=response_time_ms, error_code=error_code,
                        error_message=error_message)
    async with async_session() as db:
        db.add(log)
        await db.commit()
        await db.refresh(log)
    return log


async def check_and_record(project_id: int, path: str = "/") -> MonitoringLog | None:
    """Check the project's latest live deployment. Returns None if nothing is
    live to monitor (honest — no fabricated 'healthy')."""
    dep = await _latest_live_deployment(project_id)
    if dep is None or dep.status != "live" or not dep.live_url:
        return None
    return await check_once(project_id, dep.live_url, path)


async def monitor_loop(project_id: int, interval: int | None = None,
                       max_checks: int | None = None) -> int:
    """Background loop: check every `interval` seconds. Stops after `max_checks`
    (None = until the app is no longer live). Returns the number of checks done.

    Bounded by design: the loop exits as soon as there is no live deployment, so
    a torn-down app is not pinged forever."""
    import asyncio
    interval = interval or settings.monitoring_interval_seconds
    done = 0
    while max_checks is None or done < max_checks:
        log = await check_and_record(project_id)
        if log is None:
            break  # nothing live to monitor
        done += 1
        if max_checks is not None and done >= max_checks:
            break
        await asyncio.sleep(interval)
    return done


# ------------------------------------------------------------------ weekly summary
def _week_metrics(logs: list[MonitoringLog], interval: int) -> dict:
    """Compute honest weekly metrics from the real logs."""
    total = len(logs)
    healthy = sum(1 for r in logs if r.is_healthy)
    times = [r.response_time_ms for r in logs if r.response_time_ms is not None]
    errors = [r for r in logs if not r.is_healthy]
    # Longest run of consecutive unhealthy checks -> approx downtime minutes.
    longest_streak = streak = 0
    worst_day = None
    for r in sorted(logs, key=lambda x: x.checked_at):
        if not r.is_healthy:
            streak += 1
            if streak > longest_streak:
                longest_streak = streak
                worst_day = r.checked_at
        else:
            streak = 0
    return {
        "checks": total,
        "healthy": healthy,
        "uptime_pct": round(100.0 * healthy / total, 1) if total else None,
        "avg_response_ms": int(sum(times) / len(times)) if times else None,
        "error_count": len(errors),
        "downtime_minutes": round(longest_streak * interval / 60.0, 1),
        "worst_day": worst_day.strftime("%A") if worst_day else None,
    }


async def weekly_summary(project_id: int, interval: int | None = None) -> str:
    """Plain-English summary of the last 7 days from REAL logs; stored as a
    weekly_report document. Only claims a fix happened if a fix_log backs it."""
    interval = interval or settings.monitoring_interval_seconds
    since = datetime.now(timezone.utc) - timedelta(days=7)
    async with async_session() as db:
        logs = list((await db.execute(
            select(MonitoringLog).where(MonitoringLog.project_id == project_id,
                                        MonitoringLog.checked_at >= since)
        )).scalars().all())
        fixes = list((await db.execute(
            select(FixLog).where(FixLog.project_id == project_id,
                                 FixLog.created_at >= since)
        )).scalars().all())

    if not logs:
        text = ("We don't have a full week of activity for your app yet, so there's "
                "nothing to summarise. Once it's been live for a while, you'll get a "
                "plain-English weekly update here.")
        await _store(project_id, text)
        return text

    m = _week_metrics(logs, interval)
    fixed = any(f.outcome in ("healed", "notified", "rolled_back") for f in fixes)

    system = (
        "You write a warm, plain-English WEEKLY UPDATE for a non-technical business "
        "owner about their app. No technical words. 2-4 short sentences. Use ONLY "
        "the numbers I give you — do not invent any figure (especially do NOT make "
        "up a count of customer actions or orders; you only know uptime and speed). "
        "If there was downtime, mention roughly how long and which day; only say it "
        "was fixed if told a fix happened."
    )
    facts = {**m, "a_fix_happened": fixed}
    text, _ = await codegen.generate(model=settings.monitoring_model, system=system,
                                     user=str(facts),
                                     temperature=settings.monitoring_temperature)
    if not (text and text.strip()):
        text = _fallback_summary(m, fixed)
    await _store(project_id, text.strip())
    return text.strip()


def _fallback_summary(m: dict, fixed: bool) -> str:
    if m["error_count"] == 0:
        return (f"Your app had a great week. It was up {m['uptime_pct']}% of the "
                f"time across {m['checks']} checks, responding in about "
                f"{m['avg_response_ms']} milliseconds on average. Everything is "
                f"running smoothly.")
    downtime = f"about {m['downtime_minutes']:.0f} minute(s)"
    day = f" on {m['worst_day']}" if m["worst_day"] else ""
    tail = (" We spotted it and it's back to normal." if fixed
            else " We're keeping an eye on it.")
    return (f"Your app was up {m['uptime_pct']}% of the time this week. It had a "
            f"rough patch of {downtime}{day}.{tail}")


async def _store(project_id: int, text: str) -> None:
    async with async_session() as db:
        db.add(Document(project_id=project_id, doc_type="weekly_report", content=text))
        await db.commit()
