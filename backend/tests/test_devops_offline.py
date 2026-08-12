"""Week 7 DevOps — offline proof. Zero AWS, zero LLM spend, no Docker daemon.

Every check here is written so it can FAIL for the reason it exists (the standing
principle): the isolation test proves the name sets are DISJOINT (not merely that
one run looks fine); the redaction test proves the sentinel is gone AND that it
reappears with the filter off; the health classifier is fed text that mixes a
transient signal with a security refusal to prove the unsafe class wins (a
milder replay of defect #6 would be auto-restarting a control that is refusing on
purpose); the cost tripwire is fired in the future to prove it can fire.

The REAL docker build/run/health/teardown + the live cross-tenant DB-rejection
proof live in tests/test_devops_local_live.py (needs the Docker socket).

Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tests/test_devops_offline.py
"""
import asyncio
import logging
import io
import os
import sys
import tempfile

from cryptography.fernet import Fernet

from app.config import settings
# A real key so the encrypted store is exercised (never plaintext).
settings.secrets_enc_key = Fernet.generate_key().decode()

from app.devops import cost, health, manifest, naming, secrets_store, sizing
from app.devops.drivers import aws as aws_driver

_failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}"
          + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


def bp(tier: str) -> dict:
    return {"cloud_config": {"tier": tier, "server_size": "x", "autoscaling": False}}


# ------------------------------------------------------------------ A. sizing
def test_sizing():
    print("\nA. Sizing (STEP 1) — tier -> concrete server")
    small = sizing.decide(bp("small"), {"user_count": "5", "budget": "15"})
    check("small -> single EC2 t3.micro",
          small.strategy == "ec2_single" and small.instance_type == "t3.micro",
          f"{small.strategy}/{small.instance_type}")
    large = sizing.decide(bp("large"), {"user_count": "200000"})
    check("large -> ECS (not a single EC2)",
          large.strategy == "ecs" and large.autoscaling is True, large.strategy)

    # The mismatch warning must FIRE when scale contradicts the tier ...
    mism = sizing.decide(bp("small"), {"user_count": "500000"})
    check("scale/tier mismatch raises a warning", len(mism.warnings) == 1)
    # ... and be ABSENT when they agree (else the warning proves nothing).
    ok = sizing.decide(bp("small"), {"user_count": "10"})
    check("no spurious warning when tier fits", ok.warnings == [])


# ------------------------------------------------------------------ B. isolation
def test_isolation():
    print("\nB. Isolation (naming) — enforced by construction")
    a = naming.names(101, "Coffee Shop")
    a2 = naming.names(101, "Coffee Shop")
    b = naming.names(102, "Coffee Shop")   # same NAME, different project

    check("names are a pure function of project_id (stable)", a == a2)

    # The strongest offline proof: the two projects share NO resource identifier.
    shared_keys = ["network", "db_container", "backend_container",
                   "frontend_container", "caddy_container", "db_volume",
                   "db_user", "db_password", "compose_project", "subdomain",
                   "image_backend", "image_frontend"]
    collisions = [k for k in shared_keys if a[k] == b[k]]
    check("two projects share NO container/network/db/subdomain name",
          collisions == [], f"collisions: {collisions}")

    # Same human name, different subdomain (the random suffix does its job).
    check("identical project names get distinct subdomains",
          a["subdomain"] != b["subdomain"], f"{a['subdomain']} vs {b['subdomain']}")
    # Suffix is stable across calls (URL doesn't change between deploy & health).
    check("subdomain suffix is stable", a["subdomain"] == a2["subdomain"])
    # DB password stable + distinct per project.
    check("db password stable per project", a["db_password"] == a2["db_password"])
    check("db password differs across projects",
          a["db_password"] != b["db_password"])
    # A bad project_id must never fall back to a shared default.
    try:
        naming.names(0, "x")
        check("rejects a non-positive project_id", False)
    except ValueError:
        check("rejects a non-positive project_id", True)


