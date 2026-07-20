"""Architect blueprint builder.

Hybrid design: deterministic Python owns the fixed rules (cloud sizing,
LLM routing, Stripe/email triggers, mobile tickets) so they can never
drift; GPT-4o generates the creative parts (tech stack, database schema,
API endpoints, sprint tickets). Falls back to a fully deterministic
blueprint when no LLM key is configured.
"""
import logging
import re

from app import llm
from app.config import settings

logger = logging.getLogger("architect.builder")


# ---------------------------------------------------------------- helpers
def _text_blob(summary: dict) -> str:
    """All the free text we scan for keywords (payment, email, etc.)."""
    priorities = summary.get("priorities", {}) or {}
    parts = [
        summary.get("build", ""),
        summary.get("growth", ""),
        " ".join(summary.get("competitor_features", []) or []),
        " ".join(summary.get("missing_essentials", []) or []),
        " ".join(priorities.get("must_have", []) or []),
        " ".join(priorities.get("nice_to_have", []) or []),
    ]
    return " ".join(parts).lower()


def _parse_users(text: str) -> int | None:
    text = (text or "").lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(million|m|thousand|k)?", text)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit in ("million", "m"):
        num *= 1_000_000
    elif unit in ("thousand", "k"):
        num *= 1_000
    return int(num)


def _parse_budget(text: str) -> int | None:
    m = re.search(r"(\d+(?:\.\d+)?)", (text or "").replace(",", ""))
    return int(float(m.group(1))) if m else None


def _is_mobile(summary: dict) -> bool:
    choice = (summary.get("mobile_choice") or "").lower()
    return "native" in choice or "both" in choice


# ---------------------------------------------------------------- rules
def _decide_tier(summary: dict) -> str:
    plan_id = (summary.get("plan") or {}).get("id", "")
    tier = {"quick": "small", "production": "medium", "scale": "large"}.get(
        plan_id, "medium"
    )

    audience = (summary.get("audience") or "").lower()
    personal = "just" in audience and "other" not in audience
    budget = _parse_budget(summary.get("budget", ""))
    users = _parse_users(summary.get("user_count", ""))

    # Personal use + small budget -> smallest, cheapest.
    if personal and budget is not None and budget <= 20:
        tier = "small"
    # Lots of users -> scalable, bigger (overrides down-sizing).
    if users is not None and users >= 100_000:
        tier = "large"
    return tier


_CLOUD = {
    "small": {
        "server_size": "1 shared vCPU, 1 GB RAM",
        "autoscaling": False,
        "estimated_monthly_cost_usd": 15,
    },
    "medium": {
        "server_size": "2 vCPU, 4 GB RAM",
        "autoscaling": False,
        "estimated_monthly_cost_usd": 50,
    },
    "large": {
        "server_size": "4 vCPU, 8 GB RAM + load balancer",
        "autoscaling": True,
        "estimated_monthly_cost_usd": 150,
    },
}


def _cloud_config(tier: str) -> dict:
    cfg = dict(_CLOUD[tier])
    cfg["tier"] = tier
    return cfg


def _llm_routing() -> dict:
    """Downstream agent -> model. Locked per CONTEXT.md; security is always
    Claude Opus 4.8, no exceptions."""
    return {
        "architect": "gpt-4o",
        # Backend on GPT-4o: the binding contract now prevents the drift and
        # hallucinated-import bugs, so Claude isn't needed here — keeps cost down.
        "backend_developer": "gpt-4o",
        # Claude Sonnet where it measurably wins: UI code.
        "frontend_developer": "claude-sonnet",
        "mobile_developer": "claude-sonnet",
        "integration_developer": "gemini-2.5-flash-lite",
        "design_review": "claude-sonnet",
        "code_reviewer": "gpt-4o-mini",
        "security_review": "claude-opus-4-8",
        "qa": "gpt-4o-mini",
        "devops": "gpt-4o-mini",
        "documentation": "gpt-4o-mini",
        "monitoring": "gpt-4o-mini",
        "auto_fix": "gpt-4o",
        "cost_tracker": "gpt-4o-mini",
    }


# Stripe Connect (POST-REVIEW DESIGN DECISION 3): the payment connection lives
# INSIDE the generated app. The business owner connects their OWN Stripe account
# through Stripe's hosted OAuth flow from the app's own settings screen. The
# platform never sees or stores any Stripe credential or token — not even once.
_STRIPE_CONNECT_STEPS = [
    "After your app is live, open its Settings (or Admin) screen.",
    "Click 'Connect Stripe' — you'll be taken to Stripe's own secure page.",
    "Sign in to (or create) your Stripe account and approve the connection.",
    "You're brought straight back to your app; your 'Pay' buttons switch on "
    "automatically once Stripe is connected.",
]

