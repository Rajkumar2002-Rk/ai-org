"""Stripe Connect — click-to-connect for the app OWNER's own Stripe account.

The generated apps take payments via Stripe Connect (the platform onboards the
owner as a connected account; charges go to the owner). This module is the
PLATFORM side of that OAuth handshake, run BEFORE deploy from the BA conversation:

  start()          -> the Stripe authorize URL the owner's browser is sent to,
                      carrying a signed, short-TTL `state` bound to the project.
  handle_callback()-> verifies `state`, exchanges the returned `code` for the
                      owner's connected account id, and PERSISTS it in
                      secrets_store (key STRIPE_CONNECTED_ACCOUNT_ID) so the deploy
                      can inject it. Nothing owner-specific is ever fabricated.
  is_connected()   -> whether this project already has a stored connection.

Platform prerequisites (operator-set, PLAN_owner_onboarding.md §7): a platform
Stripe Connect application — settings.stripe_client_id / stripe_secret_key /
stripe_redirect_uri. Absent -> connect is unavailable and we say so (never faked).

The `state` is a Fernet token (confidential + integrity-checked + time-limited)
over the project id, reusing the platform secrets key. This prevents CSRF/replay:
a callback for a project must carry a state THIS platform minted, unexpired.
"""
import json
import logging
import secrets as _secrets
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.devops import secrets_store

logger = logging.getLogger("onboarding.stripe_connect")

CONNECTED_ACCOUNT_KEY = "STRIPE_CONNECTED_ACCOUNT_ID"
_AUTHORIZE_URL = "https://connect.stripe.com/oauth/authorize"
_TOKEN_URL = "https://connect.stripe.com/oauth/token"
_STATE_TTL_SECONDS = 600            # a connect must complete within 10 minutes


class ConnectError(RuntimeError):
    """A connect step failed for a reason worth surfacing (misconfig, bad state,
    Stripe rejection). Never carries a secret in its message."""


def is_configured() -> bool:
    """True if the platform Stripe Connect application is configured. Without it
    there is no client to connect the owner to (feature genuinely unavailable)."""
    return bool(settings.stripe_client_id and settings.stripe_secret_key
                and settings.stripe_redirect_uri)


def _signer() -> Fernet:
    key = settings.secrets_enc_key
    if not key:
        raise ConnectError("secrets key is not configured; cannot sign connect state")
    return Fernet(key.encode() if isinstance(key, str) else key)


def _sign_state(project_id: int) -> str:
    payload = json.dumps({"pid": project_id, "nonce": _secrets.token_urlsafe(8)})
    return _signer().encrypt(payload.encode()).decode()


def verify_state(token: str) -> int | None:
    """Return the project id a `state` was minted for, or None if it is invalid,
    tampered, or older than the TTL. Never raises on bad input."""
    try:
        raw = _signer().decrypt(token.encode(), ttl=_STATE_TTL_SECONDS)
        return int(json.loads(raw)["pid"])
    except (InvalidToken, ValueError, KeyError, TypeError):
        return None


def start(project_id: int) -> str:
    """Build the Stripe authorize URL to send the owner's browser to. Raises
    ConnectError if the platform Connect app is not configured."""
    if not is_configured():
        raise ConnectError("Stripe Connect is not configured on the platform")
    params = {
        "response_type": "code",
        "client_id": settings.stripe_client_id,
        "scope": "read_write",
        "redirect_uri": settings.stripe_redirect_uri,
        "state": _sign_state(project_id),
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def _exchange_code(code: str) -> str:
    """Exchange an authorization `code` for the owner's connected account id
    (Stripe `stripe_user_id`). Raises ConnectError on any failure."""
    async with httpx.AsyncClient(timeout=20) as client:
        # Stripe authenticates the token exchange with the secret key as HTTP basic-auth
        # username (per current docs: `curl ... -u sk_...:`), not a body field.
        resp = await client.post(
            _TOKEN_URL,
            data={"grant_type": "authorization_code", "code": code},
            auth=(settings.stripe_secret_key or "", ""),
        )
    if resp.status_code != 200:
        # Stripe returns an error body; do NOT echo it (may reference the secret).
        raise ConnectError(f"Stripe token exchange failed (HTTP {resp.status_code})")
    account_id = resp.json().get("stripe_user_id")
    if not account_id:
        raise ConnectError("Stripe token exchange returned no connected account id")
    return account_id


async def handle_callback(code: str, state: str) -> int:
    """Verify `state`, exchange `code`, and PERSIST the owner's connected account id
    for the project. Returns the project id. Raises ConnectError on any failure so
    the caller can show a friendly retry (and never a partial/faked connection)."""
    project_id = verify_state(state)
    if project_id is None:
        raise ConnectError("connect link is invalid or has expired — please retry")
    account_id = await _exchange_code(code)
    await secrets_store.set_secret(project_id, CONNECTED_ACCOUNT_KEY, account_id)
    logger.info("Stripe connected for project %s (account stored).", project_id)
    return project_id


async def is_connected(project_id: int) -> bool:
    """True if this project already has a stored Stripe connection."""
    if not settings.secrets_enc_key:
        return False
    return CONNECTED_ACCOUNT_KEY in await secrets_store.get_secrets(project_id)
