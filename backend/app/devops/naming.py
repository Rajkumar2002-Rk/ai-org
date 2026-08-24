"""Per-project resource naming — the STRUCTURAL enforcement of isolation.

The core rule "never mix two users' apps on the same container" is not honoured
by remembering to keep things apart; it is honoured because **every name below is
a pure function of `project_id`**. There is no code path anywhere in DevOps that
accepts a caller-supplied container/network/database name, so deploying project A
can only ever resolve to A's resources. Two similarly-named projects (two
"coffee shop" apps) get different `project_id`s and therefore disjoint names.

Database isolation is at the DATABASE + NETWORK level, the strongest boundary
short of separate servers:
  * each project's app runs on its OWN docker network, so it has no route to any
    other project's database container;
  * each project's database has its OWN credentials, derived per-project, so even
    a mis-wired connection string cannot authenticate against another project's
    database.

`test_devops_offline` proves the boundary by trying to CROSS it (app A's
credentials against app B's database) and asserting the crossing is refused —
not merely by observing that no crossing happened.
"""
import hashlib
import re

from app.config import settings

# Everything for a project is prefixed with this. `p<id>` keeps the id explicit
# in `docker ps`, which makes an accidental cross-project reference obvious.
_PREFIX = "aiorg_p"


def _prefix(project_id: int) -> str:
    if not isinstance(project_id, int) or project_id <= 0:
        # Isolation depends on a real id — never fall back to a shared default.
        raise ValueError(f"project_id must be a positive int, got {project_id!r}")
    return f"{_PREFIX}{project_id}"


def _slugify(name: str) -> str:
    """A DNS-safe label from a human project name (lowercase, [a-z0-9-])."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug[:30].strip("-")) or "app"


def _salt() -> str:
    """Salt for derived, stable, non-sequential values. Uses the secrets key when
    present so subdomains/passwords are unguessable without it; falls back to a
    fixed dev salt so tests are deterministic."""
    return settings.secrets_enc_key or "ai-org-dev-salt"


def subdomain_suffix(project_id: int) -> str:
    """A short, STABLE, non-sequential suffix for the subdomain.

    Deterministic (so the URL does not change between a deploy and its health
    check, or across a redeploy), unique per project, and not a bare incrementing
    id — you cannot enumerate other apps by guessing the next number.
    """
    h = hashlib.sha256(f"subdomain:{project_id}:{_salt()}".encode()).hexdigest()
    return h[:6]


def subdomain(project_id: int, project_name: str) -> str:
    """`<slug>-<suffix>.apps.example.com` — the public host for this app."""
    label = f"{_slugify(project_name)}-{subdomain_suffix(project_id)}"
    return f"{label}.{settings.apps_subdomain}"


def derive_db_password(project_id: int) -> str:
    """A stable per-project database password.

    Must be stable: Postgres sets the password only on first initialisation of
    its data volume, so a redeploy that reused the volume with a fresh random
    password would fail authentication. Derived (not stored) so there is nothing
    extra to lose, and unguessable without the salt.
    """
    return hashlib.sha256(
        f"dbpass:{project_id}:{_salt()}".encode()
    ).hexdigest()[:32]


def names(project_id: int, project_name: str = "") -> dict:
    """The complete, isolated resource name set for a project.

    Callers use ONLY what this returns — they never construct a name themselves,
    which is what makes cross-project mixing impossible rather than merely
    discouraged.
    """
    p = _prefix(project_id)
    return {
        "project_id": project_id,
        "prefix": p,
        # docker-compose project name (namespaces every container it creates).
        "compose_project": p,
        "network": f"{p}_net",
        "db_container": f"{p}_db",
        "backend_container": f"{p}_backend",
        "frontend_container": f"{p}_frontend",
        "caddy_container": f"{p}_caddy",
        "db_volume": f"{p}_dbdata",
        # The generated app's OWN database — its own name, user, password. The app
        # is handed a connection string scoped to exactly this database.
        "db_name": "appdb",
        "db_user": f"appuser_{project_id}",
        "db_password": derive_db_password(project_id),
        # Local image tags / ECR repository names.
        "image_backend": f"ai-org/proj-{project_id}-backend",
        "image_frontend": f"ai-org/proj-{project_id}-frontend",
        "image_caddy": f"ai-org/proj-{project_id}-caddy",
        # Public identity.
        "subdomain": subdomain(project_id, project_name),
        "slug": _slugify(project_name),
    }
