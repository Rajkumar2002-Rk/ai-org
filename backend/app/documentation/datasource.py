"""The honest source-of-truth layer for the Documentation agent.

`gather(project_id)` returns a plain dict of REAL facts pulled read-only from the
existing tables + Redis. Every generator reads from this dict and nothing else —
so there is exactly one place where "what is true about this project" is decided,
and it is decided from stored data, never invented.

Missing data is represented honestly: `deployment=None` when nothing was ever
deployed, `security["status"]="no_certificate"` when the cert is absent, real
`qa` counts (including failures), and integrations marked "connected" ONLY when a
real secret row exists for them.
"""
import json
import logging
import re

from sqlalchemy import select

from app.database import async_session
from app.models import (Blueprint, CodeReview, Deployment, GeneratedFile,
                        Project, QAResult, Secret)
from app.redis_client import redis_client

logger = logging.getLogger("documentation.datasource")

# Ticket id prefixes that are infrastructure, not user-facing features — excluded
# from the "features" a non-technical guide should describe.
_NON_FEATURE_PREFIXES = ("FND", "APP", "SEC")


def _platform_word(mobile_choice: str | None) -> str:
    return {"native": "app", "both": "website and app", "web": "website"}.get(
        mobile_choice or "web", "website")


def _screen_name(filepath: str) -> str:
    """Friendly screen name from a Next.js page path.

    frontend/app/page.tsx -> "Home"; frontend/app/menu/page.tsx -> "Menu";
    frontend/app/orders/new/page.tsx -> "Orders — New"; dynamic segments like
    [order_id] become "Details".
    """
    rel = re.sub(r"^.*?/app/", "", filepath)
    rel = re.sub(r"/?page\.(t|j)sx?$", "", rel)
    if not rel:
        return "Home"
    parts = []
    for seg in rel.split("/"):
        if not seg:
            continue
        if seg.startswith("[") and seg.endswith("]"):
            parts.append("Details")
        else:
            parts.append(seg.replace("-", " ").replace("_", " ").strip().title())
    return " — ".join(parts) if parts else "Home"


def _built_features(blueprint: dict, files: list[dict]) -> list[dict]:
    """User-facing features that were ACTUALLY built (a ticket that produced a
    generated file), excluding infrastructure tickets."""
    built_ticket_ids = {(f.get("ticket_id") or "").upper() for f in files}
    features = []
    for t in blueprint.get("sprint_tickets", []) or []:
        tid = (t.get("id") or "").upper()
        if not tid or tid not in built_ticket_ids:
            continue
        if any(tid.startswith(p) for p in _NON_FEATURE_PREFIXES):
            continue
        features.append({"id": t.get("id"), "title": t.get("title", ""),
                         "description": t.get("description", ""),
                         "assigned_to": t.get("assigned_to", "")})
    return features


def _screens(files: list[dict]) -> list[dict]:
    """Real frontend screens = generated Next.js pages. The demo script is built
    from THESE — it can only ever describe screens that exist."""
    out = []
    for f in files:
        path = (f.get("filepath") or f.get("filename") or "")
        if "frontend/" in path and re.search(r"page\.(t|j)sx?$", path):
            out.append({"name": _screen_name(path), "path": path})
    # Home first, then alphabetical — a natural walkthrough order.
    out.sort(key=lambda s: (s["name"] != "Home", s["name"]))
    return out


def _integrations(blueprint: dict, secret_names: set[str]) -> list[dict]:
    """Designed third-party integrations + their REAL connection status.

    'connected' ONLY when a matching secret row exists. Stripe Connect is never
    reported as live from here — it is connected in-app by the owner after launch,
    so it reads "designed, connect in-app after launch" until that happens.
    """
    out = []
    for a in blueprint.get("third_party_apis", []) or []:
        name = a.get("name", "")
        low = name.lower()
        is_stripe = "stripe" in low
        connection = a.get("connection", "")
        who = a.get("who_handles", "")
        # Does a real secret back this integration?
        connected = any(low.split()[0] in s.lower() for s in secret_names) if secret_names else False
        if is_stripe or connection == "in_app_oauth":
            status = "designed — connect in-app after launch (not yet connected)"
            connected = False
        elif connected:
            status = "connected"
        else:
            status = "designed — not yet connected"
        out.append({"name": name, "who_handles": who, "connection": connection,
                    "connected": connected, "status": status})
    return out


def _security(cert: dict | None, reviews: list[dict]) -> dict:
    """Security status from the Opus certificate (authoritative) + code_reviews.

    Fails closed: no certificate reads as 'no_certificate' (never 'passed'); a
    certificate that says passed=false reads as 'not_passed'.
    """
    total_found = sum(r.get("issues_found", 0) for r in reviews)
    total_fixed = sum(r.get("issues_fixed", 0) for r in reviews)
    if not cert:
        return {"status": "no_certificate", "passed": False,
                "issues_found": total_found, "issues_fixed": total_fixed,
                "model_used": None, "files_reviewed": len(reviews),
                "recertified": False}
    return {
        "status": "passed" if cert.get("passed") else "not_passed",
        "passed": bool(cert.get("passed")),
        "issues_found": cert.get("issues_found", total_found),
        "issues_fixed": cert.get("issues_fixed", total_fixed),
        "model_used": cert.get("model_used"),
        "files_reviewed": cert.get("files_reviewed", len(reviews)),
        "recertified": bool(cert.get("recertified_after_qa")),
    }


