"""Week 9 background agents — offline/local proof. Zero AWS, zero LLM spend.

Every check can FAIL for its reason (standing principle):

* Monitoring is proven against a REAL local HTTP server (real round-trips): a 200
  is healthy, a 404/500 is captured with its code, a dead port is unhealthy with a
  message — no fabricated "healthy".
* Auto-fix is exercised through every branch with a patched driver + scripted
  health: Level 1 silent, Level 2 notify, Level 3 escalate (non-restartable AND
  restart-didn't-help→rollback). A snapshot is ALWAYS taken before the fix, and it
  never writes to generated_files / code_reviews (read-only over code/security).
* Cost math: projection, budget compare, and the +20% alert.
* Weekly summary + dashboard: honest — real numbers only, "we fixed it" only when a
  fix_log backs it, missing data reads as "not available".

Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tests/test_background_offline.py
"""
import asyncio
import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from sqlalchemy import delete, func, select

import app.codegen as codegen
from app.config import settings
from app.database import async_session
from app.background import autofix, cost_tracker, dashboard, monitor
from app.models import (CodeReview, CostLog, Deployment, DeploymentSnapshot,
                        Document, FixLog, GeneratedFile, MonitoringLog, Project,
                        UserIssue)

_failures: list[str] = []
_seeded: list[int] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


# ------------------------------------------------------------- local HTTP server
class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        code = 200
        if self.path.startswith("/notfound"):
            code = 404
        elif self.path.startswith("/boom"):
            code = 500
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"ok")


def _start_server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


async def _seed(*, deployed_live: bool, budget: str = "$15",
                live_url: str | None = None) -> int:
    async with async_session() as db:
        p = Project(prompt="grocery app", status="deployed",
                    summary_json=json.dumps({"business_name": "Corner Grocer",
                                             "budget": budget, "mobile_choice": "web"}))
        db.add(p); await db.commit(); await db.refresh(p); pid = p.id
        if deployed_live:
            db.add(Deployment(project_id=pid, target="local", status="live",
                              live_url=live_url or "https://x-abc.apps.rajkumarai.dev",
                              server_type="EC2 t3.micro", monthly_cost_estimate=12.38,
                              image_backend_ref="img-be", image_frontend_ref=None))
        await db.commit()
    _seeded.append(pid)
    return pid


async def _cleanup():
    async with async_session() as db:
        for pid in _seeded:
            for M in (Document, CostLog, FixLog, UserIssue, DeploymentSnapshot,
                      MonitoringLog, Deployment, CodeReview, GeneratedFile):
                await db.execute(delete(M).where(M.project_id == pid))
            await db.execute(delete(Project).where(Project.id == pid))
        await db.commit()


# ------------------------------------------------------------------ A. monitoring
async def test_monitoring():
    print("\nA. Monitoring — real HTTP round-trips (200 / 404 / 500 / dead)")
    srv, port = _start_server()
    base = f"http://127.0.0.1:{port}"   # not 'localhost' -> monitor_url leaves it
    pid = await _seed(deployed_live=True, live_url=base)
    try:
        ok = await monitor.check_once(pid, base, "/")
        check("200 is healthy + response time recorded",
              ok.is_healthy and ok.response_time_ms is not None and ok.error_code is None)
        nf = await monitor.check_once(pid, base, "/notfound")
        check("404 captured as unhealthy with code 404",
              (not nf.is_healthy) and nf.error_code == 404)
        boom = await monitor.check_once(pid, base, "/boom")
        check("500 captured as unhealthy with code 500",
              (not boom.is_healthy) and boom.error_code == 500)
        dead = await monitor.check_once(pid, "http://127.0.0.1:1", "/")
        check("dead port is unhealthy with a message, no fabricated ok",
              (not dead.is_healthy) and dead.error_message and dead.error_code is None)
        # check_and_record uses the deployment's live_url.
        rec = await monitor.check_and_record(pid, "/")
        check("check_and_record logs against the live deployment", rec is not None)
        async with async_session() as db:
            n = (await db.execute(select(func.count()).select_from(MonitoringLog)
                 .where(MonitoringLog.project_id == pid))).scalar()
        check("monitoring_logs rows persisted", n >= 5, str(n))
        # No live deployment -> honest None, not a fake healthy row.
        pid2 = await _seed(deployed_live=False)
        check("no live deployment -> check_and_record returns None (honest)",
              (await monitor.check_and_record(pid2)) is None)
    finally:
        srv.shutdown()


