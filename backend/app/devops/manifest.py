"""STEP 2 — assemble the generated files into a real, buildable project.

The Developer agents store a first draft in `generated_files`; nothing there is
runnable on its own. This module turns that draft into two build contexts (a
FastAPI backend image and a Next.js frontend image) plus a Caddy reverse-proxy
image, and a docker-compose that wires them to a per-project Postgres.

Key decisions, and why:

* **`requirements.txt` is generated here, not by the pipeline.** CONTEXT flagged
  this for Week 7: QA could import-scan and pip-install on the fly, but a deployed
  container cannot scan itself. We reuse QA's AST import scanner
  (`assembly._third_party_imports`) — the same one whose regex predecessor
  fabricated "hallucinated dependency" findings — so the manifest is derived from
  what the code actually imports, not guessed.

* **All config is baked into images; only named volumes hold data.** DevOps runs
  the build on the HOST daemon via a mounted socket (docker-out-of-docker), where
  a host *bind*-mount would resolve against the host filesystem, not the backend
  container's. Baking the Caddyfile/app into images and using named volumes for
  the database sidesteps that entirely and keeps the local and AWS paths identical.

* **The two import styles are reconciled by aliasing, not a dual PYTHONPATH** —
  reusing QA's `sitecustomize` shim (defect #4), so a mixed-style generated app
  imports each module exactly once.
"""
import os
from dataclasses import dataclass, field

from app.qa import assembly as qa

BACKEND_PORT = 8000
FRONTEND_PORT = 3000

# FE↔BE wiring (deploy gap #2). The generated frontend reaches the backend through
# EXACTLY this env var (pinned as a contract on the codegen side too —
# developers/agents._system('frontend')), set to a RELATIVE `/api` prefix so a
# browser fetch is same-origin and works on BOTH the local (localhost:<port>) and the
# AWS (real subdomain) origins. Caddy strips the `/api` prefix and forwards to the
# backend (see `_caddyfile`). It MUST be a Docker BUILD ARG, not just a runtime env:
# Next.js inlines `NEXT_PUBLIC_*` into the client bundle at build time, so a runtime-only
# value never reaches the browser (the run-1105 bug). Keep this string in sync with the
# frontend developer prompt; `test_devops_offline` asserts they agree.
FRONTEND_API_BASE_ENV = "NEXT_PUBLIC_API_BASE_URL"
FRONTEND_API_BASE_VALUE = "/api"

# Always needed to run a generated FastAPI + async SQLAlchemy app, whether or not
# the code imports them by a name the scanner sees.
_BACKEND_BASE_REQS = [
    "fastapi", "uvicorn[standard]", "sqlalchemy[asyncio]", "asyncpg",
    "pydantic", "pydantic-settings", "python-dotenv",
]


@dataclass
class Manifest:
    root: str
    backend_context: str
    caddy_context: str
    app_module: str | None
    requirements: str
    has_frontend: bool
    frontend_context: str | None = None
    compose_path: str | None = None
    failures: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ file split
def _is_frontend(f: dict) -> bool:
    path = (f.get("filepath") or f.get("filename") or "").lower()
    if path.startswith("frontend/"):
        return True
    if path.startswith("backend/"):
        return False
    # Fall back to extension / agent for files with an ambiguous path.
    if path.endswith((".tsx", ".ts", ".jsx", ".js", ".css", ".json")):
        return "backend" not in (f.get("agent_type") or "")
    return False


def _rel_for_backend(f: dict) -> str | None:
    """Path under the backend context's /srv, preserving the dotted module layout
    (so `backend/app/main.py` -> module `backend.app.main`)."""
    return qa._safe_relpath(f.get("filepath", ""), f.get("filename", ""))


def _rel_for_frontend(f: dict) -> str | None:
    """Path under the frontend context root, with the leading `frontend/` dropped
    so `package.json`/`app/` sit at the image root Next.js expects."""
    rel = qa._safe_relpath(f.get("filepath", ""), f.get("filename", ""))
    if rel is None:
        return None
    if rel.startswith("frontend/"):
        rel = rel[len("frontend/"):]
    return rel or None


