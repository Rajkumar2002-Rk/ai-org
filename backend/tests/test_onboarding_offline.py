"""Owner onboarding — offline proof (no Stripe, no network, no LLM).

Covers the Stripe Connect click-to-connect backbone (state signing, authorize URL,
code exchange, persistence) and the BA `connect_accounts` conversation stage
(payment-intent detection, skip logic, stage order, composed UI). Every check can
fail for the reason it exists: a tampered/expired state is rejected; the connect step
appears ONLY for payment ideas; an unconfigured platform yields no connect URL.

Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tests/test_onboarding_offline.py
"""
import asyncio
import sys

from cryptography.fernet import Fernet

from app.config import settings
settings.secrets_enc_key = settings.secrets_enc_key or Fernet.generate_key().decode()

from app.onboarding import stripe_connect as sc
from app.onboarding import auth0_provision as a0
from app.ba import controller, state as st

_failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}" + (f"  --- {detail}" if not cond and detail else ""))
    if not cond:
        _failures.append(label)


class _FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _FakeClient:
    """Minimal async-context httpx.AsyncClient stand-in; records the POST."""
    posted: dict = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, data=None, **kwargs):
        _FakeClient.posted = {"url": url, "data": data, "auth": kwargs.get("auth")}
        return _FakeClient._resp


def test_state_signing():
    print("\nA. Connect state — signed, project-bound, time-limited, tamper-proof")
    tok = sc._sign_state(1289)
    check("a state round-trips to its project id", sc.verify_state(tok) == 1289)
    check("a tampered state is rejected", sc.verify_state(tok + "x") is None)
    check("garbage is rejected (never raises)", sc.verify_state("not-a-token") is None)
    check("two states for the same project differ (nonce)", sc._sign_state(1) != sc._sign_state(1))
    # Expiry: a token older than the TTL must be refused.
    saved_ttl = sc._STATE_TTL_SECONDS
    try:
        sc._STATE_TTL_SECONDS = -1          # everything is already 'too old'
        check("an expired state is rejected", sc.verify_state(sc._sign_state(2)) is None)
    finally:
        sc._STATE_TTL_SECONDS = saved_ttl


def test_start_url():
    print("\nB. Authorize URL — only when the platform Connect app is configured")
    saved = (settings.stripe_client_id, settings.stripe_secret_key,
             settings.stripe_redirect_uri)
    try:
        settings.stripe_client_id = settings.stripe_secret_key = None
        settings.stripe_redirect_uri = None
        check("is_configured False when unset", not sc.is_configured())
        try:
            sc.start(1)
            check("start() refuses when unconfigured", False)
        except sc.ConnectError:
            check("start() refuses when unconfigured", True)

        settings.stripe_client_id = "ca_platform"
        settings.stripe_secret_key = "sk_live_SECRET"
        settings.stripe_redirect_uri = "https://platform/connect/stripe/callback"
        check("is_configured True when set", sc.is_configured())
        url = sc.start(42)
        check("authorize URL targets Stripe Connect",
              url.startswith("https://connect.stripe.com/oauth/authorize?"))
        check("URL carries the platform client_id", "client_id=ca_platform" in url)
        check("URL carries a state bound to the project",
              "state=" in url and sc.verify_state(url.split("state=")[1].split("&")[0]) == 42)
        check("URL never leaks the platform SECRET", "sk_live_SECRET" not in url)
    finally:
        (settings.stripe_client_id, settings.stripe_secret_key,
         settings.stripe_redirect_uri) = saved


def test_callback():
    print("\nC. Callback — verify state, exchange code, PERSIST the connected account")
    stored: dict = {}

    async def _fake_set(pid, key, value):
        stored[(pid, key)] = value

    orig_client = sc.httpx.AsyncClient
    orig_set = sc.secrets_store.set_secret
    sc.httpx.AsyncClient = _FakeClient
    sc.secrets_store.set_secret = _fake_set
    try:
        # Happy path: valid state + Stripe returns a connected account.
        _FakeClient._resp = _FakeResp(200, {"stripe_user_id": "acct_OWNER123"})
        state = sc._sign_state(777)
        pid = asyncio.run(sc.handle_callback("auth_code_abc", state))
        check("callback returns the project id from the state", pid == 777)
        check("the connected account id is PERSISTED for the project",
              stored.get((777, sc.CONNECTED_ACCOUNT_KEY)) == "acct_OWNER123")
        check("the code exchange POSTs to Stripe's token endpoint with the code",
              _FakeClient.posted["url"] == sc._TOKEN_URL
              and _FakeClient.posted["data"]["code"] == "auth_code_abc")
        check("the exchange uses HTTP basic-auth (secret key), not a client_secret body field",
              isinstance(_FakeClient.posted["auth"], tuple)
              and "client_secret" not in _FakeClient.posted["data"])

        # A bad state never reaches Stripe and stores nothing.
        stored.clear()
        try:
            asyncio.run(sc.handle_callback("code", "tampered-state"))
            check("a bad state is refused", False)
        except sc.ConnectError:
            check("a bad state is refused", True)
        check("nothing is stored on a bad state", stored == {})

        # Stripe rejecting the exchange raises, stores nothing (never a partial connect).
        _FakeClient._resp = _FakeResp(400, {"error": "invalid_grant"})
        try:
            asyncio.run(sc.handle_callback("bad_code", sc._sign_state(9)))
            check("a Stripe rejection raises", False)
        except sc.ConnectError as e:
            check("a Stripe rejection raises without leaking the body",
                  "invalid_grant" not in str(e))
    finally:
        sc.httpx.AsyncClient = orig_client
        sc.secrets_store.set_secret = orig_set