_PAYMENT_WORDS = ("payment", "pay ", "checkout", "buy", "purchase", "order",
                  "subscription", "stripe", "billing", "sell")
# The tip/gratuity family is matched on WORD BOUNDARIES so implied payments like
# "leave a tip" are caught, while substrings like "multiple" are not.
_TIP_RE = re.compile(r"\btip(s|ped|ping)?\b|\btip jar\b|\bgratuit(y|ies)\b")
_MESSAGING_WORDS = ("email", "notify", "notification", "sms", "text message",
                    "reminder", "confirmation", "alert", "updates")


def _mentions_payment(blob: str) -> bool:
    """Detect explicit or implied payment intent in the app's free text."""
    return any(w in blob for w in _PAYMENT_WORDS) or bool(_TIP_RE.search(blob))


def _has_payments(apis: list[dict]) -> bool:
    """True when Stripe Connect is part of the build (name match is tolerant of
    the 'Stripe Connect' label)."""
    return any("stripe" in (a.get("name", "").lower()) for a in apis)


def _third_party_apis(summary: dict) -> list[dict]:
    blob = _text_blob(summary)
    apis: list[dict] = []

    if _mentions_payment(blob):
        apis.append({
            "name": "Stripe Connect",
            "purpose": "Let the business owner connect their own Stripe account "
                       "and accept payments — via Stripe-hosted OAuth, inside "
                       "the app itself (no platform involvement).",
            "who_handles": "user",
            # In-app OAuth, NOT a platform-mediated connection.
            "connection": "in_app_oauth",
            "setup_steps": _STRIPE_CONNECT_STEPS,
        })

    if any(w in blob for w in _MESSAGING_WORDS):
        apis.append({
            "name": "Email & SMS notifications",
            "purpose": "Send customers confirmations and updates",
            "who_handles": "platform",
            "setup_steps": [],
        })

    return apis


# ---------------------------------------------------------------- delegated auth
# POST-REVIEW DESIGN DECISION 1: generated apps must NEVER hand-roll password
# hashing or JWT issuance. The Architect instructs the Backend Dev to integrate a
# managed identity provider instead.
#
# Default = Auth0. Why Auth0 over Clerk / AWS Cognito:
#   - Standards-based OIDC/OAuth2 that works UNIFORMLY across ALL THREE targets
#     this platform generates — the FastAPI backend, the Next.js web app, and the
#     React Native mobile app. Clerk is excellent but React/Next-first (weaker
#     first-class backend + native story); Cognito ties the app to AWS and has a
#     rougher developer experience / historically limited passkey support.
#   - Built-in MFA (for the 2FA tier) and passkeys/WebAuthn (for the Scale tier)
#     with zero custom credential code.
#   - Being plain OIDC keeps the generated app portable, matching the
#     "fully exportable, no vendor lock-in" core rule.
# Clerk and AWS Cognito stay acceptable alternatives — change AUTH_PROVIDER to
# switch the documented default.
AUTH_PROVIDER = "Auth0"
AUTH_PROVIDER_ALTERNATIVES = ("Clerk", "AWS Cognito")

# Sensitive-data signals that upgrade an app to the 2FA-required tier. Kept
# specific on purpose: a near-universal field like a plain email must NOT trip
# 2FA, but health, financial, government-id, or employee data must.
# Note "address" is intentionally qualified (home/mailing/…) so it does NOT match
# "email address" / "IP address" and spuriously trip 2FA on ordinary apps.
_PII_WORDS = ("health", "medical", "patient", "diagnosis", "prescription",
              "therapy", "ssn", "social security", "passport", "driver's",
              "driver license", "date of birth", "date-of-birth",
              "home address", "mailing address", "shipping address",
              "street address", "physical address",
              "bank account", "financial", "insurance", "tax", "credit score")
_EMPLOYEE_WORDS = ("employee", "staff", "payroll", "human resources",
                   "team member", "timesheet", "shift schedul", "worker record")