# ------------------------------------------------------------------ manifest gen
def _backend_requirements(backend_files: list[dict]) -> str:
    wanted: set[str] = set()
    for f in backend_files:
        rel = f.get("filepath") or f.get("filename") or ""
        if not rel.endswith(".py"):
            continue
        for root in qa._third_party_imports(f.get("content") or ""):
            wanted.add(qa._PACKAGE_ALIASES.get(root, root))
    # Base set first (deduped), then the scanned extras that aren't already base.
    base_roots = {r.split("[")[0].lower() for r in _BACKEND_BASE_REQS}
    extras = sorted(p for p in wanted if p.lower() not in base_roots)
    reqs = list(_BACKEND_BASE_REQS) + extras
    # Pydantic EmailStr needs the email-validator extra, which no import names —
    # so the scan above misses it and the deployed app won't boot. Add it on use.
    if qa.needs_email_validator(f.get("content") or "" for f in backend_files) \
            and "email-validator" not in extras:
        reqs.append("email-validator")
    # File/Form routes (e.g. the menu PDF upload) need python-multipart, also named
    # by no import — so the deployed app crashes at startup without it.
    if qa.needs_python_multipart(f.get("content") or "" for f in backend_files) \
            and "python-multipart" not in extras:
        reqs.append("python-multipart")
    # GATE INTEGRITY (project 829): pin every requirement to the platform's tested
    # requirements.txt — the SAME source the QA/smoke_boot venv constrains to — so
    # the deployed image and the gate install IDENTICAL versions and can never boot
    # under a different Pydantic. Extras the platform doesn't pin stay unpinned.
    pinned = [qa.pin_spec(r) for r in reqs]
    lines = ["# Generated by DevOps from the app's actual imports (AST scan),",
             "# version-pinned to the platform's tested requirements.txt."] + pinned
    return "\n".join(lines) + "\n"


def _bootstrap_py(app_module: str) -> str:
    """Container entrypoint: create the generated schema (STEP 4), then exec
    uvicorn. Reuses QA's dual-style import discovery to find the app's Base."""
    pkg = app_module.rsplit(".", 1)[0] if "." in app_module else ""
    cands = [c for c in (pkg, "app", "backend.app") if c]
    return f'''"""DevOps bootstrap: create the generated app's schema, then serve it."""
import asyncio, importlib, os, sys

APP_MODULE = {app_module!r}
CANDS = {cands!r}


def _create_schema():
    db = None
    for c in CANDS:
        try:
            db = importlib.import_module(c + ".database")
            importlib.import_module(c + ".models")
            break
        except Exception:
            db = None
    if db is None:
        print("[devops-bootstrap] no models module found; app will manage its own schema")
        return
    eng = getattr(db, "engine", None)
    base = getattr(db, "Base", None)
    if eng is None or base is None:
        print("[devops-bootstrap] no engine/Base; skipping schema create")
        return
    try:
        async def _go():
            async with eng.begin() as conn:
                await conn.run_sync(base.metadata.create_all)
        asyncio.run(_go())
        print("[devops-bootstrap] schema created (async)")
    except Exception as e_async:
        try:
            base.metadata.create_all(bind=eng)
            print("[devops-bootstrap] schema created (sync)")
        except Exception as e_sync:
            print("[devops-bootstrap] schema create skipped:", e_async, e_sync)


_create_schema()
os.execvp("uvicorn", ["uvicorn", APP_MODULE + ":app",
                      "--host", "0.0.0.0", "--port", "{BACKEND_PORT}"])
'''


def _backend_dockerfile() -> str:
    return f'''FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/srv
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY srv/ /srv/
EXPOSE {BACKEND_PORT}
# Secrets are injected at RUN time via --env-file, never baked into these layers.
CMD ["python", "/srv/_devops_bootstrap.py"]
'''