# ------------------------------------------------------------------ C. manifest
def _synthetic_backend(entrypoint: bool = True, extra_import: str = "stripe"):
    models = ("from sqlalchemy.orm import DeclarativeBase\n"
              "class Base(DeclarativeBase): pass\n")
    router = (f"import {extra_import}\nimport os\n"
              "from fastapi import APIRouter\nrouter = APIRouter()\n") if extra_import \
        else ("import os\nfrom fastapi import APIRouter\nrouter = APIRouter()\n")
    files = [
        {"id": 1, "ticket_id": "FND-1", "filename": "models.py",
         "filepath": "backend/app/models.py", "content": models,
         "agent_type": "backend"},
        {"id": 2, "ticket_id": "BE-1", "filename": "orders.py",
         "filepath": "backend/app/routes/orders.py", "content": router,
         "agent_type": "backend"},
    ]
    if entrypoint:
        files.append({
            "id": 3, "ticket_id": "APP-1", "filename": "main.py",
            "filepath": "backend/app/main.py",
            "content": ("from fastapi import FastAPI\napp = FastAPI()\n"),
            "agent_type": "backend"})
    return files


def test_manifest():
    print("\nC. Manifest (STEP 2) — assemble + requirements + Dockerfiles")
    root = tempfile.mkdtemp(prefix="devops-test-")
    names = naming.names(201, "Shop")
    m = manifest.build(_synthetic_backend(), root, names,
                       subdomain=names["subdomain"], local=True)

    # requirements: base set present, scanned import mapped, no junk.
    reqs = m.requirements
    check("requirements has the base runtime (fastapi/uvicorn/asyncpg)",
          all(p in reqs for p in ("fastapi", "uvicorn", "asyncpg")))
    check("scanned 3rd-party import lands in requirements ('stripe')",
          "stripe" in reqs)
    # It must be able to fail: a build with NO 3rd-party import must NOT list it.
    root2 = tempfile.mkdtemp(prefix="devops-test-")
    m2 = manifest.build(_synthetic_backend(extra_import=""), root2, names,
                        subdomain=names["subdomain"], local=True)
    check("no phantom dependency when nothing imports it",
          "stripe" not in m2.requirements)

    check("app module discovered (backend.app.main)",
          m.app_module == "backend.app.main", str(m.app_module))
    check("backend Dockerfile written",
          os.path.exists(os.path.join(m.backend_context, "Dockerfile")))
    check("alias shim written (mixed import styles resolve)",
          os.path.exists(os.path.join(m.backend_context, "srv", "sitecustomize.py")))
    check("bootstrap written (schema create -> uvicorn)",
          os.path.exists(os.path.join(m.backend_context, "srv",
                                      "_devops_bootstrap.py")))
    check("compose written", os.path.exists(m.compose_path))

    # no-entrypoint MUST be reported as a failure ...
    root3 = tempfile.mkdtemp(prefix="devops-test-")
    m3 = manifest.build(_synthetic_backend(entrypoint=False), root3, names,
                        subdomain=names["subdomain"], local=True)
    check("missing FastAPI entrypoint is a reported failure",
          any("no FastAPI entrypoint" in f for f in m3.failures))
    # ... and ABSENT when the entrypoint exists (else the check is decorative).
    check("no false entrypoint failure when it exists",
          not any("no FastAPI entrypoint" in f for f in m.failures))

    # Caddyfile: local uses internal CA; aws uses Let's Encrypt for the domain.
    local_caddy = open(os.path.join(m.caddy_context, "Caddyfile")).read()
    check("local Caddyfile uses an internal cert (not LE)",
          "tls internal" in local_caddy)
    root4 = tempfile.mkdtemp(prefix="devops-test-")
    m4 = manifest.build(_synthetic_backend(), root4, names,
                        subdomain=names["subdomain"], local=False,
                        le_email="x@y.com", use_images=True,
                        image_refs={"backend": "r/b", "frontend": "r/f",
                                    "caddy": "r/c"})
    aws_caddy = open(os.path.join(m4.caddy_context, "Caddyfile")).read()
    check("aws Caddyfile uses Let's Encrypt (email + real host, no internal)",
          "tls internal" not in aws_caddy and "x@y.com" in aws_caddy
          and names["subdomain"] in aws_caddy)