def _auth_tier(summary: dict, apis: list[dict]) -> dict:
    """Decide the delegated-auth tier from the app's feature set.

    - basic          : standard provider auth (email/password via the provider)
    - 2fa_required   : payments, PII, or employee data present -> require MFA
    - scale          : Scale plan -> passkeys as the default sign-in
    Tiers compose: a Scale app that also handles payments both defaults passkeys
    AND requires MFA. The booleans below are authoritative; `tier` is a label.
    """
    blob = _text_blob(summary)
    has_payments = _has_payments(apis)
    has_pii = any(w in blob for w in _PII_WORDS)
    has_employee = any(w in blob for w in _EMPLOYEE_WORDS)
    plan_id = (summary.get("plan") or {}).get("id", "")

    mfa_required = has_payments or has_pii or has_employee
    passkeys_default = plan_id == "scale"

    if passkeys_default:
        tier = "scale"
    elif mfa_required:
        tier = "2fa_required"
    else:
        tier = "basic"

    return {
        "provider": AUTH_PROVIDER,
        "alternatives": list(AUTH_PROVIDER_ALTERNATIVES),
        "tier": tier,
        "mfa_required": mfa_required,
        "passkeys": "default" if passkeys_default else "offered",
        "triggers": {
            "payments": has_payments,
            "pii": has_pii,
            "employee_data": has_employee,
        },
    }


def _mobile_tickets() -> list[dict]:
    return [
        {
            "id": "MOB-1",
            "title": "Set up React Native app shell",
            "assigned_to": "mobile",
            "description": "Create the React Native project, navigation, and shared theme.",
            "dependencies": ["BE-1"],
        },
        {
            "id": "MOB-2",
            "title": "Build core mobile screens",
            "assigned_to": "mobile",
            "description": "Implement the main mobile screens against the backend API.",
            "dependencies": ["MOB-1", "BE-2"],
        },
    ]


def _security_section(summary: dict, apis: list[dict], auth: dict) -> dict:
    """A concrete, mandated security baseline for every build — so the
    blueprint is secure by design, not basic CRUD. The Code Reviewer /
    Security agent (Claude Opus 4.8) enforces this on the real code later."""
    measures = [
        # DELEGATED AUTH (POST-REVIEW DECISION 1) — no custom credential handling.
        f"Authentication: delegate to a managed identity provider "
        f"(default {auth['provider']}; {', '.join(auth['alternatives'])} also "
        f"acceptable) over OAuth2/OIDC. Do NOT hand-roll password hashing or "
        f"custom JWT issuance; validate provider-issued tokens (verify JWKS "
        f"signature, issuer and audience) on every protected request.",
        "Authorization: enforce access checks on every protected endpoint (no public data leaks).",
        "Input validation: validate and sanitize all inputs to prevent SQL injection and XSS.",
        "Transport security: HTTPS/TLS on all traffic; secure cookies.",
        "Rate limiting: throttle auth and public endpoints to stop brute-force and abuse.",
        "Secrets management: keep all keys and credentials in environment variables, never in code.",
        "Data protection: encrypt sensitive data at rest; least-privilege database access.",
        "Dependency hygiene: scan dependencies for known vulnerabilities.",
        "Follow the OWASP Top-10 protections throughout.",
    ]
    if auth["mfa_required"]:
        reasons = [k.replace("_", " ") for k, v in auth["triggers"].items() if v]
        measures.append(
            "Multi-factor: REQUIRE 2FA/MFA (via the identity provider) because "
            f"sensitive data is present ({', '.join(reasons)})."
        )
    if auth["passkeys"] == "default":
        measures.append(
            "Passkeys: enable WebAuthn passkeys as the Scale-tier default sign-in."
        )

    section = {
        "review_model": "claude-opus-4-8",  # security review is ALWAYS Opus
        "auth": auth,
        "measures": measures,
    }

    if _has_payments(apis):
        measures.append(
            "Payments (PCI): never store raw card data; use Stripe-hosted payment flows."
        )
        # Flagged so the Code Reviewer's Opus security pass specifically verifies
        # the Stripe Connect feature (POST-REVIEW DECISION 3 tradeoff to track).
        section["payment_security"] = {
            "flagged_for_security_review": True,
            "feature": "Stripe Connect (in-app OAuth)",
            "must_verify": [
                "OAuth access/refresh token stored ENCRYPTED at rest, never plaintext",
                "correct Stripe Connect OAuth (signed state param, server-side code exchange)",
                "no credential leakage: no tokens or secrets in logs, API responses, or client code",
                "the platform never receives or stores any Stripe credential",
            ],
        }
    if summary.get("customer_facing", True):
        measures.append(
            "Privacy: support user data export and deletion; collect only what's needed."
        )
    return section