def _frontend_dockerfile() -> str:
    # Build at image-build time so a broken generated UI fails the deploy honestly
    # (rather than crash-looping at runtime).
    # The API base (gap #2) MUST be present as a build ARG here — Next.js inlines
    # `NEXT_PUBLIC_*` into the client bundle during `npm run build`, so a runtime-only
    # env would never reach the browser (the run-1105 bug). The caller passes it via
    # `--build-arg`/compose `build.args`; the ENV makes it visible to `npm run build`.
    return f'''FROM node:20-slim
WORKDIR /app
ARG {FRONTEND_API_BASE_ENV}={FRONTEND_API_BASE_VALUE}
ENV {FRONTEND_API_BASE_ENV}=${FRONTEND_API_BASE_ENV}
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build
EXPOSE {FRONTEND_PORT}
CMD ["npm", "run", "start"]
'''


def _caddy_routes() -> str:
    """The shared reverse-proxy routes (deploy gap #2). Order matters in Caddy:

      * `handle_path /api/*` STRIPS the `/api` prefix, so a same-origin frontend call
        `${NEXT_PUBLIC_API_BASE_URL}/menu` = `/api/menu` reaches the backend as `/menu`.
        This also removes the `/admin/menu` collision (that path is the FRONTEND page;
        the backend endpoint is reached at `/api/admin/menu`).
      * `/openapi.json /docs /health /healthz` go to the backend WITHOUT stripping — the
        app serves them at those exact paths, and the layered health probe (fix #20)
        depends on them.
      * everything else -> the frontend (or the backend if there is no frontend)."""
    web = "backend:8000"  # overridden by caller via .format
    return '''	handle_path /api/* {{
		reverse_proxy backend:8000
	}}
	@backend_direct path /openapi.json /docs /health /healthz
	handle @backend_direct {{
		reverse_proxy backend:8000
	}}
	handle {{
		reverse_proxy {web}
	}}'''


def _caddyfile(subdomain: str, has_frontend: bool, local: bool,
               le_email: str) -> str:
    """Reverse proxy. `/api/*` (prefix stripped) + the app's own health/openapi go to
    the backend; everything else to the frontend (or the backend if there is no
    frontend). See `_caddy_routes`."""
    web = "backend:8000" if not has_frontend else "frontend:3000"
    routes = _caddy_routes().format(web=web)
    if local:
        # Local: an internally-trusted cert. The site MUST name the hosts it will
        # be reached by, or `tls internal` has no hostname to mint a cert for and
        # the TLS handshake fails with an internal-error alert. `localhost` is for
        # the user's browser; `host.docker.internal` is how the in-container health
        # probe reaches the host-published port on Docker Desktop.
        # ssl_type is recorded as 'self_signed_local', never lets_encrypt.
        return f'''{{
	auto_https disable_redirects
}}
localhost, host.docker.internal {{
	tls internal
{routes}
}}
'''
    # AWS: real Let's Encrypt for the real subdomain.
    return f'''{{
	email {le_email}
}}
{subdomain} {{
{routes}
}}
'''


def _caddy_dockerfile() -> str:
    return '''FROM caddy:2
COPY Caddyfile /etc/caddy/Caddyfile
'''


