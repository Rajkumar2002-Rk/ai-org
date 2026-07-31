"""Week 7 DevOps — LIVE local proof. Real Docker images, real containers, real
HTTPS, real Postgres, real secret injection. No AWS, no LLM spend.

This is the "it actually works" test, deliberately NOT in the free suite (it needs
the Docker socket and takes a couple of minutes) — the same way test_qa_classification
is excluded because it makes real calls.

What it proves, end to end, through the real orchestrator:
  * STEP 0 the fail-closed security gate lets a properly-certified build through;
  * STEP 2/3 a real backend image is built and an ISOLATED stack is brought up;
  * STEP 4 the generated schema is created (a DB-backed endpoint returns 200);
  * STEP 5 a seeded secret is injected into the container (proven via an endpoint
           that reports only whether it is set) AND its value is NOT in the
           deployments row or the returned report;
  * STEP 6 the app is served over HTTPS (Caddy);
  * STEP 7 the health probe passes against the live URL;
  * ISOLATION: two projects get disjoint networks/db/containers, and a container
    on project A's network CANNOT reach project B's database container;
  * TEARDOWN: every resource is sampled before -> during (exists) -> after (gone).

Run (needs the docker socket, which the backend service mounts):
  docker compose run --rm -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tests/test_devops_local_live.py
"""
import asyncio
import json
import sys
import uuid

import httpx
from sqlalchemy import delete, select

from app.config import settings
settings.deploy_target = "local"
settings.devops_health_interval = 3
settings.devops_health_timeout = 90
if not settings.secrets_enc_key:
    from cryptography.fernet import Fernet
    settings.secrets_enc_key = Fernet.generate_key().decode()

from app.database import async_session
from app.devops import naming, orchestrator, secrets_store
from app.devops.drivers.base import DeployRequest
from app.devops.drivers.local import LocalDockerDriver, run_cmd
from app.models import Blueprint, Deployment, GeneratedFile, Project
from app.redis_client import redis_client
from app.reviewer import orchestrator as reviewer_orchestrator

_failures: list[str] = []
SECRET_VALUE = f"sk-live-SENTINEL-{uuid.uuid4().hex}"


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


# ---- a minimal, real, DB-backed FastAPI app (proves the mechanism) ----------
_DATABASE_PY = '''import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
engine = create_async_engine(os.environ["DATABASE_URL"])
Session = async_sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase):
    pass
'''
_MODELS_PY = '''from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
'''
_MAIN_PY = '''import os
from fastapi import FastAPI
from sqlalchemy import select
from app.database import Session
from app.models import Item
app = FastAPI()

@app.get("/config-check")
def config_check():
    # Reports only WHETHER the secret arrived — never its value.
    return {"has_demo_secret": bool(os.getenv("DEMO_SECRET"))}

@app.get("/items")
async def items():
    async with Session() as s:
        rows = (await s.execute(select(Item))).scalars().all()
        return [{"id": r.id, "name": r.name} for r in rows]
'''


def _files():
    def f(fid, ticket, path, content):
        return {"id": fid, "ticket_id": ticket, "filename": path.split("/")[-1],
                "filepath": path, "content": content, "agent_type": "backend"}
    return [
        f(0, "FND-2", "backend/app/database.py", _DATABASE_PY),
        f(0, "FND-1", "backend/app/models.py", _MODELS_PY),
        f(0, "APP-1", "backend/app/main.py", _MAIN_PY),
    ]


async def _seed_project() -> int:
    async with async_session() as db:
        proj = Project(prompt="devops live test", status="tested",
                       summary_json=json.dumps({"business_name": "Live Test Shop",
                                                "user_count": "5", "budget": "15"}))
        db.add(proj)
        await db.commit()
        await db.refresh(proj)
        pid = proj.id
        bp = Blueprint(project_id=pid, blueprint_json=json.dumps({
            "cloud_config": {"tier": "small", "server_size": "1 vCPU, 1 GB",
                             "autoscaling": False},
            "api_endpoints": [], "llm_routing": {},
        }))
        db.add(bp)
        for fl in _files():
            db.add(GeneratedFile(project_id=pid, ticket_id=fl["ticket_id"],
                                 filename=fl["filename"], filepath=fl["filepath"],
                                 content=fl["content"], agent_type="backend"))
        await db.commit()
    # Seed a secret to inject, and a passing, drift-free certificate.
    await secrets_store.set_secret(pid, "DEMO_SECRET", SECRET_VALUE)
    hashes = await reviewer_orchestrator.file_hashes(pid)
    cert = {"passed": True, "model_used": "claude-opus-4-8", "file_hashes": hashes,
            "issues_found": 0, "issues_fixed": 0, "files_reviewed": len(hashes)}
    await redis_client.set(f"security_cert:{pid}", json.dumps(cert), ex=3600)
    await redis_client.set(f"qa_report:{pid}",
                           json.dumps({"total": 7, "passed": 7, "failed": 0}), ex=3600)
    return pid


async def _cleanup(pid: int):
    async with async_session() as db:
        await db.execute(delete(Deployment).where(Deployment.project_id == pid))
        await db.execute(delete(GeneratedFile).where(GeneratedFile.project_id == pid))
        await db.execute(delete(Blueprint).where(Blueprint.project_id == pid))
        from app.models import Secret
        await db.execute(delete(Secret).where(Secret.project_id == pid))
        await db.execute(delete(Project).where(Project.id == pid))
        await db.commit()
    for k in ("security_cert", "qa_report", "deploy_report"):
        await redis_client.delete(f"{k}:{pid}")