# ------------------------------------------------------------------ B. auto-fix
class _FakeDriver:
    def __init__(self): self.restarts = 0
    async def restart(self, req): self.restarts += 1


class _FakeLog:
    def __init__(self, healthy): self.is_healthy = healthy


async def _run_autofix(pid, problem, after_healthy, detected_at):
    fake = _FakeDriver()
    autofix._get_driver = lambda target: fake

    async def _fake_check(project_id, live_url, path="/", verify_tls=None):
        return _FakeLog(after_healthy)
    autofix.check_once = _fake_check
    result = await autofix.handle(pid, problem, detected_at=detected_at)
    return result, fake


async def test_autofix():
    print("\nB. Auto-fix — Safe Mode snapshot, level mapping, rollback, read-only")
    now = datetime.now(timezone.utc)

    async with async_session() as db:
        gf_before = (await db.execute(select(func.count()).select_from(GeneratedFile))).scalar()
        cr_before = (await db.execute(select(func.count()).select_from(CodeReview))).scalar()

    # Level 1 — transient fault, restart heals quickly -> silent.
    pid = await _seed(deployed_live=True)
    res, fake = await _run_autofix(pid, "could not connect to server: Connection refused",
                                   after_healthy=True, detected_at=now)
    check("L1: transient fault healed by restart, silent",
          res["level"] == 1 and res["outcome"] == "healed" and res["notified"] is False)
    check("L1: reused restart primitive was called", fake.restarts == 1)
    async with async_session() as db:
        snaps = (await db.execute(select(func.count()).select_from(DeploymentSnapshot)
                 .where(DeploymentSnapshot.project_id == pid))).scalar()
    check("L1: a snapshot was taken BEFORE the fix (Safe Mode)", snaps == 1)

    # Level 2 — same fix, but long downtime -> notify after.
    pid = await _seed(deployed_live=True)
    res, _ = await _run_autofix(pid, "connection refused", after_healthy=True,
                                detected_at=now - timedelta(minutes=6))
    check("L2: long downtime -> fixed + user notified",
          res["level"] == 2 and res["notified"] and "back to normal" in res["message"].lower())

    # Level 3 — non-restartable app error -> escalate, NO restart.
    pid = await _seed(deployed_live=True)
    res, fake = await _run_autofix(pid, "Traceback (most recent call last): ImportError x",
                                   after_healthy=True, detected_at=now)
    check("L3: app error escalates (not restart-fixed)",
          res["level"] == 3 and res["outcome"] == "escalated")
    check("L3: restart NOT attempted for app error", fake.restarts == 0)
    async with async_session() as db:
        iss = (await db.execute(select(func.count()).select_from(UserIssue)
               .where(UserIssue.project_id == pid))).scalar()
    check("L3: a user_issue with instructions was created", iss == 1)

    # Level 3 — transient, but restart did NOT help -> rollback then escalate.
    pid = await _seed(deployed_live=True)
    res, fake = await _run_autofix(pid, "connection refused", after_healthy=False,
                                   detected_at=now)
    check("L3: restart didn't help -> rolled_back + escalated",
          res["level"] == 3 and res["outcome"] == "rolled_back")
    check("L3: rollback re-applied the stack (restart called twice)", fake.restarts == 2)

    # Read-only over code/security.
    async with async_session() as db:
        gf_after = (await db.execute(select(func.count()).select_from(GeneratedFile))).scalar()
        cr_after = (await db.execute(select(func.count()).select_from(CodeReview))).scalar()
    check("auto-fix never touched generated_files", gf_after == gf_before)
    check("auto-fix never touched code_reviews", cr_after == cr_before)