def _foundation_tickets() -> list[dict]:
    """Shared foundation built FIRST so every other agent imports the same
    models/session instead of inventing its own (kills cross-file drift)."""
    return [
        {
            "id": "FND-1",
            "title": "Shared database models",
            "assigned_to": "backend",
            "description": "Create backend/app/models.py defining ALL SQLAlchemy "
            "models EXACTLY as the contract's database schema specifies — same "
            "table names, same column names, same types, same relationships. "
            "This is the single source of truth every other file imports.",
            "dependencies": [],
        },
        {
            "id": "FND-2",
            "title": "Database session setup",
            "assigned_to": "backend",
            "description": "Create backend/app/database.py with the async "
            "SQLAlchemy engine, Base, async_session factory and a get_db() "
            "dependency. Read the connection string from the DATABASE_URL "
            "environment variable. Every other file imports Base/get_db from here.",
            "dependencies": [],
        },
    ]


def _security_ticket() -> dict:
    return {
        "id": "SEC-1",
        "title": "Security hardening",
        "assigned_to": "backend",
        "description": "Enforce AUTHORIZATION on every protected endpoint "
        "(authentication itself is delegated to the identity provider in AUTH-1 — "
        "do NOT build custom auth here), input validation/sanitization, rate "
        "limiting, HTTPS/TLS, encryption of sensitive data at rest, and secrets in "
        "environment variables.",
        "dependencies": ["BE-1"],
    }


def _auth_ticket(auth: dict) -> dict:
    """Delegated-auth ticket for the Backend Dev (POST-REVIEW DECISION 1).

    Instructs integration of a managed identity provider instead of custom
    password/JWT code, and carries the tier (basic / 2FA-required / passkeys)."""
    provider = auth["provider"]
    desc = (
        f"Integrate the managed identity provider {provider} for ALL "
        f"authentication using OAuth2/OIDC. Do NOT hand-roll password hashing, "
        f"salting, or custom JWT issuance — delegate sign-up, login, sessions and "
        f"password reset to {provider}. Validate provider-issued tokens (verify "
        f"the signature via the provider's JWKS, plus issuer and audience) on "
        f"every protected endpoint. Read all provider keys from environment "
        f"variables. "
    )
    if auth["mfa_required"]:
        reasons = [k.replace("_", " ") for k, v in auth["triggers"].items() if v]
        desc += (
            f"This app handles sensitive data ({', '.join(reasons)}), so REQUIRE "
            f"two-factor authentication — enable the provider's MFA/2FA. "
        )
    if auth["passkeys"] == "default":
        desc += ("This is a Scale-tier app: enable passkeys (WebAuthn) as the "
                 "default sign-in method. ")
    else:
        desc += "Offer passkeys (WebAuthn) as an optional sign-in method. "
    return {
        "id": "AUTH-1",
        "title": f"Delegated authentication via {provider} ({auth['tier']})",
        "assigned_to": "backend",
        "description": desc.strip(),
        "dependencies": ["FND-1", "FND-2"],
        # Flagged for the Opus security pass.
        "security_critical": True,
        "security_focus": [
            "no custom password hashing or hand-rolled JWT — provider only",
            "provider tokens validated (JWKS signature, issuer, audience)",
            "2FA enforced when required; provider secrets only from environment",
        ],
    }


def _stripe_connect_schema() -> list[dict]:
    """Encrypted token storage in the GENERATED APP's OWN database. The OAuth
    token is stored ENCRYPTED and never in plaintext; the platform never touches
    it (POST-REVIEW DECISION 3)."""
    return [{
        "table": "stripe_accounts",
        "columns": [
            {"name": "id", "type": "integer"},
            {"name": "stripe_account_id", "type": "string"},
            # ENCRYPTED at rest — never store the raw token.
            {"name": "access_token_encrypted", "type": "string"},
            {"name": "refresh_token_encrypted", "type": "string"},
            {"name": "scope", "type": "string"},
            {"name": "connected", "type": "boolean"},
            {"name": "created_at", "type": "datetime"},
        ],
        "relationships": [],
    }]


