"""The deploy-driver contract.

The orchestrator owns the parts that must behave IDENTICALLY regardless of where
an app runs — the security-cert drift gate, the health-probe loop, the bounded
one-shot auto-fix, the deployments row. A driver owns only the mechanics of
"build these images and bring this stack up" and "tear it down". That split is
what lets the local path be a faithful, free rehearsal of the AWS path.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DeployRequest:
    project_id: int
    project_name: str
    files: list[dict]
    names: dict
    subdomain: str
    # Non-secret discovered env + the user's secrets, already merged. The VALUES
    # have been registered with secrets_store.guard() before this point.
    env: dict[str, str]
    sizing: object                      # devops.sizing.Sizing
    root: str                           # build/working directory for this deploy
    le_email: str = ""
    # Explicit list of secret KEY names present in `env` (for the row/summary —
    # never the values).
    secret_names: list[str] = field(default_factory=list)


@dataclass
class DeployResult:
    ok: bool
    live_url: str | None = None
    # Where the health probe should hit. Differs from live_url for the local
    # driver: the stack publishes ports on the HOST, but the probe runs inside the
    # platform container, so it reaches them via host.docker.internal — while the
    # user's clickable link stays https://localhost:<port>. Defaults to live_url.
    probe_url: str | None = None
    https_port: int | None = None
    http_port: int | None = None
    server_type: str = ""
    ssl_enabled: bool = False
    ssl_type: str | None = None            # lets_encrypt | self_signed_local | none
    image_backend_ref: str | None = None
    image_frontend_ref: str | None = None
    # health probe against live_url should verify TLS? (True for real certs)
    verify_tls: bool = False
    error: str | None = None
    manifest_failures: list[str] = field(default_factory=list)


class DeployDriver(ABC):
    """A place to run one project's app. All methods must be idempotent enough to
    be called again for the one-shot auto-fix retry."""

    target: str = "base"

    @abstractmethod
    async def build_and_up(self, req: DeployRequest) -> DeployResult:
        """Build the images and bring the stack up. Returns once the containers
        are created — the orchestrator does the health probing separately, so the
        2-minute probe is the same code for every driver."""

    @abstractmethod
    async def diagnostics(self, req: DeployRequest) -> str:
        """Container status + recent logs, for the health classifier. MUST be
        safe to log (values are redacted upstream, but never dump the env-file)."""

    @abstractmethod
    async def restart(self, req: DeployRequest) -> None:
        """The ONE infra-only auto-fix remedy: restart the already-built app
        containers (e.g. after a transient database-not-ready-yet crash). It must
        NOT rebuild from changed source, and by construction it cannot touch
        generated code or security config — it only cycles processes."""

    @abstractmethod
    async def teardown(self, req: DeployRequest) -> None:
        """Remove every resource for this project. Best-effort, never raises."""
