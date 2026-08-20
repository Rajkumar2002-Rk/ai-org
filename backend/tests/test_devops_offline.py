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

from app.devops import cost, health, manifest, naming, provisioning, secrets_store, sizing
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


def test_frontend_wiring():
    """DevOps deploy gap #2 (proven against the run-1105 defects specifically): the
    generated frontend could not reach the backend because (a) the deploy set
    NEXT_PUBLIC_API_URL but the frontend read NEXT_PUBLIC_API_BASE_URL, (b) the value
    was a remote domain, (c) it was a runtime env not a BUILD ARG (Next inlines
    NEXT_PUBLIC_* at build), and (d) Caddy sent /api/* to the backend WITHOUT stripping
    /api. Each is asserted resolved against the REAL generated artifacts."""
    from app.developers import agents

    root = tempfile.mkdtemp(prefix="devops-fe-")
    names = naming.names(1105, "Bella Vista")
    files = _synthetic_backend() + [
        {"id": 9, "ticket_id": "FE-1", "filename": "page.tsx",
         "filepath": "frontend/app/menu/page.tsx",
         "content": "export default function P(){return <div/>;}\n",
         "agent_type": "frontend"}]
    m = manifest.build(files, root, names, subdomain=names["subdomain"], local=True)

    compose = open(m.compose_path).read()
    fe_dockerfile = open(os.path.join(m.frontend_context, "Dockerfile")).read()
    caddy = open(os.path.join(m.caddy_context, "Caddyfile")).read()
    ENV = manifest.FRONTEND_API_BASE_ENV
    VAL = manifest.FRONTEND_API_BASE_VALUE

    # (a) NAME: the deploy now sets the var the frontend reads — and NOT the wrong one.
    check("deploy sets NEXT_PUBLIC_API_BASE_URL (the var the 1105 frontend read)",
          ENV == "NEXT_PUBLIC_API_BASE_URL" and ENV in compose, ENV)
    check("the wrong NEXT_PUBLIC_API_URL is gone from the compose",
          "NEXT_PUBLIC_API_URL:" not in compose and "NEXT_PUBLIC_API_URL " not in compose)

    # (b) VALUE: a relative /api (same-origin), NOT the remote .apps.rajkumarai.dev host.
    check("the API base is the relative /api, not an absolute/remote URL",
          VAL == "/api" and f'{ENV}: "/api"' in compose)
    check("the API base does NOT point at the remote apps subdomain",
          names["subdomain"] not in _fe_env_region(compose))

    # (c) BUILD ARG: present in the Dockerfile BEFORE `npm run build`, and in build.args.
    dockerfile_arg_before_build = (f"ARG {ENV}" in fe_dockerfile
                                   and fe_dockerfile.index(f"ARG {ENV}")
                                   < fe_dockerfile.index("npm run build"))
    check("frontend Dockerfile declares the API base as an ARG before `npm run build`",
          dockerfile_arg_before_build, fe_dockerfile)
    fe_build_block = _fe_env_region(compose).split("container_name:")[0]  # the `build:` section
    check("compose passes the API base as a build ARG (not runtime-only)",
          "args:" in fe_build_block and f'{ENV}: "/api"' in fe_build_block)

    # (d) CADDY: /api/* is prefix-STRIPPED to the backend; health/openapi still routed.
    check("Caddy strips the /api prefix (handle_path /api/*) so /api/menu -> backend /menu",
          "handle_path /api/* {" in caddy)
    check("Caddy still routes /openapi.json + /health to the backend (fix #20 probe)",
          "/openapi.json" in caddy and "/health" in caddy and "backend:8000" in caddy)
    check("a bare frontend path (/menu, /admin/menu) is NOT sent to the backend",
          "handle_path /menu" not in caddy and "reverse_proxy frontend:3000" in caddy)

    # AWS branch strips /api too (the prefix fix is not local-only).
    root2 = tempfile.mkdtemp(prefix="devops-fe-")
    m2 = manifest.build(files, root2, names, subdomain=names["subdomain"], local=False,
                        le_email="x@y.com", use_images=True,
                        image_refs={"backend": "r/b", "frontend": "r/f", "caddy": "r/c"})
    aws_caddy = open(os.path.join(m2.caddy_context, "Caddyfile")).read()
    check("AWS Caddy also strips the /api prefix", "handle_path /api/* {" in aws_caddy)

    # Part 3 — the codegen contract-pin: the frontend prompt mandates the SAME var, so a
    # fresh generation reads exactly what the deploy sets (not a guessed name).
    fe_prompt = agents._system("frontend")
    check("frontend developer prompt pins process.env.NEXT_PUBLIC_API_BASE_URL",
          "process.env.NEXT_PUBLIC_API_BASE_URL" in fe_prompt)
    check("the pinned var name MATCHES the manifest constant (no drift)",
          manifest.FRONTEND_API_BASE_ENV in fe_prompt)
    check("frontend prompt forbids the wrong/invented var names",
          "NEXT_PUBLIC_API_URL" in fe_prompt and "do NOT" in fe_prompt.replace("Do NOT", "do NOT"))
    check("the API-base rule is FRONTEND-only (backend prompt does not carry it)",
          manifest.FRONTEND_API_BASE_ENV not in agents._system("backend"))


