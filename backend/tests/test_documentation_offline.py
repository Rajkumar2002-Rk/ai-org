"""Week 8 Documentation — offline proof. Zero LLM spend (codegen.generate is
patched), no network.

Every check is written so it can FAIL for its reason (the standing principle).
The point of this agent is HONESTY, so the tests attack fabrication:

* run the real agent against a REAL partial project (342: qa_failed, never
  deployed) and prove the handoff reports "not deployed", the real failed-test
  count, and honest security — never a fabricated green;
* prove the agent is READ-ONLY — every other table's row count is unchanged, only
  `documents` grows;
* prove the demo script is built from REAL screens only (no Stripe screen unless a
  Stripe page exists), and the handoff marks Stripe "not connected" when no secret
  backs it;
* prove a green fixture reports the real live URL / cost / passed counts;
* prove missing data (support contact) gets an honest answer, never an invented one.

Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tests/test_documentation_offline.py
"""
import asyncio
import json
import sys

from sqlalchemy import delete, func, select

import app.codegen as codegen
from app.database import async_session
from app.documentation import datasource, generators, orchestrator
from app.models import (Blueprint, CodeReview, Deployment, Document,
                        GeneratedFile, Project, QAResult)
from app.redis_client import redis_client

_failures: list[str] = []
_seeded: list[int] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


# LLM is patched so the suite is free; the screen SET / handoff numbers come from
# real data, NOT the LLM, so patching cannot make the honesty checks pass falsely.
async def _canned(model, system, user, temperature=0.1, bypass_cheap=False):
    return ("Plain-English generated text.", model)

async def _none(model, system, user, temperature=0.1, bypass_cheap=False):
    return (None, model)


async def _seed(*, deployed: bool, cert_passed: bool, qa_pass: int, qa_fail: int,
                stripe: bool, frontend_pages: list[str]) -> int:
    apis = []
    if stripe:
        apis = [{"name": "Stripe Connect", "who_handles": "user",
                 "connection": "in_app_oauth"}]
    tickets = [
        {"id": "FND-1", "title": "Data models", "assigned_to": "backend"},
        {"id": "APP-1", "title": "App entrypoint", "assigned_to": "backend"},
        {"id": "BE-1", "title": "Menu management", "assigned_to": "backend",
         "description": "Add, edit and remove menu items."},
        {"id": "BE-2", "title": "Orders", "assigned_to": "backend",
         "description": "Take and track customer orders."},
    ]
    blueprint = {"cloud_config": {"tier": "small", "server_size": "1 vCPU, 1 GB"},
                 "api_endpoints": [{"path": "/api/menu", "method": "GET"}],
                 "third_party_apis": apis, "sprint_tickets": tickets}
    async with async_session() as db:
        p = Project(prompt="a corner grocery store app", status="tested",
                    summary_json=json.dumps({"business_name": "Corner Grocer",
                                             "mobile_choice": "web", "user_count": "20",
                                             "priorities": {"must_have": ["Menu", "Orders"]}}))
        db.add(p); await db.commit(); await db.refresh(p); pid = p.id
        db.add(Blueprint(project_id=pid, blueprint_json=json.dumps(blueprint)))
        # backend files (built tickets) + frontend pages (screens)
        for tid in ("FND-1", "APP-1", "BE-1", "BE-2"):
            db.add(GeneratedFile(project_id=pid, ticket_id=tid, filename=f"{tid}.py",
                                 filepath=f"backend/app/{tid.lower()}.py",
                                 content="x", agent_type="backend"))
        for page in frontend_pages:
            db.add(GeneratedFile(project_id=pid, ticket_id="FE", filename="page.tsx",
                                 filepath=f"frontend/app/{page}".rstrip("/") + "/page.tsx"
                                 if page else "frontend/app/page.tsx",
                                 content="x", agent_type="frontend"))
        for i in range(qa_pass):
            db.add(QAResult(project_id=pid, run_id="r1", test_name=f"ok{i}",
                            test_level=1, passed=True))
        for i in range(qa_fail):
            db.add(QAResult(project_id=pid, run_id="r1", test_name=f"bad{i}",
                            test_level=1, passed=False,
                            failure_reason="[escalated after retries] boom"))
        db.add(CodeReview(project_id=pid, file_id=1, issues_found=3, issues_fixed=3,
                          security_passed=cert_passed, reviewed_by_model="claude-opus-4-8"))
        if deployed:
            db.add(Deployment(project_id=pid, target="local", status="live",
                              live_url="https://corner-grocer-abc123.apps.rajkumarai.dev",
                              subdomain="corner-grocer-abc123.apps.rajkumarai.dev",
                              server_type="EC2 t3.micro", ssl_enabled=True,
                              ssl_type="lets_encrypt", monthly_cost_estimate=12.38,
                              cost_basis="projected_aws_small", security_certified=cert_passed,
                              tests_passed=qa_pass))
        await db.commit()
    cert = {"passed": cert_passed, "model_used": "claude-opus-4-8",
            "issues_found": 3, "issues_fixed": 3, "files_reviewed": 4}
    await redis_client.set(f"security_cert:{pid}", json.dumps(cert), ex=600)
    _seeded.append(pid)
    return pid