def test_ba_stage():
    print("\nD. BA connect_accounts stage — payment-intent, skip, order, composed UI")
    # Stage order: connect_accounts sits right before confirm.
    check("connect_accounts is in the stage ORDER just before confirm",
          st.ORDER[st.ORDER.index(st.CONNECT_ACCOUNTS) + 1] == st.CONFIRM)

    pay = st.BAState(project_id=5, stage=st.CONNECT_ACCOUNTS,
                     fields={"build": "an online store to sell shoes", "business_name": "Kicks"})
    nopay = st.BAState(project_id=6, stage=st.CONNECT_ACCOUNTS,
                       fields={"build": "a personal blog about hiking"})
    check("payment idea (store/sell) needs payments", controller._needs_payments(pay))
    check("non-payment idea (blog) does not", not controller._needs_payments(nopay))
    check("the connect step is SHOWN for a payment idea",
          not controller._should_skip(st.CONNECT_ACCOUNTS, pay))
    check("the connect step is SKIPPED when there's no payment intent",
          controller._should_skip(st.CONNECT_ACCOUNTS, nopay))
    check("an explicit stored flag overrides the keyword scan",
          not controller._needs_payments(
              st.BAState(project_id=7, stage=st.CONNECT_ACCOUNTS,
                         fields={"build": "a store", "needs_payments": False})))

    # Composed UI: a real connect button pointing at the platform start endpoint.
    saved = settings.secrets_enc_key
    out = asyncio.run(controller.compose(pay))
    check("compose renders the connect_accounts UI", out["ui"]["kind"] == "connect_accounts")
    prov = out["ui"]["providers"][0]
    check("it offers a Stripe connect button for THIS project",
          prov["id"] == "stripe" and prov["url"] == "/connect/stripe/start?project_id=5")
    check("the stage is skippable (owner can connect later)", out["ui"]["skippable"] is True)
    settings.secrets_enc_key = saved

    # Ingest records an explicit skip.
    controller.ingest(pay, "skip for now")
    check("saying 'skip' records payments_connect_skipped",
          pay.fields.get("payments_connect_skipped") is True)


class _Auth0Client:
    """Fake httpx.AsyncClient dispatching Auth0 Management calls by URL."""
    calls: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _Auth0Client.calls.append(url)
        if url.endswith("/oauth/token"):
            return _FakeResp(200, {"access_token": "mgmt_tok"})
        if url.endswith("/api/v2/resource-servers"):
            return _FakeResp(201, {"id": "rs_1"})
        if url.endswith("/api/v2/clients"):
            return _FakeResp(201, {"client_id": "cid_ABC", "client_secret": "csec_XYZ"})
        return _FakeResp(500, {})


