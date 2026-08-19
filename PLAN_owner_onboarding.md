# PLAN — Owner Account Onboarding (deploy gap #1, "problem #1")

Status: **PLAN ONLY — not implemented.** Approved direction, deferred build.
Author context: written 2026-08-19. Companion to `CONTEXT.md` §1l / §5.C.
Do NOT auto-seed secrets or implement any of this until explicitly told to build.

---

## 0. What this solves (one paragraph)

A generated app (e.g. run 1289) fail-fasts at startup because it needs real
per-owner credentials — Auth0 (login), Stripe (payments), SMTP (email), Twilio
(SMS) — and the platform has **no flow that ever collects or provisions them**.
The `secrets_store` plumbing exists (encrypted per-project, injected at deploy
STEP 5) but is never populated, so `deploy.env` is empty and Fix #20 honestly
reports "backend layer failed." This plan adds the missing collection/provision
step, surfaced in the **BA conversation before deploy**, per the user's decision.

Confirmed against the real 1289 code:
- `stripe.py` already implements **Stripe Connect OAuth** (`/authorize` → `oauth/token`,
  `STRIPE_CLIENT_ID`, stores a `StripeAccount` row with `account_id`/`access_token`).
- `auth.py` validates tokens against an **Auth0 tenant** (JWKS; `AUTH0_DOMAIN`,
  `API_AUDIENCE`).
- Boot-blocking env vars extracted from the generated code:
  `AUTH0_DOMAIN, API_AUDIENCE, STRIPE_CLIENT_ID, STRIPE_SECRET_KEY,
  STRIPE_REDIRECT_URI, STRIPE_TOKEN_ENC_KEY, SMTP_HOST/PORT/USER/PASSWORD,
  SENDER_EMAIL, TWILIO_ACCOUNT_SID/AUTH_TOKEN/PHONE_NUMBER`.

---

## 1. Decisions locked (from the design discussion)

| Provider | Model chosen |
| --- | --- |
| **Auth0 (login)** | **Platform auto-provisions** — the platform holds ONE Auth0 account and auto-creates a login app per project via the Auth0 Management API. Owner does nothing. |
| **Stripe (payments)** | **Click-to-connect (Stripe Connect OAuth)** — owner connects their own Stripe; money goes to them. Surfaced in the BA conversation. |
| **Email (SMTP)** | **Platform sends on the owner's behalf** from a platform email service. Owner does nothing (own-domain connect is a later nicety). |
| **SMS (Twilio)** | **Platform-provided if simple, else DEFER just the texting piece** — real per-business phone numbers cost money + need provisioning. The app already works without SMS. |
| **Platform Stripe account** | Plan **includes the one-time human setup steps** (Claude cannot create financial accounts). |

Scope this round: **all four providers addressed** (Stripe + Auth0 + Email, with SMS
as the one allowed-to-defer piece).

---

## 2. The platform-held vs owner-specific split (the key architectural fact)

Not every "secret" is the owner's. Sorting the boot-blocking vars by WHO owns them
changes how much actually needs an onboarding flow:

**A. Platform-held (identical for every app — the platform holds ONE of each):**
- `STRIPE_CLIENT_ID`, `STRIPE_SECRET_KEY`, `STRIPE_REDIRECT_URI` — the platform's
  own Stripe **Connect** application. The app charges "on behalf of" the owner's
  connected account using the platform secret key + the connected `account_id`.
- `AUTH0_DOMAIN`, `API_AUDIENCE` — after Auth0 auto-provision, these describe the
  per-project Auth0 app the PLATFORM created (platform-held tenant).
- `SMTP_*`, `SENDER_EMAIL` — the platform email service (if platform-sends).
- `STRIPE_TOKEN_ENC_KEY` — actually a **crypto key** → belongs to platform-solvable
  problem #3 (mint + persist), NOT owner onboarding. Cross-referenced, not built here.

**B. Genuinely owner-specific (only ONE thing):**
- The owner's **connected Stripe account id** (`acct_…`), captured by the Connect
  OAuth. Everything else the platform can hold or provision.

➡️ **Implication:** most of gap #1 is actually platform-provisioning (problem #3-style
injection). The ONLY thing that truly needs the owner in the loop is **connecting their
Stripe account**. The plan is sized accordingly.

---

## 3. THE ONE REAL FORK — where the owner's Stripe connect happens

The generated `stripe.py` already contains a full runtime Connect flow (the owner can
connect from inside the deployed app after logging in). So there are two valid designs;
they differ only in WHEN the owner connects Stripe:

- **Design 1 — platform keys only, owner connects in-app (simplest).**
  Deploy injects the platform's Stripe Connect keys (like the menu key). Backend BOOTS.
  The owner connects their Stripe from inside the live app using its existing `/oauth`
  UI. No BA connect step for Stripe. Smallest change; matches the code as-generated.
  Downside: the live app isn't payment-ready until the owner does an in-app step later.

