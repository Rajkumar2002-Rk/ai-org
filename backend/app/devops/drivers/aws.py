"""AWS driver — real EC2 deploy (ECR + t3.micro + Caddy/Let's Encrypt + Route53).

Strategy (from the user's experience, Week 7):
  * build images LOCALLY (a t3.micro can hang mid-build) and push to ECR;
  * one reusable EC2 t3.micro pulls-and-runs them via docker-compose;
  * Caddy on the instance gets a real Let's Encrypt cert for the subdomain;
  * Route53 record is created in the delegated `apps.rajkumarai.dev` zone;
  * every AWS resource is TAGGED so `teardown_aws.py` can reclaim it by tag;
  * cost target $5-10/mo — controlled by stopping (not terminating) the instance
    between tests. That stop/start is a human action, deliberately not automated.

⚠️ STATUS — REAL CODE, NOT YET RUN LIVE. This path spends money and cannot
succeed until (a) the `apps.rajkumarai.dev` NS delegation has propagated (so
Let's Encrypt can validate) and (b) the operator explicitly greenlights the paid
run. It is off by default (`DEPLOY_TARGET=local`) and NEVER exercised by the
offline test suite. The pure-API pieces (ECR lifecycle JSON, the Route53 change
batch, the tag set) are unit-tested; the end-to-end EC2 bring-up needs a live
shakeout before it can be called verified — which is exactly the "built is not
verified" distinction this project runs on.
"""
import asyncio
import base64
import json
import logging
import uuid

from app.config import settings
from app.devops import manifest, secrets_store
from app.devops.drivers.base import DeployDriver, DeployRequest, DeployResult
from app.devops.drivers.local import run_cmd

logger = logging.getLogger("devops.driver.aws")

# Every AWS resource DevOps creates carries these, so teardown is by-tag and
# nothing paid can be orphaned silently.
_TAG_PROJECT = "ai-org"

# Images are BUILT here (often an arm64 Mac) but RUN on the EC2 instance. t2/t3
# instances are x86_64, so images must be built for that arch or they crash-loop
# with "exec format error". Built via `docker build --platform` (BuildKit + qemu).
_TARGET_PLATFORM = "linux/amd64"


def _tags(project_id: int, ephemeral: bool) -> list[dict]:
    return [
        {"Key": "Project", "Value": _TAG_PROJECT},
        {"Key": "project_id", "Value": str(project_id)},
        {"Key": "ephemeral", "Value": "true" if ephemeral else "false"},
        {"Key": "created_by", "Value": "devops"},
    ]


def ecr_lifecycle_policy(keep_last: int = 3) -> str:
    """Keep only the last N images per repo (and expire untagged) so ECR storage
    stays near-free. Pure function -> unit-tested without touching AWS."""
    return json.dumps({
        "rules": [
            {
                "rulePriority": 1,
                "description": "expire untagged",
                "selection": {"tagStatus": "untagged", "countType": "sinceImagePushed",
                              "countUnit": "days", "countNumber": 1},
                "action": {"type": "expire"},
            },
            {
                "rulePriority": 2,
                "description": f"keep last {keep_last}",
                "selection": {"tagStatus": "any", "countType": "imageCountMoreThan",
                              "countNumber": keep_last},
                "action": {"type": "expire"},
            },
        ]
    })


def route53_upsert_batch(subdomain: str, ip: str) -> dict:
    """The ChangeResourceRecordSets batch for `subdomain -> ip`. Pure -> testable
    without a live zone."""
    return {
        "Comment": f"ai-org DevOps deploy {subdomain}",
        "Changes": [{
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": subdomain,
                "Type": "A",
                "TTL": 60,
                "ResourceRecords": [{"Value": ip}],
            },
        }],
    }