def _compose(names: dict, has_frontend: bool, https_host_port: int,
             http_host_port: int, subdomain: str, *, use_images: bool,
             image_refs: dict | None = None, needs_redis: bool = False) -> str:
    """docker-compose for one isolated app. `use_images=False` builds locally;
    `use_images=True` references pushed images (the AWS/EC2 path). `needs_redis`
    adds an isolated redis service + wires REDIS_URL into the backend (Fix B)."""
    image_refs = image_refs or {}
    db_url = (f"postgresql+asyncpg://{names['db_user']}:{names['db_password']}"
              f"@db:5432/{names['db_name']}")

    def _svc_source(kind: str, context: str) -> str:
        if use_images:
            return f"    image: {image_refs.get(kind)}"
        return f"    build: ./{context}"

    frontend_block = ""
    if has_frontend:
        # gap #2: build the frontend WITH the API base as a build ARG (Next inlines
        # NEXT_PUBLIC_* at build time), not just a runtime env. For the pushed-image
        # (AWS) path the arg is passed by the buildx build; here (local compose build)
        # it rides in `build.args`. The runtime `environment:` mirrors it (harmless,
        # and covers any server-side read).
        if use_images:
            fe_source = f"    image: {image_refs.get('frontend')}"
        else:
            fe_source = (f"    build:\n"
                         f"      context: ./frontend\n"
                         f"      args:\n"
                         f"        {FRONTEND_API_BASE_ENV}: \"{FRONTEND_API_BASE_VALUE}\"")
        frontend_block = f'''  frontend:
{fe_source}
    container_name: {names['frontend_container']}
    environment:
      {FRONTEND_API_BASE_ENV}: "{FRONTEND_API_BASE_VALUE}"
    depends_on:
      - backend
    networks: [appnet]
    restart: unless-stopped
'''

    # Fix B: optional isolated Redis service + backend wiring. Only present when the
    # generated backend reads REDIS_URL (e.g. FastAPI-Limiter). `redis:6379` is the
    # app's OWN network DNS — no port is published to the host (isolation preserved).
    from app.devops.provisioning import REDIS_INTERNAL_URL
    if needs_redis:
        _redis_backend_env = f'      REDIS_URL: "{REDIS_INTERNAL_URL}"\n'
        _redis_backend_depends = "      redis:\n        condition: service_healthy\n"
        _redis_service = f'''  redis:
    image: redis:7-alpine
    container_name: {names['backend_container']}-redis
    networks: [appnet]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

'''
    else:
        _redis_backend_env = _redis_backend_depends = _redis_service = ""

    return f'''# DevOps-generated deployment for project {names['project_id']} — ISOLATED:
# its own network, its own database + credentials, its own containers. No name
# here is shared with any other project (all derived from project_id).
name: {names['compose_project']}

services:
  db:
    image: postgres:16-alpine
    container_name: {names['db_container']}
    environment:
      POSTGRES_DB: {names['db_name']}
      POSTGRES_USER: {names['db_user']}
      POSTGRES_PASSWORD: {names['db_password']}
    volumes:
      - dbdata:/var/lib/postgresql/data
    networks: [appnet]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U {names['db_user']} -d {names['db_name']}"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  backend:
{_svc_source('backend', 'backend')}
    container_name: {names['backend_container']}
    # DATABASE_URL (and REDIS_URL, when present) are safe to inline — per-project,
    # internal compose DNS. Real SECRETS come from the 0600 --env-file the driver
    # passes, never from this file.
    environment:
      DATABASE_URL: "{db_url}"
{_redis_backend_env}    env_file:
      - deploy.env
    depends_on:
      db:
        condition: service_healthy
{_redis_backend_depends}    networks: [appnet]
    restart: unless-stopped
{_redis_service}

{frontend_block}  caddy:
{_svc_source('caddy', 'caddy')}
    container_name: {names['caddy_container']}
    ports:
      - "{http_host_port}:80"
      - "{https_host_port}:443"
    depends_on:
      - backend
    networks: [appnet]
    restart: unless-stopped

networks:
  appnet:
    name: {names['network']}

volumes:
  dbdata:
    name: {names['db_volume']}
'''