async def _container_exists(name: str) -> bool:
    code, out = await run_cmd(["docker", "ps", "-a", "--filter", f"name=^{name}$",
                               "--format", "{{.Names}}"], timeout=30)
    return name in out


async def _teardown_names(names: dict):
    d = LocalDockerDriver()
    req = DeployRequest(project_id=names["project_id"], project_name="", files=[],
                        names=names, subdomain=names["subdomain"], env={},
                        sizing=None, root="")
    await d.teardown(req)


async def main():
    print("=" * 64)
    print("DevOps LIVE local proof (real Docker, real HTTPS, no AWS/LLM)")
    print("=" * 64)

    pid_a = await _seed_project()
    pid_b = await _seed_project()
    names_a = naming.names(pid_a, "Live Test Shop")
    names_b = naming.names(pid_b, "Live Test Shop")

    try:
        print(f"\nDeploying project A ({pid_a}) through the real orchestrator…")
        rep_a = await orchestrator.run(pid_a)
        check("A: deployment went LIVE", rep_a.get("status") == "live",
              json.dumps(rep_a)[:300])
        check("A: ssl recorded honestly as self_signed_local",
              rep_a.get("ssl_type") == "self_signed_local")
        check("A: security_certified true (cert covered the deployed files)",
              rep_a.get("security_certified") is True)
        check("A: honest cost is a projection with a non-zero number",
              rep_a.get("cost_basis", "").startswith("projected_aws")
              and (rep_a.get("monthly_cost_estimate") or 0) > 0)
        check("A: the secret VALUE is not in the returned report",
              SECRET_VALUE not in json.dumps(rep_a))

        # The live app: reachable over HTTPS, DB works, secret injected.
        if rep_a.get("live_url"):
            port = rep_a["live_url"].rsplit(":", 1)[1]
            base = f"https://host.docker.internal:{port}"
            async with httpx.AsyncClient(verify=False, timeout=10) as c:
                r_api = await c.get(f"{base}/openapi.json")
                check("A: live app serves its API over HTTPS (200)",
                      r_api.status_code == 200, str(r_api.status_code))
                r_items = await c.get(f"{base}/items")
                check("A: DB-backed endpoint works (schema was created)",
                      r_items.status_code == 200, str(r_items.status_code))
                r_cfg = await c.get(f"{base}/config-check")
                check("A: seeded secret was injected into the container",
                      r_cfg.status_code == 200
                      and r_cfg.json().get("has_demo_secret") is True)

        # The deployments row must not contain the secret VALUE anywhere.
        async with async_session() as db:
            row = (await db.execute(
                select(Deployment).where(Deployment.project_id == pid_a)
                .order_by(Deployment.id.desc()).limit(1)
            )).scalar_one()
            row_text = " ".join(str(getattr(row, c.name)) for c in row.__table__.columns)
        check("A: secret VALUE never lands in the deployments row",
              SECRET_VALUE not in row_text)
        check("A: deployments row is LIVE with a subdomain + server_type",
              row.status == "live" and row.subdomain and row.server_type)

        print(f"\nDeploying project B ({pid_b}) — isolation check…")
        rep_b = await orchestrator.run(pid_b)
        check("B: deployment went LIVE", rep_b.get("status") == "live",
              json.dumps(rep_b)[:300])

        # Structural: no shared resource name.
        shared = [k for k in ("network", "db_container", "backend_container",
                              "db_user", "db_volume", "subdomain")
                  if names_a[k] == names_b[k]]
        check("A and B share NO resource name", shared == [], str(shared))

        # Runtime crossing: a container on A's network can reach A's DB but NOT
        # B's DB container (different network) — isolation proven by the crossing
        # being REFUSED, not merely by nothing happening.
        code_self, _ = await run_cmd(
            ["docker", "run", "--rm", "--network", names_a["network"],
             "postgres:16-alpine", "pg_isready", "-h", names_a["db_container"],
             "-t", "3"], timeout=60)
        check("A's own DB is reachable on A's network", code_self == 0)
        code_cross, _ = await run_cmd(
            ["docker", "run", "--rm", "--network", names_a["network"],
             "postgres:16-alpine", "pg_isready", "-h", names_b["db_container"],
             "-t", "3"], timeout=60)
        check("A CANNOT reach B's database container (network isolation)",
              code_cross != 0, f"cross exit={code_cross}")

        # Teardown: sample DURING (exists) then AFTER (gone).
        during_a = await _container_exists(names_a["backend_container"])
        during_b = await _container_exists(names_b["db_container"])
        check("DURING: A backend + B db containers exist", during_a and during_b)
        await _teardown_names(names_a)
        await _teardown_names(names_b)
        after_a = await _container_exists(names_a["backend_container"])
        after_b = await _container_exists(names_b["db_container"])
        check("AFTER: A backend container is gone", not after_a)
        check("AFTER: B db container is gone", not after_b)
        code_net, out_net = await run_cmd(
            ["docker", "network", "inspect", names_a["network"]], timeout=30)
        check("AFTER: A network is gone", code_net != 0)

    finally:
        # Belt-and-suspenders teardown even if an assertion above failed.
        await _teardown_names(names_a)
        await _teardown_names(names_b)
        await _cleanup(pid_a)
        await _cleanup(pid_b)
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