# ------------------------------------------------------------------ D. secrets
def test_secrets():
    print("\nD. Secrets (STEP 5) — encrypted + kept out of logs, provably")
    token = secrets_store.encrypt("super-secret-value")
    check("value is encrypted at rest (ciphertext != plaintext)",
          token != "super-secret-value" and secrets_store.decrypt(token)
          == "super-secret-value")

    # env-file: 0600 perms, keys present, no newline injection.
    d = tempfile.mkdtemp(prefix="devops-test-")
    path = secrets_store.write_env_file(d, {"OPENAI_API_KEY": "abc",
                                            "X": "line1\nline2"})
    mode = oct(os.stat(path).st_mode & 0o777)
    check("env-file is 0600", mode == "0o600", mode)
    body = open(path).read()
    check("env-file has the key", "OPENAI_API_KEY=abc" in body)
    check("newlines in a value can't inject a line", body.count("\n") == 2)

    # Redaction, BOTH directions.
    SENTINEL = "SECRET-sk-live-abcdef1234567890"
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.addFilter(secrets_store.redactor)
    root = logging.getLogger()
    root.addHandler(handler)
    prev_level = root.level
    root.setLevel(logging.INFO)
    try:
        secrets_store.guard([SENTINEL])
        logging.getLogger("devops.x").info("connecting with token=%s", SENTINEL)
        handler.flush()
        with_filter = buf.getvalue()
        check("secret is redacted from logs",
              SENTINEL not in with_filter and "***REDACTED***" in with_filter)

        # It must be able to fail: remove the filter, the sentinel reappears.
        handler.removeFilter(secrets_store.redactor)
        buf.truncate(0); buf.seek(0)
        logging.getLogger("devops.x").info("connecting with token=%s", SENTINEL)
        handler.flush()
        without_filter = buf.getvalue()
        check("without the redactor the sentinel WOULD appear (filter proven)",
              SENTINEL in without_filter)
    finally:
        secrets_store.unguard()
        root.removeHandler(handler)
        root.setLevel(prev_level)

    # Refuse to operate with no key rather than silently hold plaintext.
    saved = settings.secrets_enc_key
    settings.secrets_enc_key = None
    try:
        secrets_store.encrypt("x")
        check("refuses to encrypt without a key", False)
    except RuntimeError:
        check("refuses to encrypt without a key", True)
    finally:
        settings.secrets_enc_key = saved


# ------------------------------------------------------------------ E. cost
def test_cost():
    print("\nE. Cost — from the concrete resources, with a staleness tripwire")
    szg = sizing.decide(bp("small"), {})
    local = cost.estimate(szg, "local")
    check("local cost basis is a projection", local.basis == "projected_aws_small")
    check("t3.micro line + IPv4 line are both in the breakdown",
          any("t3.micro" in k for k in local.breakdown)
          and "public ipv4" in local.breakdown)
    check("estimate is a plausible non-zero monthly", 8 <= local.monthly_usd <= 20,
          str(local.monthly_usd))
    aws = cost.estimate(szg, "aws")
    check("aws basis records the billed server", aws.basis.startswith("billed_aws_"))

    # Tripwire must be quiet now and FIRE in the future (proving it can fire).
    check("rates are fresh today", cost.rates_stale(today=cost._RATE_ASOF) is False)
    check("rate staleness tripwire fires in the future",
          cost.rates_stale(today="2099-01-01") is True)