def _fe_env_region(compose: str) -> str:
    """Just the frontend service block, so the remote-subdomain check can't be fooled by
    an unrelated mention elsewhere in the compose."""
    if "  frontend:" not in compose:
        return ""
    start = compose.index("  frontend:")
    end = compose.index("  caddy:", start) if "  caddy:" in compose[start:] else len(compose)
    return compose[start:end]


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


def test_auth0_frontend_wiring():
    """Owner onboarding — the frontend Auth0 consumption contract: the per-project
    NEXT_PUBLIC_AUTH0_* values (from provisioning) must reach the frontend as BUILD ARGs
    (Next inlines NEXT_PUBLIC_* at build), the codegen prompt must read those EXACT
    names, and an app WITHOUT Auth0 must inline none."""
    from app.developers import agents

    # Mapping: backend provisioned values -> frontend NEXT_PUBLIC_* (source-present only).
    be = {"AUTH0_DOMAIN": "t.us.auth0.com", "AUTH0_CLIENT_ID": "cid_1",
          "API_AUDIENCE": "https://app/api", "FERNET_KEY": "secret"}
    fp = manifest.frontend_public_env(be)
    check("frontend_public_env maps domain/client_id/audience to NEXT_PUBLIC_*",
          fp == {"NEXT_PUBLIC_AUTH0_DOMAIN": "t.us.auth0.com",
                 "NEXT_PUBLIC_AUTH0_CLIENT_ID": "cid_1",
                 "NEXT_PUBLIC_AUTH0_AUDIENCE": "https://app/api"}, str(fp))
    check("frontend_public_env never leaks a non-Auth0 secret (no FERNET_KEY)",
          "FERNET_KEY" not in fp and "secret" not in str(fp))
    check("an app without provisioned Auth0 gets an empty frontend_public_env",
          manifest.frontend_public_env({"FERNET_KEY": "x"}) == {})

    root = tempfile.mkdtemp(prefix="devops-a0-")
    names = naming.names(4242, "Loginful")
    files = _synthetic_backend() + [
        {"id": 9, "ticket_id": "FE-1", "filename": "page.tsx",
         "filepath": "frontend/app/page.tsx",
         "content": "export default function P(){return <div/>;}\n",
         "agent_type": "frontend"}]
    m = manifest.build(files, root, names, subdomain=names["subdomain"], local=True,
                       frontend_public=fp)
    compose = open(m.compose_path).read()
    fe_dockerfile = open(os.path.join(m.frontend_context, "Dockerfile")).read()
    check("frontend Dockerfile declares each Auth0 var as a build ARG",
          all(f"ARG {e}=" in fe_dockerfile for e in manifest.FRONTEND_AUTH0_ENVS))
    check("compose passes the Auth0 values as build ARGs (Next inlines at build)",
          'NEXT_PUBLIC_AUTH0_DOMAIN: "t.us.auth0.com"' in compose
          and 'NEXT_PUBLIC_AUTH0_AUDIENCE: "https://app/api"' in compose)

    # An app WITHOUT Auth0 provisioning inlines nothing (no empty placeholders leaking).
    root2 = tempfile.mkdtemp(prefix="devops-noa0-")
    m2 = manifest.build(files, root2, naming.names(7, "Plain"),
                        subdomain="x", local=True, frontend_public={})
    check("an app without Auth0 has no NEXT_PUBLIC_AUTH0 in its compose",
          "NEXT_PUBLIC_AUTH0" not in open(m2.compose_path).read())

    # Drift guard: the frontend codegen prompt reads EXACTLY the manifest's names.
    fe_prompt = agents._system("frontend")
    check("the frontend codegen prompt names every manifest Auth0 var (no drift)",
          all(e in fe_prompt for e in manifest.FRONTEND_AUTH0_ENVS))
    # Contract 1 drift guard: the backend prompt reads the connected-account var.
    check("the backend codegen prompt reads STRIPE_CONNECTED_ACCOUNT_ID (contract 1)",
          "STRIPE_CONNECTED_ACCOUNT_ID" in agents._system("backend"))