async def _cleanup():
    async with async_session() as db:
        for pid in _seeded:
            for M in (Document, Deployment, CodeReview, QAResult, GeneratedFile,
                      Blueprint):
                await db.execute(delete(M).where(M.project_id == pid))
            await db.execute(delete(Project).where(Project.id == pid))
        await db.commit()
    for pid in _seeded:
        await redis_client.delete(f"security_cert:{pid}")


def _doc(rows: dict, doc_type: str):
    return rows.get(doc_type)


async def _stored_docs(pid: int) -> dict:
    async with async_session() as db:
        r = (await db.execute(select(Document.doc_type, Document.content)
             .where(Document.project_id == pid).order_by(Document.id.desc()))).all()
    out = {}
    for dt, c in r:
        out.setdefault(dt, c)
    return out


# ------------------------------------------------------------------ A. green
async def test_green():
    print("\nA. Green project — reports the real live URL / cost / passes")
    codegen.generate = _canned
    pid = await _seed(deployed=True, cert_passed=True, qa_pass=7, qa_fail=0,
                      stripe=False, frontend_pages=["", "menu", "orders/new"])
    rep = await orchestrator.run(pid)
    check("returns done", rep["status"] == "done", str(rep)[:200])
    check("is_live true + real URL", rep["is_live"] and "corner-grocer" in (rep["live_url"] or ""))
    check("security_passed true", rep["security_passed"] is True)
    check("real test counts (7/7)", rep["tests_passed"] == 7 and rep["tests_total"] == 7)
    check("real monthly cost surfaced", rep["monthly_cost_estimate"] == 12.38)
    docs = await _stored_docs(pid)
    check("all 4 doc types stored",
          set(docs) == {"user_guide", "demo_script", "maintenance_guide", "handoff_summary"})
    handoff = json.loads(docs["handoff_summary"])
    check("handoff live_url is the real one", handoff["deployment"]["live_url"] == rep["live_url"])
    check("handoff has NO 'not deployed' note", not any("not been deployed" in n for n in handoff["honest_notes"]))
    demo = json.loads(docs["demo_script"])
    names = [s["screen"] for s in demo["steps"]]
    check("demo scripts exactly the 3 real screens", demo["screens_count"] == 3, str(names))
    check("demo screen order starts at Home", names and names[0] == "Home", str(names))