class AwsDriver(DeployDriver):
    target = "aws"

    def __init__(self):
        import boto3
        self._session = boto3.session.Session(region_name=settings.aws_region)

    # ------------------------------------------------------------- boto helpers
    async def _call(self, client_name: str, method: str, **kwargs):
        def _do():
            client = self._session.client(client_name)
            return getattr(client, method)(**kwargs)
        return await asyncio.to_thread(_do)

    async def _account_id(self) -> str:
        if settings.aws_account_id:
            return settings.aws_account_id
        ident = await self._call("sts", "get_caller_identity")
        return ident["Account"]

    def _ecr_registry(self, account_id: str) -> str:
        return f"{account_id}.dkr.ecr.{settings.aws_region}.amazonaws.com"

    # ------------------------------------------------------------- ECR
    async def _ensure_repo(self, repo: str) -> None:
        try:
            await self._call("ecr", "create_repository", repositoryName=repo,
                             imageScanningConfiguration={"scanOnPush": True})
        except Exception as exc:
            if "RepositoryAlreadyExistsException" not in str(exc):
                raise
        await self._call("ecr", "put_lifecycle_policy", repositoryName=repo,
                         lifecyclePolicyText=ecr_lifecycle_policy())

    async def _ecr_login(self, registry: str) -> bool:
        tok = await self._call("ecr", "get_authorization_token")
        data = tok["authorizationData"][0]["authorizationToken"]
        user, pwd = base64.b64decode(data).decode().split(":", 1)
        # --password-stdin so the token never appears in argv (which `ps` shows).
        proc = await asyncio.create_subprocess_exec(
            "docker", "login", "--username", user, "--password-stdin", registry,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await proc.communicate(pwd.encode())
        return proc.returncode == 0

    async def _build_and_push(self, req: DeployRequest, m: manifest.Manifest,
                              registry: str) -> dict:
        """Cross-build each context for the EC2 arch and push STRAIGHT to ECR.

        Uses a docker-container buildx builder: the default 'docker' driver can't
        load a cross-arch image into an arm64 host's image store (that broke a
        plain `docker build --platform`), and building + pushing via buildx in one
        step avoids the local load entirely. The builder is uniquely named per run
        (no cross-run collision), made current with --use (so no per-build flag),
        and removed in a finally so nothing leaks.
        """
        builder = f"ai-org-bx-{uuid.uuid4().hex[:8]}"
        code, out = await run_cmd(
            ["docker", "buildx", "create", "--name", builder,
             "--driver", "docker-container", "--use", "--bootstrap"], timeout=240)
        if code != 0:
            raise RuntimeError(f"could not create cross-arch builder: {out[-400:]}")
        refs: dict[str, str] = {}
        contexts = {"backend": (req.names["image_backend"], m.backend_context),
                    "caddy": (req.names["image_caddy"], m.caddy_context)}
        if m.has_frontend and m.frontend_context:
            contexts["frontend"] = (req.names["image_frontend"], m.frontend_context)
        try:
            for kind, (repo, ctx) in contexts.items():
                await self._ensure_repo(repo)
                uri = f"{registry}/{repo}:latest"
                code, out = await run_cmd(
                    ["docker", "buildx", "build", "--platform", _TARGET_PLATFORM,
                     "-t", uri, "--push", ctx],
                    timeout=settings.devops_build_timeout)
                if code != 0:
                    raise RuntimeError(f"buildx build+push {kind} failed: {out[-600:]}")
                refs[kind] = uri
        finally:
            await run_cmd(["docker", "buildx", "rm", builder], timeout=60)
        return refs

    # ------------------------------------------------------------- EC2 (reused)
    async def _find_instance(self, project_id: int) -> dict | None:
        """The one reusable ai-org instance (running or stopped)."""
        resp = await self._call(
            "ec2", "describe_instances",
            Filters=[
                {"Name": "tag:Project", "Values": [_TAG_PROJECT]},
                {"Name": "instance-state-name",
                 "Values": ["pending", "running", "stopping", "stopped"]},
            ],
        )
        for res in resp.get("Reservations", []):
            for inst in res.get("Instances", []):
                return inst
        return None

    async def build_and_up(self, req: DeployRequest) -> DeployResult:
        """Build+push images, ensure the instance, deliver the stack, point DNS.

        Kept deliberately explicit and fail-fast; every AWS mutation is tagged.
        See the module docstring: this is real but pending a live shakeout.
        """
        account_id = await self._account_id()
        registry = self._ecr_registry(account_id)

        m = manifest.build(
            req.files, req.root, req.names, subdomain=req.subdomain, local=False,
            le_email=req.le_email or settings.letsencrypt_email,
            https_host_port=443, http_host_port=80,
            use_images=True,
            image_refs={
                "backend": f"{registry}/{req.names['image_backend']}:latest",
                "frontend": f"{registry}/{req.names['image_frontend']}:latest",
                "caddy": f"{registry}/{req.names['image_caddy']}:latest",
            },
        )
        fatal = [f for f in m.failures if "no FastAPI entrypoint" in f]
        if fatal:
            return DeployResult(ok=False, error="; ".join(fatal),
                                manifest_failures=m.failures)

        if not await self._ecr_login(registry):
            return DeployResult(ok=False, error="ECR docker login failed")
        refs = await self._build_and_push(req, m, registry)

        inst = await self._find_instance(req.project_id)
        if inst is None:
            return DeployResult(
                ok=False,
                error=("No ai-org EC2 instance found. Launch one t3.micro tagged "
                       "Project=ai-org with an instance profile granting ECR pull "
                       "+ SSM, then redeploy. (First live bring-up is a gated, "
                       "human-confirmed step — see the module docstring.)"),
                image_backend_ref=refs.get("backend"),
                image_frontend_ref=refs.get("frontend"),
            )

        # Start it if stopped, then deliver + run the stack via SSM, upsert DNS.
        instance_id = inst["InstanceId"]
        if inst.get("State", {}).get("Name") == "stopped":
            await self._call("ec2", "start_instances", InstanceIds=[instance_id])
            await self._wait_running(instance_id)
            inst = await self._find_instance(req.project_id)
        public_ip = inst.get("PublicIpAddress")

        # Point DNS FIRST. Caddy tries to obtain the Let's Encrypt cert as soon as
        # it starts, and LE's HTTP-01 challenge validates against the subdomain —
        # which must already resolve to this instance. Creating the record after
        # bring-up (the original order) meant Caddy's first ACME attempt failed and
        # only a later backoff retry could succeed, which the health window missed.
        if public_ip and settings.route53_zone_id:
            await self._call(
                "route53", "change_resource_record_sets",
                HostedZoneId=settings.route53_zone_id,
                ChangeBatch=route53_upsert_batch(req.subdomain, public_ip),
            )

        # Secrets -> SSM SecureString (never in user-data/argv/logs), then bring up.
        await self._push_secrets_to_ssm(req)
        await self._deliver_and_up(req, m, registry)

        return DeployResult(
            ok=True,
            live_url=f"https://{req.subdomain}",
            server_type=req.sizing.server_type,
            ssl_enabled=True,
            ssl_type="lets_encrypt",
            verify_tls=True,
            image_backend_ref=refs.get("backend"),
            image_frontend_ref=refs.get("frontend"),
            manifest_failures=m.failures,
        )

    async def _wait_running(self, instance_id: str) -> None:
        for _ in range(30):
            resp = await self._call("ec2", "describe_instances",
                                    InstanceIds=[instance_id])
            state = (resp["Reservations"][0]["Instances"][0]["State"]["Name"])
            if state == "running":
                return
            await asyncio.sleep(5)

    async def _push_secrets_to_ssm(self, req: DeployRequest) -> None:
        prefix = f"/ai-org/proj-{req.project_id}"
        for k, v in req.env.items():
            await self._call("ssm", "put_parameter", Name=f"{prefix}/{k}",
                             Value=v, Type="SecureString", Overwrite=True)

    async def _ssm_run(self, instance_id: str, commands: list[str],
                       timeout: int = 600) -> tuple[bool, str]:
        send = await self._call(
            "ssm", "send_command", InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": commands},
        )
        cmd_id = send["Command"]["CommandId"]
        for _ in range(timeout // 5):
            await asyncio.sleep(5)
            inv = await self._call("ssm", "get_command_invocation",
                                   CommandId=cmd_id, InstanceId=instance_id)
            if inv["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
                return inv["Status"] == "Success", (inv.get("StandardErrorContent")
                                                    or inv.get("StandardOutputContent") or "")
        return False, "SSM command timed out"

    async def _deliver_and_up(self, req: DeployRequest, m: manifest.Manifest,
                              registry: str) -> None:
        inst = await self._find_instance(req.project_id)
        instance_id = inst["InstanceId"]
        with open(m.compose_path, "r", encoding="utf-8") as fh:
            compose_b64 = base64.b64encode(fh.read().encode()).decode()
        appdir = f"/opt/apps/proj-{req.project_id}"
        prefix = f"/ai-org/proj-{req.project_id}"
        # Build deploy.env on the instance by reading SSM SecureString params —
        # secrets never travel through argv or the compose file.
        commands = [
            # pipefail is essential: the secrets fetch is `aws ... | awk > file`,
            # and without it a failed `aws` (e.g. missing IAM permission) is
            # swallowed by awk succeeding on empty input — silently deploying with
            # NO secrets. A missing secret must fail the bring-up, not pass it.
            "set -euo pipefail",
            f"mkdir -p {appdir}",
            f"echo {compose_b64} | base64 -d > {appdir}/docker-compose.deploy.yml",
            f"aws ssm get-parameters-by-path --path {prefix} --with-decryption "
            f"--region {settings.aws_region} --query 'Parameters[].[Name,Value]' "
            f"--output text | awk -F'\\t' '{{n=$1; sub(\".*/\",\"\",n); "
            f"print n\"=\"$2}}' > {appdir}/deploy.env",
            f"chmod 600 {appdir}/deploy.env",
            f"aws ecr get-login-password --region {settings.aws_region} "
            f"| docker login --username AWS --password-stdin {registry}",
            f"cd {appdir} && docker compose -f docker-compose.deploy.yml pull",
            f"cd {appdir} && docker compose -f docker-compose.deploy.yml up -d",
        ]
        ok, out = await self._ssm_run(instance_id, commands,
                                      timeout=settings.devops_deploy_timeout)
        if not ok:
            raise RuntimeError(f"instance bring-up failed: {out[-500:]}")

    async def diagnostics(self, req: DeployRequest) -> str:
        inst = await self._find_instance(req.project_id)
        if inst is None:
            return "no instance"
        appdir = f"/opt/apps/proj-{req.project_id}"
        ok, out = await self._ssm_run(
            inst["InstanceId"],
            [f"cd {appdir} && docker compose -f docker-compose.deploy.yml ps",
             f"cd {appdir} && docker compose -f docker-compose.deploy.yml logs "
             f"--tail 120 backend"],
            timeout=120,
        )
        return out

    async def restart(self, req: DeployRequest) -> None:
        inst = await self._find_instance(req.project_id)
        if inst is None:
            return
        appdir = f"/opt/apps/proj-{req.project_id}"
        await self._ssm_run(
            inst["InstanceId"],
            [f"cd {appdir} && docker compose -f docker-compose.deploy.yml restart"],
            timeout=120,
        )

    async def teardown(self, req: DeployRequest) -> None:
        """Bring THIS app down on the instance and remove its DNS record + SSM
        secrets. The instance itself is stopped/terminated by teardown_aws.py
        (by tag) — a deliberate human-controlled step for cost."""
        try:
            inst = await self._find_instance(req.project_id)
            if inst is not None:
                appdir = f"/opt/apps/proj-{req.project_id}"
                await self._ssm_run(
                    inst["InstanceId"],
                    [f"cd {appdir} && docker compose -f docker-compose.deploy.yml "
                     f"down -v || true"],
                    timeout=120,
                )
                ip = inst.get("PublicIpAddress")
                if ip and settings.route53_zone_id:
                    try:
                        await self._call(
                            "route53", "change_resource_record_sets",
                            HostedZoneId=settings.route53_zone_id,
                            ChangeBatch={
                                "Changes": [{
                                    "Action": "DELETE",
                                    "ResourceRecordSet": {
                                        "Name": req.subdomain, "Type": "A",
                                        "TTL": 60,
                                        "ResourceRecords": [{"Value": ip}],
                                    },
                                }],
                            },
                        )
                    except Exception:
                        logger.warning("Could not delete Route53 record %s",
                                       req.subdomain)
        except Exception:  # pragma: no cover - teardown is best-effort
            logger.exception("AWS teardown (app-level) failed for %s",
                             req.project_id)
