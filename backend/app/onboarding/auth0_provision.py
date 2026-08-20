"""Auth0 — PLATFORM auto-provisioning of a per-project login (owner does nothing).

Auth0 has no consumer "connect your account" flow, so instead of asking the owner,
the platform holds ONE Auth0 tenant + a Management API app and creates a per-project
Application (the login client) + API (the token audience) at deploy time. The owner
never touches Auth0. The generated backend validates JWTs against the platform tenant
(AUTH0_DOMAIN) with the per-project audience (API_AUDIENCE).

Idempotent by construction: the provisioned values are persisted in secrets_store, so
a redeploy REUSES them (never creates a duplicate Auth0 app). If the Management app is
not configured, provisioning is skipped and the app fail-fasts on AUTH0_* honestly.

Platform prerequisites (operator-set, PLAN_owner_onboarding.md §7):
  settings.auth0_tenant_domain, auth0_mgmt_client_id, auth0_mgmt_client_secret
  (the Management app needs create:resource_servers + create:clients).

Env vars produced for the deployed app:
  AUTH0_DOMAIN      (non-secret) — the platform tenant domain.
  API_AUDIENCE      (non-secret) — the per-project API identifier.
  AUTH0_CLIENT_ID   (non-secret) — the per-project login application's client id.
  AUTH0_CLIENT_SECRET (SECRET)   — its client secret (only if the app reads it).
"""
import logging

import httpx

from app.config import settings
from app.devops import secrets_store

logger = logging.getLogger("onboarding.auth0")

# Provisioned env var names (what the generated code reads / the deploy injects).
DOMAIN_KEY = "AUTH0_DOMAIN"
AUDIENCE_KEY = "API_AUDIENCE"
CLIENT_ID_KEY = "AUTH0_CLIENT_ID"
CLIENT_SECRET_KEY = "AUTH0_CLIENT_SECRET"
# Which of the above are secret (guarded/redacted) vs plain identifiers.
_SECRET_KEYS = {CLIENT_SECRET_KEY}
# The gate: provision only when the app reads Auth0 config.
TRIGGER_KEYS = {DOMAIN_KEY, AUDIENCE_KEY, CLIENT_ID_KEY, CLIENT_SECRET_KEY}


class ProvisionError(RuntimeError):
    """Auth0 provisioning failed; never carries a secret in its message."""


def is_configured() -> bool:
    return bool(settings.auth0_tenant_domain and settings.auth0_mgmt_client_id
                and settings.auth0_mgmt_client_secret)


def _audience_for(subdomain: str, project_id: int) -> str:
    """A stable, unique API identifier (audience) for this project. Auth0 identifiers
    are opaque URIs; using the app's own origin keeps them human-readable + unique."""
    host = subdomain or f"project-{project_id}"
    return f"https://{host}/api"


async def _mgmt_token(client: httpx.AsyncClient) -> str:
    """Client-credentials token for the Management API v2."""
    base = f"https://{settings.auth0_tenant_domain}"
    resp = await client.post(f"{base}/oauth/token", json={
        "grant_type": "client_credentials",
        "client_id": settings.auth0_mgmt_client_id,
        "client_secret": settings.auth0_mgmt_client_secret,
        "audience": f"{base}/api/v2/",
    })
    if resp.status_code != 200:
        raise ProvisionError(f"Auth0 management token failed (HTTP {resp.status_code})")
    token = resp.json().get("access_token")
    if not token:
        raise ProvisionError("Auth0 management token response had no access_token")
    return token


async def _create_api(client: httpx.AsyncClient, token: str, audience: str,
                      name: str) -> None:
    """Create the resource server (API) whose identifier is the audience. A 409
    (already exists) is fine — provisioning is idempotent."""
    base = f"https://{settings.auth0_tenant_domain}"
    resp = await client.post(
        f"{base}/api/v2/resource-servers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "identifier": audience,
              "signing_alg": "RS256", "enforce_policies": True,
              "token_dialect": "access_token_authz"},
    )
    if resp.status_code not in (200, 201, 409):
        raise ProvisionError(f"Auth0 API create failed (HTTP {resp.status_code})")


async def _create_client(client: httpx.AsyncClient, token: str, name: str,
                         subdomain: str) -> tuple[str, str]:
    """Create the login Application; return (client_id, client_secret)."""
    base = f"https://{settings.auth0_tenant_domain}"
    origin = f"https://{subdomain}" if subdomain else "https://localhost"
    resp = await client.post(
        f"{base}/api/v2/clients",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "app_type": "regular_web",
              "callbacks": [f"{origin}/callback"],
              "allowed_logout_urls": [origin],
              "web_origins": [origin], "grant_types": [
                  "authorization_code", "refresh_token"]},
    )
    if resp.status_code not in (200, 201):
        raise ProvisionError(f"Auth0 client create failed (HTTP {resp.status_code})")
    body = resp.json()
    cid, csecret = body.get("client_id"), body.get("client_secret")
    if not cid:
        raise ProvisionError("Auth0 client create returned no client_id")
    return cid, csecret or ""


async def ensure_provisioned(project_id: int, subdomain: str, needed: set[str]
                             ) -> tuple[dict[str, str], dict[str, str]]:
    """Ensure this project has an Auth0 API + Application, returning
    (secret_values, nonsecret_values) to inject. IDEMPOTENT: if already provisioned
    (values in secrets_store), reuse them and make NO Auth0 calls. Skips entirely
    when the app reads no Auth0 config or the platform Management app is unconfigured
    (→ app fail-fasts honestly). Never raises into the deploy — logs + returns ({},{})
    on failure so the deploy proceeds and the health gate reports the missing config."""
    if not (needed & TRIGGER_KEYS):
        return {}, {}
    if not is_configured():
        logger.warning("Project %s needs Auth0 but the platform Management app is not "
                       "configured — the app will fail-fast on AUTH0_* (PLAN §7).",
                       project_id)
        return {}, {}

    # Idempotent reuse: a prior deploy already stored the provisioned values.
    try:
        stored = await secrets_store.get_secrets(project_id)
    except Exception:
        stored = {}
    if DOMAIN_KEY in stored and AUDIENCE_KEY in stored:
        vals = {k: stored[k] for k in TRIGGER_KEYS if k in stored}
        logger.info("Reusing existing Auth0 provisioning for project %s.", project_id)
        return _split(vals)

    audience = _audience_for(subdomain, project_id)
    name = f"proj-{project_id}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token = await _mgmt_token(client)
            await _create_api(client, token, audience, name)
            client_id, client_secret = await _create_client(client, token, name, subdomain)
    except ProvisionError as exc:
        logger.error("Auth0 provisioning failed for project %s: %s", project_id, exc)
        return {}, {}

    vals = {DOMAIN_KEY: settings.auth0_tenant_domain, AUDIENCE_KEY: audience,
            CLIENT_ID_KEY: client_id, CLIENT_SECRET_KEY: client_secret}
    # Persist so a redeploy reuses (idempotency) — store only what the app needs.
    for k, v in vals.items():
        if v:
            try:
                await secrets_store.set_secret(project_id, k, v)
            except Exception:
                logger.warning("Could not persist Auth0 %s for project %s.", k, project_id)
    return _split({k: v for k, v in vals.items() if k in needed and v})


def _split(vals: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Partition provisioned values into (secret, non-secret) for STEP 5 guarding."""
    secret = {k: v for k, v in vals.items() if k in _SECRET_KEYS}
    nonsecret = {k: v for k, v in vals.items() if k not in _SECRET_KEYS}
    return secret, nonsecret