def test_provisioning():
    print("\nD2. Platform provisioning (deploy gap #1, the 3 platform-solvable fixes)")

    # Inline fixtures: a backend file reading a mix of crypto/config/infra/owner vars,
    # a frontend file (must be ignored), and a backend file with no env at all.
    be = {"filepath": "backend/app/security.py", "content": (
        "import os\n"
        "FERNET_KEY = os.getenv('FERNET_KEY')\n"
        "SESSION_SECRET_KEY = os.getenv(\"SESSION_SECRET_KEY\")\n"
        "REDIS_URL = os.getenv('REDIS_URL')\n"
        "ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')\n"
        "ALLOWED = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000')\n"
        "STRIPE = os.environ['STRIPE_SECRET_KEY']\n")}
    fe = {"filepath": "frontend/app/page.tsx",
          "content": "const x = process.env.NEXT_PUBLIC_API_BASE_URL\n"}
    plain = {"filepath": "backend/app/models.py", "content": "class M:\n    pass\n"}
    files = [be, fe, plain]

    # --- required_env: extracts backend env names, ignores frontend/plain ---
    ne = provisioning.required_env(files)
    check("required_env finds getenv + environ[...] names",
          {"FERNET_KEY", "SESSION_SECRET_KEY", "REDIS_URL", "ENVIRONMENT",
           "ALLOWED_ORIGINS", "STRIPE_SECRET_KEY"} <= ne, str(sorted(ne)))
    check("required_env ignores frontend NEXT_PUBLIC_* (not a backend os.getenv)",
          "NEXT_PUBLIC_API_BASE_URL" not in ne)
    check("required_env on a file with no env is empty",
          provisioning.required_env([plain]) == set())

    # --- needs_redis: gate is exactly 'reads REDIS_URL' ---
    check("needs_redis True when the app reads REDIS_URL", provisioning.needs_redis(files))
    check("needs_redis False when it does not", not provisioning.needs_redis([plain]))

    # --- Fix C config defaults: referenced-only, ALLOWED_ORIGINS excluded, owner wins ---
    cfg = provisioning.config_defaults(ne, {})
    check("config_defaults sets ENVIRONMENT/SQL_ECHO-style vars that are referenced",
          cfg.get("ENVIRONMENT") == "production", str(cfg))
    check("config_defaults does NOT include ALLOWED_ORIGINS (driver sets it)",
          "ALLOWED_ORIGINS" not in cfg)
    check("config_defaults does NOT set a var the app never reads (no RATE_LIMIT here)",
          "RATE_LIMIT_TIMES" not in cfg)
    check("an owner-set value is never overridden by a default",
          provisioning.config_defaults(ne, {"ENVIRONMENT": "staging"}).get("ENVIRONMENT")
          is None)

    # --- Fix A crypto: mint valid keys, only what's needed, never an owner secret ---
    async def _mint():
        recorded: dict[str, str] = {}

        async def _fake_set(pid, key, value):
            recorded[key] = value
        orig = secrets_store.set_secret
        secrets_store.set_secret = _fake_set
        try:
            first = await provisioning.ensure_crypto_keys(4242, ne, {})
            # Second pass with the minted keys now 'existing' -> nothing re-minted.
            second = await provisioning.ensure_crypto_keys(4242, ne, dict(first))
            return first, second, recorded
        finally:
            secrets_store.set_secret = orig

    first, second, recorded = asyncio.run(_mint())
    check("mints exactly the crypto keys the app needs (FERNET + SESSION here)",
          set(first) == {"FERNET_KEY", "SESSION_SECRET_KEY"}, str(sorted(first)))
    check("NEVER mints an owner secret (no STRIPE_SECRET_KEY)",
          "STRIPE_SECRET_KEY" not in first and "STRIPE_SECRET_KEY" not in recorded)
    check("Fernet-type keys are VALID Fernet keys (Fernet(key) works)",
          Fernet(first["FERNET_KEY"]) is not None)
    check("SESSION_SECRET_KEY is a non-trivial random string",
          isinstance(first["SESSION_SECRET_KEY"], str) and len(first["SESSION_SECRET_KEY"]) >= 32)
    check("every minted key is PERSISTED via set_secret (redeploy reuse)",
          set(recorded) == {"FERNET_KEY", "SESSION_SECRET_KEY"}, str(sorted(recorded)))
    check("a redeploy re-mints NOTHING when the keys already exist (stable)",
          second == {}, str(second))

    # --- Fix B compose: redis service present only when needed, no host port ---
    names = {"project_id": 1, "compose_project": "p1", "db_container": "db",
             "db_user": "u", "db_password": "pw", "db_name": "d",
             "backend_container": "be", "frontend_container": "fe",
             "caddy_container": "cad", "network": "net", "db_volume": "vol"}
    c_yes = manifest._compose(names, True, 8443, 8080, "x", use_images=False, needs_redis=True)
    c_no = manifest._compose(names, True, 8443, 8080, "x", use_images=False, needs_redis=False)
    check("needs_redis adds a redis:7 service",
          "  redis:\n    image: redis:7-alpine" in c_yes, "no redis service")
    check("needs_redis wires REDIS_URL into the backend (internal DNS)",
          'REDIS_URL: "redis://redis:6379"' in c_yes)
    check("backend waits for redis to be healthy",
          "redis:\n        condition: service_healthy" in c_yes)
    check("redis publishes NO host port (isolation preserved)",
          "6379:" not in c_yes)
    check("an app that needs no redis gets NO redis service and NO REDIS_URL wiring",
          "image: redis:7-alpine" not in c_no and 'REDIS_URL: "' not in c_no)

    # --- Platform-held provider credentials (owner-onboarding, deploy gap #1) ---
    # Referenced env set: Stripe (client_id + secret + redirect) + SMTP (host/port/pw) +
    # sender + a var the platform hasn't configured.
    p_needed = {"STRIPE_CLIENT_ID", "STRIPE_SECRET_KEY", "STRIPE_REDIRECT_URI",
                "SMTP_HOST", "SMTP_PORT", "SMTP_PASSWORD", "SENDER_EMAIL",
                "TWILIO_ACCOUNT_SID"}
    saved = {k: getattr(settings, k) for k in
             ("stripe_client_id", "stripe_secret_key", "stripe_redirect_uri",
              "smtp_host", "smtp_port", "smtp_password", "sender_email",
              "twilio_account_sid")}
    try:
        settings.stripe_client_id = "ca_platform_123"
        settings.stripe_secret_key = "sk_live_PLATFORM_SECRET"
        settings.stripe_redirect_uri = "https://platform/connect/stripe/callback"
        settings.smtp_host = "smtp.platform.test"
        settings.smtp_port = "587"
        settings.smtp_password = "SMTP_SECRET_PW"
        settings.sender_email = "no-reply@platform.test"
        settings.twilio_account_sid = None            # deliberately unconfigured
        sec, nonsec = provisioning.platform_provided(p_needed, {})
        check("secrets go in the SECRET bucket (Stripe secret, SMTP password)",
              set(sec) == {"STRIPE_SECRET_KEY", "SMTP_PASSWORD"}, str(sorted(sec)))
        check("identifiers go in the NON-secret bucket (client id, redirect, host/port, sender)",
              set(nonsec) == {"STRIPE_CLIENT_ID", "STRIPE_REDIRECT_URI", "SMTP_HOST",
                              "SMTP_PORT", "SENDER_EMAIL"}, str(sorted(nonsec)))
        check("SMTP_PORT is NON-secret (never redacted as if it were a secret)",
              nonsec.get("SMTP_PORT") == "587")
        check("an UNCONFIGURED platform var (TWILIO_ACCOUNT_SID) is omitted -> app fail-fasts",
              "TWILIO_ACCOUNT_SID" not in sec and "TWILIO_ACCOUNT_SID" not in nonsec)
        # An owner who supplied their own value keeps it (platform never overrides).
        sec2, nonsec2 = provisioning.platform_provided(
            p_needed, {"STRIPE_SECRET_KEY": "owner_key"})
        check("owner-supplied value is not overridden by the platform",
              "STRIPE_SECRET_KEY" not in sec2)
        # A var the app never reads is never injected, even if the platform set it.
        sec3, nonsec3 = provisioning.platform_provided({"STRIPE_CLIENT_ID"}, {})
        check("only injects vars the app actually reads",
              set(sec3) == set() and set(nonsec3) == {"STRIPE_CLIENT_ID"})
    finally:
        for k, v in saved.items():
            setattr(settings, k, v)


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