# ------------------------------------------------------------------ F. health
def test_health():
    print("\nF. Health classify — auto-fix ONLY for transient infra")
    sec = health.classify("RuntimeError: refusing to start: missing AUTH0_DOMAIN "
                           "and allow_origins=['*'] with credentials")
    check("security refusal is not auto-fixable",
          sec.kind == health.SECURITY_REFUSAL and not sec.autofixable)
    miss = health.classify("Missing required environment variable STRIPE_SECRET_KEY")
    check("missing config is not auto-fixable (never fake a secret)",
          miss.kind == health.MISSING_CONFIG and not miss.autofixable)
    app = health.classify("Traceback (most recent call last):\nImportError: x")
    check("app code error escalates, not auto-fixed",
          app.kind == health.APP_ERROR and not app.autofixable)
    tr = health.classify("could not connect to server: Connection refused\n"
                         "the database system is starting up")
    check("transient db-not-ready IS auto-fixable",
          tr.kind == health.TRANSIENT_INFRA and tr.autofixable)
    unk = health.classify("something totally unrecognised happened")
    check("unknown failures escalate (no guessing)",
          unk.kind == health.UNKNOWN and not unk.autofixable)

    # THE defect-#6-shaped check: a transient signal PLUS a security refusal must
    # classify as the security refusal, never the auto-fixable transient one.
    mixed = health.classify("connection refused ... authorization check failed; "
                            "refusing to start")
    check("a security refusal wins over a co-occurring transient signal",
          not mixed.autofixable, mixed.kind)


# ------------------------------------------------------------------ G. sec gate
def test_security_gate():
    print("\nG. Security gate (STEP 0) — fail-closed at the deploy edge")
    from app.devops import orchestrator as orch

    class _FakeRedis:
        def __init__(self, val): self.val = val
        async def get(self, *_a, **_k): return self.val

    async def _run_case(cert_json, drifted, expect_ok):
        orig_redis = orch.redis_client
        orig_drift = orch.reviewer_orchestrator.drifted_files
        orch.redis_client = _FakeRedis(cert_json)

        async def _fake_drift(_pid, _cert): return drifted
        orch.reviewer_orchestrator.drifted_files = _fake_drift
        try:
            return await orch._security_gate(1)
        finally:
            orch.redis_client = orig_redis
            orch.reviewer_orchestrator.drifted_files = orig_drift

    import json as _json
    passing = _json.dumps({"passed": True, "file_hashes": {"1": "a"}})
    ok, _reason, skipped = asyncio.run(_run_case(passing, [], True))
    check("certified when cert passes and nothing drifted", ok is True)
    check("a real passing cert is NOT flagged skipped", skipped is False)
    ok, _reason, _s = asyncio.run(_run_case(passing, [1, 2], False))
    check("BLOCKED when files drifted from the certificate", ok is False)
    ok, _reason, _s = asyncio.run(_run_case(_json.dumps({"passed": False}), [], False))
    check("BLOCKED when the certificate is not passing", ok is False)
    ok, _reason, _s = asyncio.run(_run_case(None, [], False))
    check("BLOCKED when there is no certificate at all (fail-closed)", ok is False)
    # Debug skip cert: may deploy (drift proven) but flagged skipped so the deploy is
    # never LABELLED security-certified (security_review_enabled=False path).
    skipcert = _json.dumps({"passed": True, "security_review_skipped": True,
                            "file_hashes": {"1": "a"}})
    ok, _reason, skipped = asyncio.run(_run_case(skipcert, [], True))
    check("skip cert may deploy (drift still proven)", ok is True)
    check("skip cert is flagged skipped (deploy must not claim certification)",
          skipped is True)