- **Design 2 — connect in the BA conversation (the user's stated choice).**
  A new BA `connect_accounts` stage runs the Stripe Connect OAuth up front (platform-
  mediated). The owner's connected `account_id` is stored in `secrets_store`; deploy
  seeds it so the deployed app starts **already connected**. Better UX (everything ready
  at launch), matches the user's vision, more to build (platform callback + pre-seed).

**Recommendation:** build **Design 2** (user's choice), but structure the code so the
platform-key injection piece is shared with problem #3 and the in-app flow (Design 1)
remains a valid fallback/re-connect path. Flag for final confirmation before build.

---

## 4. Architecture / data flow (Design 2)

```
BA conversation (platform backend, BEFORE build/deploy)
  ├─ detects app needs {payments?, login?, notifications?} from the idea/plan
  ├─ new stage: connect_accounts
  │    • login/email/SMS  → nothing for the owner (platform provisions later, at deploy)
  │    • payments         → render "Connect your Stripe" button (BA `ui` channel)
  │         owner clicks → Stripe authorize page → owner Allows
  │         Stripe redirects → PLATFORM callback  /connect/stripe/callback?state,code
  │         platform exchanges code → owner acct_id + tokens
  │         → secrets_store.set_secret(project_id, "STRIPE_CONNECTED_ACCOUNT_ID", acct_id)
  │    • connection status gated: CONFIRM cannot complete until connected (or skipped)
  └─ persist_on_confirm (unchanged)
        ↓
Architect / Build / Secure / QA  (unchanged)
        ↓
Deploy STEP 5 (devops/orchestrator.py) — the single injection point
  ├─ platform-held (all apps that use the feature): STRIPE_CLIENT_ID/SECRET_KEY/
  │   REDIRECT_URI, SMTP_*, SENDER_EMAIL   [from platform settings, like menu key]
  ├─ Auth0 AUTO-PROVISION: create per-project Auth0 app via Management API →
  │   AUTH0_DOMAIN, API_AUDIENCE, (client id/secret) → secrets_store + env
  ├─ owner-specific: STRIPE_CONNECTED_ACCOUNT_ID  [from secrets_store, set during BA]
  ├─ crypto keys (problem #3): mint+persist STRIPE_TOKEN_ENC_KEY etc.
  └─ writes 0600 deploy.env  →  backend boots with real config
```

Callbacks land on the **platform** backend (the app isn't deployed yet), so the connect
must be platform-mediated during BA. This is why it lives in the BA stage, not the app.

---

## 5. Component-by-component plan

### 5.1 New BA stage `connect_accounts`
- **Where:** `backend/app/ba/state.py` `ORDER` — insert `CONNECT_ACCOUNTS` between
  `PRESENT_PLAN`/design stages and `CONFIRM`. Add stage constant + `next_stage` wiring.
- **Provider detection:** determine which providers this app needs. Cleanest signal is
  the plan/idea; a deterministic helper `required_providers(state)` → subset of
  {payments, login, notifications}. (Login/notifications need no owner action → platform
  provisions at deploy; only `payments` produces an owner-facing button.)
- **UI:** reuse the existing BA `ui` button channel (same mechanism as quick-choices) to
  render a **Connect Stripe** button + a live "Connected ✓ / Not connected" status.
- **Gate:** `CONFIRM` may not finalize while a required payments connection is missing,
  unless the owner explicitly taps "skip for now" (then deploy honestly walls only on the
  payments door — Fix #20 already handles that gracefully).
- **Controller:** `controller.persist_on_confirm` unchanged; connection state lives in
  `secrets_store`, not the requirements table.

### 5.2 Stripe Connect (owner click-to-connect)
- **Platform prerequisite (one-time, HUMAN — see §7):** platform Stripe **Connect**
  application → `STRIPE_CLIENT_ID`, platform `STRIPE_SECRET_KEY`, a registered redirect
  URL pointing at the platform callback.
- **New platform endpoints:**
  - `GET /connect/stripe/start?project_id=…` → builds the Stripe `/authorize` URL with a
    signed `state` (project_id + nonce, short TTL) and returns/redirects to it.
  - `GET /connect/stripe/callback?code=…&state=…` → verifies `state`, exchanges `code`
    at `oauth/token` for the owner's `stripe_user_id` (acct_id), calls
    `secrets_store.set_secret(project_id, "STRIPE_CONNECTED_ACCOUNT_ID", acct_id)`, marks
    the BA connection status connected.
- **Deploy injection:** STEP 5 adds the platform Stripe keys for any app that references
  Stripe (detector like `_has_menu_pdf`), plus the stored connected account id.
- **Note:** the generated app's own runtime `/oauth` flow stays as a valid re-connect
  path; pre-seeding just means it starts connected.

### 5.3 Auth0 auto-provision (platform, no owner action)
- **Platform prerequisite (one-time, HUMAN — §7):** a platform Auth0 account + a
  Management API app (client credentials) with rights to create Applications/APIs.
- **Where:** deploy STEP 5 (or a pre-deploy hook), only for apps whose code references
  Auth0 (detector). Using the Management API: create a per-project Application (+ API/
  audience) → obtain `AUTH0_DOMAIN`, `API_AUDIENCE`, client id/secret → store in
  `secrets_store` (idempotent: reuse if already provisioned for this project) → inject.
- **Idempotency + teardown:** record the created Auth0 app id per project so a redeploy
  reuses it and teardown can optionally delete it. Never create duplicates.

### 5.4 Email (platform sends)
- **Platform prerequisite (§7):** a platform transactional-email service (SMTP creds or
  an API). Owner does nothing.
- **Where:** deploy STEP 5 injects `SMTP_*` + a sensible `SENDER_EMAIL` (platform domain,
  optionally per-business display name) for apps that reference SMTP.
- **Later nicety (out of scope now):** owner connects their own sending domain.

### 5.5 SMS (deferred piece)
- If a simple platform Twilio number can be shared/provisioned cheaply, inject
  `TWILIO_*` the same way. Otherwise **defer just SMS**: the app boots and works; only
  text sending is unavailable, surfaced honestly (never faked). Decide at build time.

### 5.6 Storage (`secrets_store`) — keys written
- `STRIPE_CONNECTED_ACCOUNT_ID` (owner, set during BA).
- Auth0 provisioned values (set at deploy; cached per project).
- Everything else = platform settings injected at deploy, not per-project stored.
- All via the existing `set_secret`/`get_secrets` (encrypted with `SECRETS_ENC_KEY`,
  already `guard()`-redacted from logs).

---

## 6. Security considerations
- **No secret values through Claude or argv/URLs** — the OAuth `code`/tokens flow
  server-side; only opaque `state` appears in redirect URLs. Consistent with the repo's
  existing rules (AWS driver already fetches secrets via SSM, never argv).
- **Signed, short-TTL `state`** on the Stripe connect to prevent CSRF/replay; bind it to
  `project_id` and a one-time nonce.
- **Least privilege** for the platform Auth0 Management token (create-app scope only).
- **Fail-fast preserved** — if a required connection is missing, the app still fail-fasts
  and Fix #20 reports it honestly. This plan never fakes a value to force a green deploy.
- **Teardown** removes/rotates per-project provisioned resources where feasible.

---

## 7. One-time HUMAN setup (Claude cannot do these — financial/account creation)
1. **Stripe:** create/confirm the platform **Stripe Connect** application; record
   `STRIPE_CLIENT_ID`, platform `STRIPE_SECRET_KEY`; register the redirect URL
   `https://<platform-host>/connect/stripe/callback`. Put these in platform settings
   (`.env`, like the scoped menu key) — NOT committed.
2. **Auth0:** create a platform Auth0 account/tenant; create a Management API application
   with create-Application/API scopes; record its domain + client id/secret into platform
   settings.
3. **Email:** provision a platform transactional-email sender (SMTP creds or API key) +
   a sending domain; record into platform settings.
4. **(Optional) SMS:** a platform Twilio account + number strategy, if not deferring SMS.

All four are platform-level and set ONCE; they are not per-owner.

---

## 8. Test strategy (same rigor as #16–#24; all offline/deterministic)
- **Provider detection:** `required_providers` returns the right subset for real
  blueprints — 1289 (payments+login+notifications) vs a menu-only app (none owner-facing).
- **BA stage:** `connect_accounts` inserted in `ORDER` at the right spot; renders the
  Stripe button only when payments are needed; `CONFIRM` gated on connection/skip;
  existing BA conversation tests still pass (stage-order regression).
- **Stripe callback:** mock Stripe token exchange (no network) → asserts a valid
  `state` stores `STRIPE_CONNECTED_ACCOUNT_ID`; a bad/expired/forged `state` is rejected;
  nothing is stored on failure.
- **Deploy injection (STEP 5):** with the store populated + platform settings set,
  `deploy.env` for 1289 contains every boot-blocking var; **zero** injection for an app
  that doesn't use a given provider (no Stripe env for a Stripe-free app).
- **Auth0 provision:** mock the Management API → creates once, reuses on redeploy
  (idempotent), stores domain/audience; never duplicates.
- **Zero-regression:** all 14 existing offline suites still pass; no secret value ever
  logged (guard/redaction asserted).
- **End-to-end check (manual, later):** after the human §7 setup, a re-deploy of 1289
  boots the backend and walls (if at all) only on a deliberately-skipped provider.

---

## 9. Explicitly OUT of scope here (follow-ups)
- Platform-solvable trio (crypto-key mint+persist, Redis provisioning, config defaults) —
  that is the **problem #3 plan** (separate; `CONTEXT.md` §5). `STRIPE_TOKEN_ENC_KEY`
  belongs there.
- Owner's own email sending domain (nice-to-have).
- Full SMS provisioning if deferred.
- Candidate Fix #25 (gate the reviewer fix-loop) — unrelated, tracked in `CONTEXT.md` §1l.

---

## 10. Build order when we DO implement (suggested, plan-approved-first each)
1. Platform prerequisites (§7) — human, unblocks everything.
2. Deploy STEP 5 injection for platform-held vars + Auth0 auto-provision + Email
   (this alone makes 1289 boot except payments).
3. BA `connect_accounts` stage + Stripe Connect endpoints + pre-seed (the owner-facing
   piece).
4. SMS decision (provision or defer).
5. Re-run 1289 QA→deploy to verify a genuinely-live full-scope app.