def test_health_probe():
    """The LAYERED health probe (fix #3, gap #3): a deploy is healthy ONLY when the
    BACKEND actually answers. The headline check is the run-1105 defect — a crash-looping
    backend (502 on backend routes) behind a LIVE frontend edge (404 homepage) must be
    reported UNHEALTHY, not a false 'live'. Deterministic: httpx.MockTransport, no network."""
    import httpx

    def _probe(status_map, has_frontend=True):
        """Run health.probe against a mock where each path returns status_map[path]
        (an int status, or an Exception instance to simulate a connection error; a
        path missing from the map raises ConnectError = unreachable)."""
        def handler(request):
            st = status_map.get(request.url.path, httpx.ConnectError("refused"))
            if isinstance(st, Exception):
                raise st
            return httpx.Response(st, text="x")
        orig = health.httpx.AsyncClient      # the REAL class (health.httpx IS the httpx module)

        def factory(*_a, **_k):              # build a real client with a mock transport
            return orig(transport=httpx.MockTransport(handler))
        health.httpx.AsyncClient = factory
        try:
            return asyncio.run(health.probe("https://x", False, 0, 0,
                                            has_frontend=has_frontend))
        finally:
            health.httpx.AsyncClient = orig

    print("\nF2. Layered health probe — backend liveness is required")

    # ⭐ THE run-1105 REGRESSION: backend routes 502 (crash-loop) but the frontend edge
    # serves a 404 homepage. Old probe returned healthy on the '/' 404; it must now FAIL.
    dead_be = _probe({"/openapi.json": 502, "/health": 502, "/healthz": 502, "/": 404})
    check("a crash-looping backend behind a LIVE frontend edge is UNHEALTHY (the 1105 bug)",
          dead_be.healthy is False, str(dead_be))
    check("...and the failure is attributed to the BACKEND layer",
          dead_be.failed_layer == "backend", str(dead_be.failed_layer))

    # A genuinely-up stack: backend answers, frontend serves (404 homepage is fine).
    up = _probe({"/openapi.json": 200, "/": 404})
    check("backend 200 + frontend edge answering (404 homepage) is HEALTHY",
          up.healthy is True and up.failed_layer is None, str(up))

    # gap #4 must NOT false-fail: a 404 homepage is the frontend answering, not a failure.
    check("a 404 homepage alone never marks the stack unhealthy",
          _probe({"/openapi.json": 200, "/": 404}).healthy is True)

    # Backend answers via /health even if /openapi.json is 502-ish? (all backend paths tried)
    be_via_health = _probe({"/openapi.json": 404, "/health": 200, "/": 404})
    check("backend answering on ANY liveness path (200/404) counts as up",
          be_via_health.healthy is True, str(be_via_health))

    # Frontend container dead (502) while backend is fine -> unhealthy, FRONTEND layer.
    dead_fe = _probe({"/openapi.json": 200, "/": 502})
    check("a dead frontend behind a healthy backend is UNHEALTHY (frontend layer)",
          dead_fe.healthy is False and dead_fe.failed_layer == "frontend", str(dead_fe))

    # Edge/Caddy unreachable (every request errors) -> EDGE layer.
    dead_edge = _probe({})   # nothing mapped -> ConnectError on every path
    check("an unreachable edge (Caddy down) is UNHEALTHY (edge layer)",
          dead_edge.healthy is False and dead_edge.failed_layer == "edge", str(dead_edge))

    # Backend-only stack (no frontend): backend liveness alone decides.
    be_only_up = _probe({"/openapi.json": 200}, has_frontend=False)
    check("a backend-only stack is healthy on backend liveness alone",
          be_only_up.healthy is True, str(be_only_up))
    be_only_down = _probe({"/openapi.json": 502}, has_frontend=False)
    check("a backend-only stack with a 502 backend is UNHEALTHY (backend layer)",
          be_only_down.healthy is False and be_only_down.failed_layer == "backend", str(be_only_down))


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
    test_frontend_wiring()
    test_auth0_frontend_wiring()
    test_secrets()
    test_provisioning()
    test_cost()
    test_health()
    test_health_probe()
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