# ------------------------------------------------------------------ C. cost
async def test_cost():
    print("\nC. Cost Tracker — projection, budget, +20% alert")
    check("projection: $6 by day 10 of 30 -> $18",
          cost_tracker.project_month_end(6.0, 10, 30) == 18.0,
          str(cost_tracker.project_month_end(6.0, 10, 30)))
    pid = await _seed(deployed_live=True, budget="$15")
    from datetime import date
    d10 = date(2026, 6, 10)   # day 10 of a 30-day month
    under = await cost_tracker.record(pid, 4.0, on_date=d10)   # projects to 12 -> under 15
    check("on-track: projected under budget -> not over", under.over_budget is False)
    over = await cost_tracker.record(pid, 7.0, on_date=d10)    # projects to 21 > 15*1.2=18
    check("alert: projected > budget*1.2 -> over_budget", over.over_budget is True)
    summ = await cost_tracker.summary(pid)
    check("summary reflects the latest reading + status",
          summ["over_budget"] is True and "budget" in summ["status_text"].lower())
    # No budget -> honest, not a fake 'on track'.
    pid2 = await _seed(deployed_live=True, budget="")
    await cost_tracker.record(pid2, 5.0, on_date=d10)
    s2 = await cost_tracker.summary(pid2)
    check("no budget -> honest 'can't compare' (not a fake on-track)",
          s2["budget"] is None and "can't compare" in s2["status_text"].lower())


# ------------------------------------------------------------------ D. weekly + dashboard
async def test_weekly_and_dashboard():
    print("\nD. Weekly summary + dashboard — honest, real numbers only")
    codegen.generate = _none_gen   # force the deterministic fallback (free)

    pid = await _seed(deployed_live=True)
    # Seed a week of logs: mostly healthy, a short outage, no fix_log.
    now = datetime.now(timezone.utc)
    async with async_session() as db:
        for i in range(20):
            db.add(MonitoringLog(project_id=pid, is_healthy=True, response_time_ms=120,
                                 checked_at=now - timedelta(hours=i)))
        for i in range(2):   # a 2-check outage
            db.add(MonitoringLog(project_id=pid, is_healthy=False, error_code=500,
                                 error_message="HTTP 500",
                                 checked_at=now - timedelta(hours=30 + i)))
        await db.commit()
    text = await monitor.weekly_summary(pid, interval=3600)
    check("weekly summary mentions real uptime, no fabricated 'actions'",
          "%" in text and "action" not in text.lower(), text[:120])
    check("no fix_log -> does NOT claim it was fixed",
          "back to normal" not in text.lower() and "fixed" not in text.lower())
    async with async_session() as db:
        wr = (await db.execute(select(func.count()).select_from(Document)
              .where(Document.project_id == pid, Document.doc_type == "weekly_report"))).scalar()
    check("weekly summary stored as weekly_report document", wr == 1)

    # Empty project -> honest "not a full week yet".
    pid_empty = await _seed(deployed_live=True)
    empty_text = await monitor.weekly_summary(pid_empty)
    check("no logs -> honest, no invented numbers",
          "%" not in empty_text and "nothing to summarise" in empty_text.lower())

    # Dashboard aggregation.
    await cost_tracker.record(pid, 4.0)
    dash = await dashboard.build(pid)
    check("dashboard app_status live", dash["app_status"] == "live")
    check("dashboard has cost + activity sections",
          dash["cost"] is not None and dash["activity"] is not None)
    check("dashboard activity uptime is real", dash["activity"]["uptime_pct"] is not None)
    # Not-live project -> honest not_live + null sections.
    pid_nl = await _seed(deployed_live=False)
    dnl = await dashboard.build(pid_nl)
    check("not-deployed -> app_status not_live, null cost/activity",
          dnl["app_status"] == "not_live" and dnl["cost"] is None and dnl["activity"] is None)


async def _none_gen(*a, **k):
    return (None, "gemini-2.5-flash-lite")


async def main():
    print("=" * 64)
    print("Week 9 background agents — offline/local proof (no AWS, no LLM)")
    print("=" * 64)
    try:
        await test_monitoring()
        await test_autofix()
        await test_cost()
        await test_weekly_and_dashboard()
    finally:
        await _cleanup()

    print("\n" + "=" * 64)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
