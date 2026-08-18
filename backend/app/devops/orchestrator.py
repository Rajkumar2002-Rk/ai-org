"""DevOps orchestrator (Week 7) — STEP 1..7, silently.

Order and the guarantees that shape it:

  0. FAIL-CLOSED SECURITY GATE. Before anything is built, re-check that the Opus
     certificate covers EXACTLY the files about to ship (reviewer.drifted_files).
     No certificate, or any drift, blocks the deploy — a deployment can never ship
     code the security review never saw (defect #6, extended to the deploy edge).
  1. sizing.decide          — read cloud_config, pick a concrete server.
  2. manifest.build         — assemble the project, generate requirements/Dockerfiles.
     (build happens inside the driver, from the manifest)
  3. driver.build_and_up    — build images, run an ISOLATED per-project stack.
  4. (schema)               — the backend bootstrap create_all's the generated schema.
  5. secrets                — injected as a 0600 env-file, redacted from logs.
  6. SSL + domain           — Caddy (self-signed local / Let's Encrypt on AWS).
  7. health.probe           — ping the live URL 10s x 2min; ONE infra-only auto-fix.

The agent never talks to the user; the API layer exposes a live URL + counts.
"""
import json
import logging
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app import usage
from app.config import settings
from app.database import async_session
from app.devops import cost as cost_mod
from app.devops import health, manifest, naming, secrets_store, sizing as sizing_mod
from app.devops.drivers.base import DeployRequest
from app.models import Blueprint, Deployment, GeneratedFile, Project
from app.redis_client import redis_client
from app.reviewer import orchestrator as reviewer_orchestrator

logger = logging.getLogger("devops.orchestrator")


def _get_driver(target: str):
    if target == "aws":
        from app.devops.drivers.aws import AwsDriver
        return AwsDriver()
    from app.devops.drivers.local import LocalDockerDriver
    return LocalDockerDriver()


def _project_name(summary: dict) -> str:
    return (summary.get("business_name") or summary.get("name")
            or summary.get("build") or "app")


async def _load_files(project_id: int) -> list[dict]:
    async with async_session() as db:
        rows = (await db.execute(
            select(GeneratedFile.id, GeneratedFile.ticket_id, GeneratedFile.filename,
                   GeneratedFile.filepath, GeneratedFile.content,
                   GeneratedFile.agent_type)
            .where(GeneratedFile.project_id == project_id)
            .order_by(GeneratedFile.id)
        )).all()
    return [{"id": r[0], "ticket_id": r[1], "filename": r[2], "filepath": r[3],
             "content": r[4], "agent_type": r[5]} for r in rows]


def _has_menu_pdf(files: list[dict]) -> bool:
    """True when this app shipped the menu PDF-upload/extraction feature (MENU-3),
    identified by its route file. Drives the scoped platform vision-key injection."""
    for f in files:
        path = (f.get("filepath") or f.get("filename") or "").lower()
        if "menu_upload" in path or f.get("ticket_id") == "MENU-3":
            return True
    return False


async def _tests_passed(project_id: int) -> int:
    raw = await redis_client.get(f"qa_report:{project_id}")
    if raw:
        try:
            return int(json.loads(raw).get("passed", 0))
        except Exception:
            pass
    return 0


async def _security_gate(project_id: int) -> tuple[bool, str, bool]:
    """Fail-closed: prove the certificate covers exactly what will deploy.

    Returns (may_deploy, reason, skipped). `may_deploy` requires: a certificate
    EXISTS, it says passed, and NO file has drifted from what it fingerprinted. Any
    "we can't tell" resolves to NOT deployable — never the reverse. `skipped` is True
    when the (passing) certificate is the debug skip cert (security_review_skipped):
    the drift guarantee still holds, but the code was NOT security-reviewed, so the
    caller must not label the deploy as security-certified.
    """
    raw = await redis_client.get(f"security_cert:{project_id}")
    cert = json.loads(raw) if raw else {}
    if not cert:
        return False, ("No security certificate exists for this build — it cannot "
                       "be shown to have passed security review, so it will not be "
                       "deployed."), False
    if not cert.get("passed", False):
        return False, ("The security certificate for this build is not passing, so "
                       "it will not be deployed."), False
    drifted = await reviewer_orchestrator.drifted_files(project_id, cert)
    if drifted:
        return False, (f"The code changed since it was security-certified "
                       f"({len(drifted)} file(s) drifted from the certificate). "
                       f"Deploying would ship code the security review never saw; "
                       f"blocking and escalating for re-certification."), False
    return True, "certified", bool(cert.get("security_review_skipped", False))