def _qa(rows: list[dict], report: dict | None) -> dict:
    """Real test outcome for the latest run. Never assumes all passed."""
    if rows:
        # Group by run_id; pick the latest run by max created_at.
        runs: dict = {}
        for r in rows:
            runs.setdefault(r["run_id"], []).append(r)
        latest = max(runs.values(),
                     key=lambda rs: max(x["created_at"] for x in rs))
        total = len(latest)
        passed = sum(1 for r in latest if r["passed"])
        escalated = sum(1 for r in latest
                        if (r.get("failure_reason") or "").startswith("[escalated"))
        return {"available": True, "total": total, "passed": passed,
                "failed": total - passed, "escalated": escalated}
    if report:
        return {"available": True, "total": report.get("total", 0),
                "passed": report.get("passed", 0), "failed": report.get("failed", 0),
                "escalated": report.get("escalated", 0)}
    return {"available": False, "total": 0, "passed": 0, "failed": 0, "escalated": 0}


def _deployment(dep) -> dict | None:
    if dep is None:
        return None
    return {
        "status": dep.status,
        "live_url": dep.live_url,
        "subdomain": dep.subdomain,
        "server_type": dep.server_type,
        "monthly_cost_estimate": (float(dep.monthly_cost_estimate)
                                  if dep.monthly_cost_estimate is not None else None),
        "cost_basis": dep.cost_basis,
        "ssl_enabled": dep.ssl_enabled,
        "ssl_type": dep.ssl_type,
        "auto_fixed": dep.auto_fixed,
        "deployed_at": dep.deployed_at.isoformat() if dep.deployed_at else None,
        "is_live": dep.status == "live",
    }


async def gather(project_id: int) -> dict:
    """Read-only: assemble the real facts for a project. Never writes."""
    async with async_session() as db:
        project = await db.get(Project, project_id)
        bp_row = (await db.execute(
            select(Blueprint.blueprint_json, Blueprint.created_at)
            .where(Blueprint.project_id == project_id)
            .order_by(Blueprint.id.desc()).limit(1)
        )).first()
        file_rows = (await db.execute(
            select(GeneratedFile.ticket_id, GeneratedFile.filename,
                   GeneratedFile.filepath, GeneratedFile.agent_type,
                   GeneratedFile.status)
            .where(GeneratedFile.project_id == project_id)
        )).all()
        dep = (await db.execute(
            select(Deployment).where(Deployment.project_id == project_id)
            .order_by(Deployment.id.desc()).limit(1)
        )).scalar_one_or_none()
        review_rows = (await db.execute(
            select(CodeReview.issues_found, CodeReview.issues_fixed,
                   CodeReview.security_passed)
            .where(CodeReview.project_id == project_id)
        )).all()
        qa_rows = (await db.execute(
            select(QAResult.run_id, QAResult.passed, QAResult.failure_reason,
                   QAResult.created_at).where(QAResult.project_id == project_id)
        )).all()
        secret_rows = (await db.execute(
            select(Secret.key_name).where(Secret.project_id == project_id)
        )).all()

    summary = json.loads(project.summary_json) if project and project.summary_json else {}
    blueprint = json.loads(bp_row[0]) if bp_row else {}
    blueprint_created = bp_row[1].isoformat() if bp_row else None
    files = [{"ticket_id": r[0], "filename": r[1], "filepath": r[2],
              "agent_type": r[3], "status": r[4]} for r in file_rows]
    reviews = [{"issues_found": r[0], "issues_fixed": r[1], "security_passed": r[2]}
               for r in review_rows]
    qa = [{"run_id": r[0], "passed": r[1], "failure_reason": r[2], "created_at": r[3]}
          for r in qa_rows]
    secret_names = {r[0] for r in secret_rows}

    cert_raw = await redis_client.get(f"security_cert:{project_id}")
    cert = json.loads(cert_raw) if cert_raw else None
    qa_report_raw = await redis_client.get(f"qa_report:{project_id}")
    qa_report = json.loads(qa_report_raw) if qa_report_raw else None

    return {
        "project_id": project_id,
        "business_name": summary.get("business_name") or "your app",
        "idea": summary.get("build") or (project.prompt if project else ""),
        "platform": _platform_word(summary.get("mobile_choice")),
        "status": project.status if project else "unknown",
        "must_have": (summary.get("priorities", {}) or {}).get("must_have", []),
        "features": _built_features(blueprint, files),
        "screens": _screens(files),
        "integrations": _integrations(blueprint, secret_names),
        "deployment": _deployment(dep),
        "security": _security(cert, reviews),
        "qa": _qa(qa, qa_report),
        "built_at": blueprint_created,
        "file_count": len(files),
        "has_payments": any(i["connection"] == "in_app_oauth" or "stripe" in i["name"].lower()
                            for i in _integrations(blueprint, secret_names)),
        "menu": _menu(files),
    }


def _menu(files: list[dict]) -> dict:
    """Whether a menu feature was actually BUILT, and whether the PDF-upload path
    was built — derived from the real generated files, so the guide describes only
    what exists (and mentions the review step ONLY when the PDF path shipped)."""
    paths = [(f.get("filepath") or f.get("filename") or "").lower() for f in files]
    is_pdf = any("menu_upload" in p or "menu/review" in p for p in paths)
    has_menu = is_pdf or any("routes/menu.py" in p or "admin/menu" in p for p in paths)
    return {"built": has_menu, "is_pdf": is_pdf}