def _stripe_connect_endpoints() -> list[dict]:
    """OAuth flow lives in the generated app itself, under an admin/settings area."""
    return [
        {"method": "GET", "path": "/admin/stripe/connect",
         "purpose": "Start Stripe Connect OAuth — redirect the owner to Stripe's hosted flow"},
        {"method": "GET", "path": "/admin/stripe/callback",
         "purpose": "Stripe OAuth callback — verify state, exchange the code, store the token ENCRYPTED"},
        {"method": "GET", "path": "/admin/stripe/status",
         "purpose": "Whether Stripe is connected — drives the disabled-until-connected payment UI"},
    ]


def _payment_tickets() -> list[dict]:
    """Stripe Connect is a real generated FEATURE, not just a setup note
    (POST-REVIEW DECISION 3). Backend builds the OAuth handler + encrypted token
    storage in the app's own DB; Frontend builds the settings 'Connect Stripe'
    action and the visible-but-disabled payment UI. NO platform-side Stripe."""
    focus = [
        "encrypted token storage — OAuth token stored encrypted at rest, never plaintext",
        "correct Stripe Connect OAuth — signed state param (CSRF), server-side code exchange",
        "no credential leakage — no tokens/secrets in logs, API responses, or client code",
    ]
    return [
        {
            "id": "PAY-1",
            "title": "Stripe Connect OAuth handler + encrypted token storage",
            "assigned_to": "backend",
            "description": (
                "Implement Stripe Connect for the app OWNER (NOT the platform). "
                "GET /admin/stripe/connect redirects the owner to Stripe's hosted "
                "OAuth page (use STRIPE_CLIENT_ID and a signed `state` param). "
                "GET /admin/stripe/callback verifies `state`, exchanges the code "
                "for the connected account's token, and stores it in the "
                "stripe_accounts table ENCRYPTED (encryption key from the "
                "STRIPE_TOKEN_ENC_KEY environment variable — never store the raw "
                "token). GET /admin/stripe/status reports whether an account is "
                "connected. NEVER log or return tokens. No Stripe credential may "
                "ever leave the app for the platform."
            ),
            "dependencies": ["FND-1", "FND-2"],
            "security_critical": True,
            "security_focus": focus,
        },
        {
            "id": "PAY-2",
            "title": "Settings 'Connect Stripe' screen + payment UI (disabled until connected)",
            "assigned_to": "frontend",
            "description": (
                "Add a Settings/Admin screen with a 'Connect Stripe' button that "
                "calls GET /admin/stripe/connect. Read GET /admin/stripe/status: "
                "UNTIL Stripe is connected, render payment controls (e.g. 'Pay "
                "Now' buttons) VISIBLE but DISABLED, with helper text "
                "\"Connect Stripe to start accepting payments\" linking to the "
                "connect flow. Once connected, enable the payment controls. Never "
                "handle raw card data — use Stripe-hosted payment UI."
            ),
            "dependencies": ["PAY-1"],
            "security_critical": True,
            "security_focus": focus,
        },
    ]


def _integration_ticket(apis: list[dict]) -> dict:
    names = ", ".join(a["name"] for a in apis)
    return {
        "id": "INT-1",
        "title": f"Integrate third-party services: {names}",
        "assigned_to": "integration",
        "description": f"Wire up {names} and expose the needed backend hooks.",
        "dependencies": ["BE-1"],
    }


# ---------------------------------------------------------------- creative (LLM)
_ARCH_SYSTEM = (
    "You are a senior software architect. Given a product summary, design a "
    "concrete, realistic, buildable technical blueprint. Default stack: FastAPI "
    "+ PostgreSQL backend, Next.js + React (TypeScript) frontend; add React "
    "Native only if a mobile app is requested. Return JSON with EXACTLY these "
    "keys: tech_stack (object: backend, frontend, database, and mobile if "
    "applicable), database_schema (array of {table, columns:[{name,type}], "
    "relationships:[string]}), api_endpoints (array of {method, path, purpose}), "
    "sprint_tickets (array of {id, title, assigned_to, description, "
    "dependencies:[string]}). assigned_to must be one of backend, frontend, "
    "mobile, integration. Ticket ids like BE-1, FE-1, INT-1. Do NOT create "
    "tickets for custom password authentication or for payment processing — "
    "authentication is delegated to a managed identity provider and payments use "
    "Stripe Connect; both are added separately. No prose."
)