def test_auth0_provision():
    print("\nE. Auth0 per-project auto-provision — owner does nothing, idempotent")
    saved = (settings.auth0_tenant_domain, settings.auth0_mgmt_client_id,
             settings.auth0_mgmt_client_secret)
    orig_client = a0.httpx.AsyncClient
    orig_get = a0.secrets_store.get_secrets
    orig_set = a0.secrets_store.set_secret
    needed = {a0.DOMAIN_KEY, a0.AUDIENCE_KEY, a0.CLIENT_ID_KEY, a0.CLIENT_SECRET_KEY}
    try:
        # Unconfigured platform -> skip, app fail-fasts honestly.
        settings.auth0_tenant_domain = None
        s, n = asyncio.run(a0.ensure_provisioned(1, "app.example.com", needed))
        check("skips when the platform Auth0 Management app is unconfigured",
              s == {} and n == {})

        settings.auth0_tenant_domain = "tenant.us.auth0.com"
        settings.auth0_mgmt_client_id = "mgmt_id"
        settings.auth0_mgmt_client_secret = "mgmt_secret"
        check("is_configured True when the Management app is set", a0.is_configured())

        # App reads no Auth0 config -> nothing provisioned (no calls).
        _Auth0Client.calls = []
        a0.httpx.AsyncClient = _Auth0Client
        s, n = asyncio.run(a0.ensure_provisioned(1, "app.example.com", {"REDIS_URL"}))
        check("does nothing when the app reads no Auth0 config",
              s == {} and n == {} and _Auth0Client.calls == [])

        # Happy path: create API + client, split secret/non-secret, persist.
        stored: dict = {}

        async def _get(pid):
            return dict(stored)

        async def _set(pid, key, value):
            stored[key] = value
        a0.secrets_store.get_secrets = _get
        a0.secrets_store.set_secret = _set
        _Auth0Client.calls = []
        s, n = asyncio.run(a0.ensure_provisioned(42, "app42.example.com", needed))
        check("AUTH0_CLIENT_SECRET is in the SECRET bucket",
              s.get(a0.CLIENT_SECRET_KEY) == "csec_XYZ" and list(s) == [a0.CLIENT_SECRET_KEY])
        check("domain/audience/client_id are NON-secret",
              n.get(a0.DOMAIN_KEY) == "tenant.us.auth0.com"
              and n.get(a0.AUDIENCE_KEY) == "https://app42.example.com/api"
              and n.get(a0.CLIENT_ID_KEY) == "cid_ABC", str(n))
        check("it created the resource-server (API) and the client",
              any("resource-servers" in u for u in _Auth0Client.calls)
              and any("/clients" in u for u in _Auth0Client.calls))
        check("provisioned values are PERSISTED for idempotent reuse",
              stored.get(a0.DOMAIN_KEY) == "tenant.us.auth0.com"
              and stored.get(a0.AUDIENCE_KEY) == "https://app42.example.com/api")

        # Idempotency: a redeploy reuses stored values and makes NO Auth0 calls.
        _Auth0Client.calls = []
        s2, n2 = asyncio.run(a0.ensure_provisioned(42, "app42.example.com", needed))
        check("a redeploy REUSES stored provisioning (no Auth0 calls)",
              _Auth0Client.calls == [] and n2.get(a0.AUDIENCE_KEY) == "https://app42.example.com/api")

        # A Management API failure never raises into the deploy.
        class _Fail(_Auth0Client):
            async def post(self, url, json=None, headers=None):
                return _FakeResp(500, {})
        a0.httpx.AsyncClient = _Fail
        stored.clear()
        s3, n3 = asyncio.run(a0.ensure_provisioned(99, "x.example.com", needed))
        check("a provisioning failure returns empty (deploy proceeds, health gate reports it)",
              s3 == {} and n3 == {})
    finally:
        a0.httpx.AsyncClient = orig_client
        a0.secrets_store.get_secrets = orig_get
        a0.secrets_store.set_secret = orig_set
        (settings.auth0_tenant_domain, settings.auth0_mgmt_client_id,
         settings.auth0_mgmt_client_secret) = saved


def test_auth0_degraded_resilience():
    """Run 1950: Auth0 provisioning 403'd (tenant app-limit/scope) and the app fail-fasted
    on the missing AUTH0_* -> the whole certified, QA-clean deploy died. The resilience fix
    gives the deploy safe PLACEHOLDER Auth0 config so the app BOOTS and goes LIVE (public
    features work; login degraded), reported honestly."""
    print("\n=== Auth0 graceful degradation (deploy stays live when provisioning fails) ===")
    from app.onboarding import auth0_provision as a0
    needed = {"AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET", "AUTH0_AUDIENCE",
              "DATABASE_URL", "STRIPE_CLIENT_ID"}
    ph = a0.placeholder_config(needed)
    check("placeholder covers exactly the Auth0 keys the app reads (not DB/Stripe)",
          set(ph) == {"AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET", "AUTH0_AUDIENCE"},
          str(sorted(ph)))
    check("the placeholder domain is a non-resolving .invalid (JWKS fails cleanly, no crash)",
          ph["AUTH0_DOMAIN"].endswith(".invalid"))
    check("every placeholder value is truthy (the app's `if not AUTH0_DOMAIN` fail-fast passes)",
          all(ph.values()))
    check("an app that reads NO Auth0 config gets no placeholders",
          a0.placeholder_config({"DATABASE_URL", "REDIS_URL"}) == {})
    check("the client secret is still classified secret (guarded/redacted)",
          "AUTH0_CLIENT_SECRET" in a0._SECRET_KEYS)


def main():
    print("=" * 64)
    print("Owner onboarding offline proof (no Stripe, no Auth0, no network, no LLM)")
    print("=" * 64)
    test_state_signing()
    test_start_url()
    test_callback()
    test_ba_stage()
    test_auth0_provision()
    test_auth0_degraded_resilience()
    print("\n" + "=" * 64)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    main()