# ------------------------------------------------------------------ H. AWS pure
def test_aws_pure_functions():
    print("\nH. AWS pure functions — testable without spending a cent")
    import json as _json
    pol = _json.loads(aws_driver.ecr_lifecycle_policy(keep_last=3))
    check("ECR lifecycle expires untagged + keeps last N",
          any(r["selection"]["tagStatus"] == "untagged" for r in pol["rules"])
          and any("imageCountMoreThan" in r["selection"].get("countType", "")
                  for r in pol["rules"]))
    batch = aws_driver.route53_upsert_batch("app-x.apps.rajkumarai.dev", "1.2.3.4")
    rr = batch["Changes"][0]
    check("Route53 batch UPSERTs the A record -> ip",
          rr["Action"] == "UPSERT"
          and rr["ResourceRecordSet"]["Type"] == "A"
          and rr["ResourceRecordSet"]["ResourceRecords"][0]["Value"] == "1.2.3.4")
    tags = {t["Key"]: t["Value"] for t in aws_driver._tags(7, ephemeral=True)}
    check("every AWS resource is tagged for by-tag teardown",
          tags.get("Project") == "ai-org" and tags.get("project_id") == "7"
          and tags.get("ephemeral") == "true"
          and tags.get("created_by") == "devops")


def test_email_validator_reqs():
    print("\nH. Requirements: Pydantic EmailStr -> email-validator (regression, project 487)")
    from app.qa import assembly

    # Detector: positive on EmailStr / pydantic[email], negative otherwise.
    check("detector: EmailStr triggers email-validator",
          assembly.needs_email_validator(
              ["from pydantic import EmailStr\n    email: EmailStr\n"]) is True)
    check("detector: pydantic[email] triggers email-validator",
          assembly.needs_email_validator(["deps = 'pydantic[email]'"]) is True)
    check("detector: a plain model does NOT trigger it",
          assembly.needs_email_validator(["class User:\n    name: str\n"]) is False)

    # Deployed requirements.txt: EmailStr present -> email-validator; absent -> not.
    with_email = _synthetic_backend()
    with_email[0]["content"] = ("from pydantic import BaseModel, EmailStr\n"
                                "class UserIn(BaseModel):\n    email: EmailStr\n")
    reqs = manifest._backend_requirements(with_email)
    check("deployed requirements include email-validator when EmailStr is used",
          "email-validator" in reqs, reqs)
    reqs_none = manifest._backend_requirements(_synthetic_backend())
    check("deployed requirements omit email-validator when no email field is used",
          "email-validator" not in reqs_none, reqs_none)

    # project 661: File/Form routes (the menu PDF upload) need python-multipart,
    # which no import statement names, so the app dies at startup with
    # 'Form data requires "python-multipart" to be installed'.
    check("detector: UploadFile triggers python-multipart",
          assembly.needs_python_multipart(
              ["async def up(file: UploadFile = File(...)): ...\n"]) is True)
    check("detector: Form(...) triggers python-multipart",
          assembly.needs_python_multipart(["x: str = Form(...)"]) is True)
    check("detector: a plain JSON route does NOT trigger it",
          assembly.needs_python_multipart(
              ["async def create(body: ItemIn): return body\n"]) is False)
    with_upload = _synthetic_backend()
    with_upload[0]["content"] = ("from fastapi import APIRouter, UploadFile, File\n"
                                 "router = APIRouter()\n"
                                 "@router.post('/upload')\n"
                                 "async def up(file: UploadFile = File(...)): return {}\n")
    reqs_up = manifest._backend_requirements(with_upload)
    check("deployed requirements include python-multipart when File/UploadFile is used",
          "python-multipart" in reqs_up, reqs_up)
    check("deployed requirements omit python-multipart for a plain JSON app",
          "python-multipart" not in manifest._backend_requirements(_synthetic_backend()))


def main():
    print("=" * 64)
    print("DevOps offline proof (no AWS, no LLM, no Docker daemon)")
    print("=" * 64)
    test_sizing()
    test_isolation()
    test_manifest()
    test_secrets()
    test_cost()
    test_health()
    test_security_gate()
    test_email_validator_reqs()
    test_aws_pure_functions()

    print("\n" + "=" * 64)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    main()