async def _generate_creative(summary: dict, mobile: bool, apis: list[dict]) -> dict | None:
    context = {
        "idea": summary.get("build"),
        "audience": summary.get("audience"),
        "expected_users": summary.get("user_count"),
        "mobile_app": mobile,
        "third_party_apis": [a["name"] for a in apis],
        "competitor_features": summary.get("competitor_features", []),
        # Product Intelligence guidance (present after the review-gate).
        "priorities": summary.get("priorities", {}),
        "missing_essentials": summary.get("missing_essentials", []),
    }
    result = await llm.complete_json(
        _ARCH_SYSTEM,
        f"Product summary: {context}",
        temperature=settings.architect_temperature,
        model=settings.architect_model,
    )
    if not isinstance(result, dict) or "tech_stack" not in result:
        return None
    return result


def _mock_creative(summary: dict, mobile: bool) -> dict:
    """Deterministic blueprint used when no LLM key is configured."""
    tech = {
        "backend": "FastAPI (Python)",
        "frontend": "Next.js + React (TypeScript)",
        "database": "PostgreSQL",
    }
    if mobile:
        tech["mobile"] = "React Native"
    return {
        "tech_stack": tech,
        "database_schema": [
            {
                "table": "users",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "email", "type": "string"},
                    {"name": "created_at", "type": "datetime"},
                ],
                "relationships": ["has many orders"],
            },
            {
                "table": "orders",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "user_id", "type": "integer"},
                    {"name": "status", "type": "string"},
                    {"name": "created_at", "type": "datetime"},
                ],
                "relationships": ["belongs to users"],
            },
        ],
        "api_endpoints": [
            {"method": "POST", "path": "/users", "purpose": "Create a user account"},
            {"method": "GET", "path": "/orders", "purpose": "List a user's orders"},
            {"method": "POST", "path": "/orders", "purpose": "Place a new order"},
        ],
        "sprint_tickets": [
            {"id": "BE-1", "title": "Set up backend + database", "assigned_to": "backend",
             "description": "FastAPI app, database models, and migrations.", "dependencies": []},
            {"id": "BE-2", "title": "Build core API endpoints", "assigned_to": "backend",
             "description": "Implement the main CRUD endpoints.", "dependencies": ["BE-1"]},
            {"id": "FE-1", "title": "Build the main UI", "assigned_to": "frontend",
             "description": "Next.js pages wired to the backend API.", "dependencies": ["BE-2"]},
        ],
    }


# ---------------------------------------------------------------- entrypoint
async def build_blueprint(summary: dict) -> dict:
    """Produce the full technical blueprint from a confirmed BA summary."""
    tier = _decide_tier(summary)
    mobile = _is_mobile(summary)
    third_party = _third_party_apis(summary)
    auth = _auth_tier(summary, third_party)

    creative = await _generate_creative(summary, mobile, third_party)
    if creative is None:
        creative = _mock_creative(summary, mobile)

    database_schema = list(creative.get("database_schema", []))
    api_endpoints = list(creative.get("api_endpoints", []))

    # Foundation first — the shared contract every other ticket builds against.
    tickets = _foundation_tickets() + list(creative.get("sprint_tickets", []))

    # Deterministic guarantees on top of the creative output:
    if mobile and not any(t.get("assigned_to") == "mobile" for t in tickets):
        tickets += _mobile_tickets()

    # Delegated auth is mandatory on every build (POST-REVIEW DECISION 1).
    tickets.append(_auth_ticket(auth))

    # Stripe Connect (POST-REVIEW DECISION 3): a real generated feature — its own
    # encrypted-token table + OAuth endpoints (frozen into the contract) plus a
    # backend and a frontend ticket. The platform builds NO Stripe connection.
    if _has_payments(third_party):
        database_schema += _stripe_connect_schema()
        api_endpoints += _stripe_connect_endpoints()
        tickets += _payment_tickets()

    # Generic integration ticket only for NON-payment third-party services
    # (Stripe Connect has its own PAY-* tickets above).
    non_payment_apis = [
        a for a in third_party if "stripe" not in a.get("name", "").lower()
    ]
    if non_payment_apis and not any(t.get("assigned_to") == "integration" for t in tickets):
        tickets.append(_integration_ticket(non_payment_apis))

    # Security is mandatory on every build.
    tickets.append(_security_ticket())

    return {
        "tech_stack": creative.get("tech_stack", {}),
        "database_schema": database_schema,
        "api_endpoints": api_endpoints,
        "third_party_apis": third_party,
        "sprint_tickets": tickets,
        "security": _security_section(summary, third_party, auth),
        "llm_routing": _llm_routing(),
        "cloud_config": _cloud_config(tier),
    }