async def _set_row(deployment_id: int, **fields) -> None:
    async with async_session() as db:
        row = await db.get(Deployment, deployment_id)
        if row is not None:
            for k, v in fields.items():
                setattr(row, k, v)
            await db.commit()


async def run(project_id: int) -> dict:
    run_id = uuid.uuid4().hex
    usage_token = usage.set_run_context(run_id=run_id, project_id=project_id,
                                        stage="devops")
    target = settings.deploy_target
    root = None
    driver = None
    req = None
    try:
        # ---- load context ------------------------------------------------
        async with async_session() as db:
            project = await db.get(Project, project_id)
            summary = (json.loads(project.summary_json)
                       if project and project.summary_json else {})
            bp_row = (await db.execute(
                select(Blueprint.id, Blueprint.blueprint_json)
                .where(Blueprint.project_id == project_id)
                .order_by(Blueprint.id.desc()).limit(1)
            )).first()
        if bp_row is None:
            return {"status": "failed", "reason": "No blueprint to deploy."}
        blueprint_id, blueprint = bp_row[0], json.loads(bp_row[1])

        # ---- STEP 0: fail-closed security gate ---------------------------
        may_deploy, reason, sec_skipped = await _security_gate(project_id)
        # A skipped review still lets a LOCAL deploy proceed (drift is proven), but it
        # is NOT a security certification — never report it as one.
        certified = may_deploy and not sec_skipped
        tests_passed = await _tests_passed(project_id)

        # ---- STEP 1: sizing + cost --------------------------------------
        szg = sizing_mod.decide(blueprint, summary)
        est = cost_mod.estimate(szg, target)
        pname = _project_name(summary)
        names = naming.names(project_id, pname)

        # ---- create the deployment row (deploying) ----------------------
        async with async_session() as db:
            row = Deployment(
                project_id=project_id, run_id=run_id, blueprint_id=blueprint_id,
                target=target, subdomain=names["subdomain"],
                region=settings.aws_region if target == "aws" else None,
                server_type=szg.server_type, status="deploying",
                monthly_cost_estimate=est.monthly_usd, cost_basis=est.basis,
                security_certified=certified, tests_passed=tests_passed,
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            deployment_id = row.id

        if not may_deploy:
            await _set_row(deployment_id, status="failed", error_message=reason)
            logger.error("Deploy blocked for project %s: %s", project_id, reason)
            return {"status": "blocked", "reason": reason, "run_id": run_id,
                    "deployment_id": deployment_id, "security_certified": False,
                    "tests_passed": tests_passed}
        if sec_skipped:
            logger.warning("Project %s deploying WITHOUT a security review "
                           "(debug skip cert); drift is proven but the code was not "
                           "reviewed. security_certified=False.", project_id)

        # ---- STEP 5 (prep): real secrets only; never fabricate config ----
        files = await _load_files(project_id)
        env: dict[str, str] = {}
        secret_names: list[str] = []
        if settings.secrets_enc_key:
            try:
                secrets = await secrets_store.get_secrets(project_id)
                env.update(secrets)
                secret_names = sorted(secrets)
            except Exception:
                logger.exception("Could not load secrets for project %s", project_id)
        else:
            logger.warning("SECRETS_ENC_KEY unset — deploying with no injected "
                           "secrets. If the app needs a key it will fail-fast and "
                           "be escalated (never faked).")

        # Platform-provided menu vision key — injected ONLY for apps that shipped
        # the menu PDF-upload feature (menu_upload.py). Scoped, platform-held
        # (settings.menu_extraction_api_key), distinct from the owner-facing
        # secrets-onboarding gap. Added BEFORE guard() so its value is redacted
        # from logs like any other secret. Absent -> we warn and let the app
        # report scanned-menu reading as unavailable (never faked).
        if _has_menu_pdf(files):
            if settings.menu_extraction_api_key:
                env["MENU_EXTRACTION_API_KEY"] = settings.menu_extraction_api_key
                secret_names = sorted(set(secret_names) | {"MENU_EXTRACTION_API_KEY"})
            else:
                logger.warning("Project %s ships the menu PDF feature but "
                               "MENU_EXTRACTION_API_KEY is unset — scanned-menu "
                               "reading will be unavailable until the platform key "
                               "is configured.", project_id)

        # Register secret VALUES for redaction, and protect the root handlers so
        # nothing in this deploy can emit them.
        secrets_store.guard(env.values())
        secrets_store.protect_root_handlers()

        # ---- STEP 2/3/6: assemble + build + bring up (isolated) ----------
        root = tempfile.mkdtemp(prefix=f"devops-{project_id}-")
        req = DeployRequest(
            project_id=project_id, project_name=pname, files=files, names=names,
            subdomain=names["subdomain"], env=env, sizing=szg, root=root,
            le_email=settings.letsencrypt_email, secret_names=secret_names,
        )
        driver = _get_driver(target)

        auto_fixed = False
        fix_description = None

        res = await driver.build_and_up(req)
        if not res.ok:
            fault = health.classify(res.error or "")
            if fault.autofixable:
                auto_fixed, fix_description = True, (
                    "Bring-up failed transiently; retried the build once. "
                    f"({fault.reason})")
                res = await driver.build_and_up(req)
            if not res.ok:
                await driver.teardown(req)
                await _set_row(deployment_id, status="failed",
                               auto_fixed=auto_fixed, fix_description=fix_description,
                               error_message=(res.error or fault.reason)[:2000],
                               server_type=res.server_type or szg.server_type)
                return {"status": "failed", "run_id": run_id,
                        "deployment_id": deployment_id,
                        "reason": fault.reason, "security_certified": certified,
                        "tests_passed": tests_passed, "auto_fixed": auto_fixed}

        # ---- STEP 7: LAYERED health probe + one infra-only auto-fix -----
        # The probe must prove the BACKEND actually answers — a live frontend edge (a 404
        # homepage) can no longer mask a crash-looping backend (the run-1105 false-"live").
        probe_url = res.probe_url or res.live_url
        has_frontend = any(manifest._is_frontend(f) for f in req.files)
        p = await health.probe(probe_url, res.verify_tls,
                               settings.devops_health_interval,
                               settings.devops_health_timeout, has_frontend=has_frontend)
        health_attempts = p.attempts
        if not p.healthy and not auto_fixed:
            diag = await driver.diagnostics(req)
            fault = health.classify(diag, p)
            if fault.autofixable:
                auto_fixed, fix_description = True, (
                    f"App was not healthy on first bring-up; restarted the "
                    f"containers once. ({fault.reason})")
                await driver.restart(req)
                p = await health.probe(probe_url, res.verify_tls,
                                       settings.devops_health_interval,
                                       settings.devops_health_timeout,
                                       has_frontend=has_frontend)
                health_attempts += p.attempts
            if not p.healthy:
                # Name WHICH layer failed so a false "live" can never hide a dead backend.
                layer = p.failed_layer or "app"
                reason = f"The {layer} layer did not become healthy. {fault.reason}"
                await _set_row(deployment_id, status="failed", live_url=res.live_url,
                               ssl_enabled=res.ssl_enabled, ssl_type=res.ssl_type,
                               server_type=res.server_type, auto_fixed=auto_fixed,
                               fix_description=fix_description,
                               health_attempts=health_attempts,
                               image_backend_ref=res.image_backend_ref,
                               image_frontend_ref=res.image_frontend_ref,
                               error_message=reason[:2000])
                await driver.teardown(req)
                return {"status": "failed", "run_id": run_id,
                        "deployment_id": deployment_id, "reason": reason,
                        "security_certified": certified, "tests_passed": tests_passed,
                        "auto_fixed": auto_fixed, "health_attempts": health_attempts,
                        "failed_layer": p.failed_layer}

        # ---- LIVE --------------------------------------------------------
        await _set_row(
            deployment_id, status="live", live_url=res.live_url,
            ssl_enabled=res.ssl_enabled, ssl_type=res.ssl_type,
            server_type=res.server_type, auto_fixed=auto_fixed,
            fix_description=fix_description, health_attempts=health_attempts,
            image_backend_ref=res.image_backend_ref,
            image_frontend_ref=res.image_frontend_ref,
            deployed_at=datetime.now(timezone.utc),
        )
        async with async_session() as db:
            proj = await db.get(Project, project_id)
            if proj is not None:
                proj.status = "deployed"
                await db.commit()

        return {
            "status": "live", "run_id": run_id, "deployment_id": deployment_id,
            "live_url": res.live_url, "ssl_enabled": res.ssl_enabled,
            "ssl_type": res.ssl_type, "server_type": res.server_type,
            "monthly_cost_estimate": float(est.monthly_usd),
            "cost_basis": est.basis, "security_certified": certified,
            "tests_passed": tests_passed, "auto_fixed": auto_fixed,
            "fix_description": fix_description, "health_attempts": health_attempts,
            "target": target,
        }

    except Exception as exc:  # pragma: no cover - never let a deploy crash silently
        logger.exception("DevOps deploy failed for project %s", project_id)
        return {"status": "failed", "reason": str(exc)[:500], "run_id": run_id}
    finally:
        secrets_store.unguard()
        usage.reset_run_context(usage_token)
        if root:
            shutil.rmtree(root, ignore_errors=True)
