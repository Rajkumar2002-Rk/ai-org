"""LocalDocker driver — deploy the generated app as REAL containers on the host.

This is the default target. It builds real images, runs a real per-project
Postgres + backend (+ frontend) + Caddy, injects real secrets as environment,
and serves real HTTPS via Caddy's internally-trusted CA. Everything the AWS path
does, minus the cloud bill and the public certificate — so it is a faithful,
$0, fully-testable rehearsal, and its teardown discipline is the same one QA
proved (before -> during -> after).

Isolation is structural: every container/network/volume name comes from
`naming.names(project_id)`, and each app is on its OWN docker network with its
OWN database credentials, so no app can reach another's database.
"""
import asyncio
import logging
import os

from app.config import settings
from app.devops import manifest, provisioning, secrets_store
from app.devops.drivers.base import DeployDriver, DeployRequest, DeployResult
from app.qa import assembly as qa

logger = logging.getLogger("devops.driver.local")


async def run_cmd(cmd: list[str], timeout: int, cwd: str | None = None,
                  env: dict | None = None) -> tuple[int, str]:
    """Run a command without blocking the event loop; combined output, no raise."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError as exc:
        return -1, f"{cmd[0]} not found: {exc}"
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, f"timed out after {timeout}s: {' '.join(cmd[:3])}"
    return proc.returncode, (out or b"").decode("utf-8", "replace")


class LocalDockerDriver(DeployDriver):
    target = "local"

    async def build_and_up(self, req: DeployRequest) -> DeployResult:
        has_frontend = any(manifest._is_frontend(f) for f in req.files)
        https_port = qa._free_port()
        http_port = qa._free_port()

        # Fix C: set ALLOWED_ORIGINS to this deploy's EXACT origin, now that the host
        # port is known (chosen here, not in STEP 5). Only when the app reads it and
        # the owner has not set it. Same-origin via Caddy, so the HTTPS origin suffices.
        if ("ALLOWED_ORIGINS" in provisioning.required_env(req.files)
                and "ALLOWED_ORIGINS" not in req.env):
            req.env["ALLOWED_ORIGINS"] = f"https://localhost:{https_port}"

        m = manifest.build(
            req.files, req.root, req.names,
            subdomain=req.subdomain, local=True,
            le_email=req.le_email,
            https_host_port=https_port, http_host_port=http_port,
            use_images=False,
            frontend_public=manifest.frontend_public_env(req.env),
        )

        fatal = [f for f in m.failures if "no FastAPI entrypoint" in f]
        if fatal:
            return DeployResult(ok=False, error="; ".join(fatal),
                                manifest_failures=m.failures)

        # Secrets to a 0600 env-file the compose reads; removed right after `up`.
        env_path = secrets_store.write_env_file(req.root, req.env, "deploy.env")
        try:
            code, out = await run_cmd(
                ["docker", "compose", "-p", req.names["compose_project"],
                 "-f", m.compose_path, "up", "-d", "--build"],
                timeout=settings.devops_build_timeout,
                cwd=req.root,
            )
        finally:
            # Secrets on disk for as short a time as possible. Compose has already
            # baked them into the created containers' specs, so removal is safe.
            try:
                os.remove(env_path)
            except OSError:
                pass

        if code != 0:
            logger.warning("compose up failed for project %s", req.project_id)
            return DeployResult(ok=False, error=out[-1500:],
                                manifest_failures=m.failures)

        return DeployResult(
            ok=True,
            live_url=f"https://localhost:{https_port}",
            # The probe runs inside the platform container; the published port is
            # on the host, reachable via host.docker.internal (Docker Desktop).
            probe_url=f"https://host.docker.internal:{https_port}",
            https_port=https_port,
            http_port=http_port,
            server_type="local docker",
            ssl_enabled=True,
            ssl_type="self_signed_local",
            verify_tls=False,          # Caddy internal CA — health probe uses -k
            image_backend_ref=f"{req.names['compose_project']}-backend",
            image_frontend_ref=(f"{req.names['compose_project']}-frontend"
                                if has_frontend else None),
            manifest_failures=m.failures,
        )

    async def diagnostics(self, req: DeployRequest) -> str:
        n = req.names
        parts = []
        for label, cmd in (
            ("ps", ["docker", "ps", "-a", "--filter",
                    f"label=com.docker.compose.project={n['compose_project']}",
                    "--format", "{{.Names}}\t{{.Status}}"]),
            ("backend logs", ["docker", "logs", "--tail", "120",
                              n["backend_container"]]),
        ):
            _, out = await run_cmd(cmd, timeout=30)
            parts.append(f"--- {label} ---\n{out.strip()}")
        return "\n".join(parts)

    async def restart(self, req: DeployRequest) -> None:
        """Infra-only remedy: cycle the app processes. No rebuild, no source, no
        security config — just `docker restart`, so it cannot weaken anything."""
        n = req.names
        await run_cmd(
            ["docker", "restart", n["backend_container"], n["caddy_container"],
             n["frontend_container"]],
            timeout=90,
        )

    async def teardown(self, req: DeployRequest) -> None:
        """Remove containers, network and volume BY NAME — works even if the
        build dir is already gone, and proves the isolation names are the only
        handle needed."""
        n = req.names
        containers = [n["backend_container"], n["frontend_container"],
                      n["db_container"], n["caddy_container"]]
        await run_cmd(["docker", "rm", "-f", *containers], timeout=60)
        await run_cmd(["docker", "network", "rm", n["network"]], timeout=30)
        await run_cmd(["docker", "volume", "rm", n["db_volume"]], timeout=30)