# ------------------------------------------------------------------ B. partial (REAL 342)
async def test_partial_real():
    print("\nB. Real partial project 342 (qa_failed, never deployed) — honest")
    codegen.generate = _canned
    async with async_session() as db:
        exists = (await db.execute(select(func.count()).select_from(Project)
                  .where(Project.id == 342))).scalar()
        # snapshot other-table counts for the read-only check
        before = {}
        for name, M in (("projects", Project), ("blueprints", Blueprint),
                        ("generated_files", GeneratedFile), ("qa_results", QAResult),
                        ("code_reviews", CodeReview), ("deployments", Deployment)):
            before[name] = (await db.execute(select(func.count()).select_from(M))).scalar()
    if not exists:
        check("project 342 present (skipping if DB was reset)", False,
              "342 not in DB — seed a partial fixture instead")
        return

    facts = await datasource.gather(342)
    rep = await orchestrator.run(342)
    check("342 returns done", rep["status"] == "done")
    check("342 reports NOT live (no deployment)", rep["is_live"] is False and rep["live_url"] is None)
    check("342 monthly cost is not available (not fabricated)", rep["monthly_cost_estimate"] is None)
    check("342 reports real test failures (not all-passed)",
          facts["qa"]["available"] and facts["qa"]["failed"] > 0,
          f"qa={facts['qa']}")
    docs = await _stored_docs(342)
    handoff = json.loads(docs["handoff_summary"])
    check("342 handoff deployment status = not_deployed",
          handoff["deployment"]["status"] == "not_deployed")
    check("342 handoff notes the not-deployed truth",
          any("not been deployed" in n for n in handoff["honest_notes"]))
    check("342 handoff tests.passed matches datasource (no fabrication)",
          handoff["tests"]["passed"] == facts["qa"]["passed"]
          and handoff["tests"]["failed"] == facts["qa"]["failed"])

    # READ-ONLY: only documents grew.
    async with async_session() as db:
        for name, M in (("projects", Project), ("blueprints", Blueprint),
                        ("generated_files", GeneratedFile), ("qa_results", QAResult),
                        ("code_reviews", CodeReview), ("deployments", Deployment)):
            after = (await db.execute(select(func.count()).select_from(M))).scalar()
            check(f"read-only: {name} row count unchanged", after == before[name],
                  f"{before[name]} -> {after}")
        # clean the docs we just wrote for 342 (leave 342 as found)
        await db.execute(delete(Document).where(Document.project_id == 342))
        await db.commit()


# ------------------------------------------------------------------ C. real screens only
async def test_real_screens_only():
    print("\nC. Demo script + handoff describe only features that EXIST")
    codegen.generate = _canned
    # No Stripe, only menu screen.
    no_pay = await _seed(deployed=False, cert_passed=True, qa_pass=3, qa_fail=0,
                         stripe=False, frontend_pages=["", "menu"])
    facts = await datasource.gather(no_pay)
    check("no-stripe project has_payments false", facts["has_payments"] is False)
    rep = await orchestrator.run(no_pay)
    docs = await _stored_docs(no_pay)
    demo = json.loads(docs["demo_script"])
    screens = " ".join(s["screen"] for s in demo["steps"]).lower()
    check("no invented payment/stripe screen", "stripe" not in screens and "payment" not in screens,
          screens)
    handoff = json.loads(docs["handoff_summary"])
    check("no-stripe handoff has no Stripe integration",
          not any("stripe" in i["name"].lower() for i in handoff["integrations"]))

    # With Stripe designed but NOT connected (no secret).
    pay = await _seed(deployed=False, cert_passed=True, qa_pass=3, qa_fail=0,
                      stripe=True, frontend_pages=["", "settings"])
    pfacts = await datasource.gather(pay)
    check("stripe project has_payments true", pfacts["has_payments"] is True)
    prep = await orchestrator.run(pay)
    phandoff = json.loads((await _stored_docs(pay))["handoff_summary"])
    stripe_i = [i for i in phandoff["integrations"] if "stripe" in i["name"].lower()]
    check("stripe present but connected=false (never claims payments live)",
          stripe_i and stripe_i[0]["connected"] is False)
    check("stripe status says connect in-app / not connected",
          stripe_i and ("connect" in stripe_i[0]["status"].lower()))
    check("handoff notes Stripe not connected",
          any("stripe" in n.lower() for n in phandoff["honest_notes"]))


# ------------------------------------------------------------------ D. honest missing data
async def test_honest_support():
    print("\nD. Missing data (support) → honest, never invented")
    codegen.generate = _none   # force the deterministic fallback path
    pid = await _seed(deployed=False, cert_passed=True, qa_pass=2, qa_fail=0,
                      stripe=False, frontend_pages=[""])
    await orchestrator.run(pid)
    guide = (await _stored_docs(pid))["maintenance_guide"]
    check("maintenance guide answers 'contact support' honestly",
          "no built-in support" in guide.lower() or "whoever set" in guide.lower())
    check("no fabricated support email", "support@" not in guide.lower() and "@" not in guide)
    check("mentions free export / no lock-in", "lock-in" in guide.lower() or "copy" in guide.lower())


async def main():
    print("=" * 64)
    print("Documentation offline proof (no LLM spend, no network)")
    print("=" * 64)
    try:
        await test_green()
        await test_partial_real()
        await test_real_screens_only()
        await test_honest_support()
    finally:
        await _cleanup()
        await redis_client.aclose()

    print("\n" + "=" * 64)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