# ------------------------------------------------------------------ entrypoint
def build(files: list[dict], root: str, names: dict, *, subdomain: str,
          has_frontend_override: bool | None = None, local: bool = True,
          le_email: str = "", https_host_port: int = 443,
          http_host_port: int = 80, use_images: bool = False,
          image_refs: dict | None = None) -> Manifest:
    """Write every build context + the compose file under `root`. Never raises —
    problems are returned as `Manifest.failures` (the QA-agent convention)."""
    failures: list[str] = []
    backend_files = [f for f in files if not _is_frontend(f)]
    frontend_files = [f for f in files if _is_frontend(f)]
    has_frontend = (has_frontend_override
                    if has_frontend_override is not None
                    else bool(frontend_files))

    # ---- backend context: /srv/<module layout> + requirements + bootstrap ----
    backend_ctx = os.path.join(root, "backend")
    srv = os.path.join(backend_ctx, "srv")
    os.makedirs(srv, exist_ok=True)
    written: dict[str, str] = {}
    for f in backend_files:
        rel = _rel_for_backend(f)
        if rel is None:
            failures.append(f"unsafe backend path: {f.get('filepath')!r}")
            continue
        dest = os.path.join(srv, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(f.get("content") or "")
        written[rel] = f.get("content") or ""

    # __init__.py for every python package dir (import cleanliness).
    for rel in list(written):
        if rel.endswith(".py"):
            parts = rel.split("/")[:-1]
            for i in range(len(parts)):
                pkg = os.path.join(srv, *parts[: i + 1], "__init__.py")
                if not os.path.exists(pkg):
                    os.makedirs(os.path.dirname(pkg), exist_ok=True)
                    open(pkg, "w").close()

    app_module = qa._find_app_module(written)
    if app_module is None:
        failures.append(
            "no FastAPI entrypoint found in the generated backend (no file "
            "creates a FastAPI app) — cannot build a runnable backend image."
        )
        # Still write what we can so the failure is inspectable.
        app_module = "backend.app.main"

    # Reuse QA's alias shim so `app.*` and `backend.app.*` are one module object.
    qa._write_alias_hook(srv, app_module)

    with open(os.path.join(srv, "_devops_bootstrap.py"), "w", encoding="utf-8") as fh:
        fh.write(_bootstrap_py(app_module))
    requirements = _backend_requirements(backend_files)
    with open(os.path.join(backend_ctx, "requirements.txt"), "w", encoding="utf-8") as fh:
        fh.write(requirements)
    with open(os.path.join(backend_ctx, "Dockerfile"), "w", encoding="utf-8") as fh:
        fh.write(_backend_dockerfile())

    # ---- frontend context ----
    frontend_ctx = None
    if has_frontend:
        frontend_ctx = os.path.join(root, "frontend")
        os.makedirs(frontend_ctx, exist_ok=True)
        saw_pkg = False
        for f in frontend_files:
            rel = _rel_for_frontend(f)
            if rel is None:
                failures.append(f"unsafe frontend path: {f.get('filepath')!r}")
                continue
            if rel == "package.json":
                saw_pkg = True
            dest = os.path.join(frontend_ctx, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # D4 (project 860): force the app dynamic via the root server layout so
            # `next build` cannot die prerendering a client page that uses
            # useSearchParams()/request-time state, which failed the whole frontend
            # image build. Page-level force-dynamic does NOT work on Next 15 (route
            # config is ignored in client components); the root layout is the proven
            # fix. Same deterministic transform QA uses.
            content = qa.force_dynamic_layout(rel, f.get("content") or "")
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(content)
        with open(os.path.join(frontend_ctx, "Dockerfile"), "w", encoding="utf-8") as fh:
            fh.write(_frontend_dockerfile())
        if not saw_pkg:
            failures.append(
                "frontend has no package.json — cannot build a Next.js image. "
                "(Same gap QA's Step 5 hit; the Architect commissions FND-3.)"
            )

    # ---- caddy context ----
    caddy_ctx = os.path.join(root, "caddy")
    os.makedirs(caddy_ctx, exist_ok=True)
    with open(os.path.join(caddy_ctx, "Caddyfile"), "w", encoding="utf-8") as fh:
        fh.write(_caddyfile(subdomain, has_frontend, local, le_email))
    with open(os.path.join(caddy_ctx, "Dockerfile"), "w", encoding="utf-8") as fh:
        fh.write(_caddy_dockerfile())

    # ---- compose ----
    # Fix B (deploy gap #1, platform infra): provision a Redis service when the
    # generated backend reads REDIS_URL (e.g. FastAPI-Limiter). Local import avoids
    # a module-load cycle (provisioning scans via manifest._is_frontend).
    from app.devops import provisioning
    needs_redis = provisioning.needs_redis(files)
    compose_path = os.path.join(root, "docker-compose.deploy.yml")
    with open(compose_path, "w", encoding="utf-8") as fh:
        fh.write(_compose(names, has_frontend, https_host_port, http_host_port,
                          subdomain, use_images=use_images, image_refs=image_refs,
                          needs_redis=needs_redis))

    return Manifest(
        root=root,
        backend_context=backend_ctx,
        caddy_context=caddy_ctx,
        frontend_context=frontend_ctx,
        app_module=app_module,
        requirements=requirements,
        has_frontend=has_frontend,
        compose_path=compose_path,
        failures=failures,
    )
