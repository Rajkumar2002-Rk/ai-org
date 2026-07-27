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
        # Gemini per CONTEXT.md UPDATED ROUTING (Week 4 onwards).
        "qa": "gemini-2.5-flash-lite",
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


def _frontend_foundation_ticket() -> dict:
    """The manifest that makes the generated UI a buildable project.

    Verification found the mirror image of the APP-1 defect on the frontend: a
    real blueprint commissioned five Next.js pages and NO package.json, so
    `next build` could not start at all. Pages are individually valid files, so
    nothing before QA notices — and QA's frontend build was itself gated behind
    the backend booting, which hid it a second time.

    Named FND-* on purpose: `developers/orchestrator._waves()` runs every FND-*
    ticket in the FIRST wave, which is right here — the manifest has no
    dependencies and later frontend agents benefit from seeing it. This is the
    OPPOSITE of APP-1, which must run last.
    """
    return {
        "id": "FND-3",
        "title": "Frontend project manifest",
        "assigned_to": "frontend",
        "filepath": "frontend/package.json",
        "description": (
            "Create frontend/package.json — the manifest that makes the "
            "interface a buildable Next.js project. It MUST be valid JSON (no "
            "comments, no trailing commas) and MUST include: a \"name\" and "
            "\"private\": true; \"scripts\" with dev/build/start wired to next; "
            "and \"dependencies\" pinning next, react and react-dom, plus "
            "\"devDependencies\" with typescript and the @types packages, since "
            "the pages are TypeScript. Only list packages that genuinely exist "
            "on npm. Do NOT invent internal packages, and do NOT add a "
            "dependency the generated pages do not import."
        ),
        "dependencies": [],
    }


# Paths named inside a ticket's own text, e.g. "Create backend/app/models.py".
_PATH_IN_TEXT = re.compile(
    r"\b((?:backend|frontend|mobile)/[\w./\[\]-]+"
    r"\.(?:py|tsx|ts|jsx|js|json|mjs))"
)

# Where a ticket's file goes when nothing names one, per agent type.
_DEFAULT_DIR = {
    "backend": ("backend/app/routes", "py"),
    "frontend": ("frontend/app", "tsx"),
    "integration": ("backend/app/integrations", "py"),
    "mobile": ("mobile/screens", "tsx"),
}
# Filenames whose NAME is meaningful to the framework — Next.js routes on
# `page.tsx` specifically, so a colliding one must move to another directory
# rather than be renamed.
_STRUCTURAL_BASENAMES = {"page.tsx", "page.jsx", "index.tsx", "index.ts"}


def _slug(text: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:40]
            or "module")


# Filler verbs/words a ticket title opens with — dropped so the CONVENTIONAL
# stem is the domain noun the generated code will actually import by.
_TITLE_FILLER = {
    "implement", "create", "build", "design", "set", "up", "setup", "add",
    "develop", "make", "the", "a", "an", "and", "for", "of", "to", "core",
    "backend", "frontend", "with", "page", "screen", "endpoint", "endpoints",
}


def _conventional_stem(title: str, ticket_id: str) -> str:
    """A SHORT, conventional module stem from an unpredictable ticket title.

    Title-slug filenames (`implement_menu_retrieval_endpoint`) are what the model
    cannot guess when it wants to import a sibling — it writes `from
    backend.app.routes.menu import ...` by convention, and the slug never matches.
    Dropping leading filler verbs and keeping the first real noun yields the name
    the model already reaches for: "Implement menu retrieval endpoint" -> `menu`,
    "Stripe Connect OAuth handler" -> `stripe`. Uniqueness is still enforced by
    the collision pass in _assign_filepaths, so a clash just gets a suffix.
    """
    words = [w for w in re.findall(r"[a-z0-9]+", (title or "").lower())
             if w not in _TITLE_FILLER]
    return (words[0] if words else _slug(ticket_id))[:40]


def _assign_filepaths(tickets: list[dict]) -> list[dict]:
    """Give every ticket ONE explicit, UNIQUE output path.

    Nothing used to decide this: each Developer agent invented its own path from
    the ticket text, so two tickets could land on the same file and the later
    one silently overwrote the earlier. A paid-for ticket's work simply vanished,
    and — worse — the surviving file could import a module written against a
    different ticket's assumptions.

    That is not theoretical. Project 201 failed to boot on
    `ImportError: cannot import name 'OrderItem'`, and of its 16 generated files
    only ~13 distinct paths survived: THREE tickets wrote backend/app/main.py and
    TWO wrote backend/app/routes/orders.py.

    Resolution order per ticket: an explicit `filepath` the Architect already
    set, else a path named in the ticket's own text, else a derived one. Then a
    global uniqueness pass that disambiguates DETERMINISTICALLY — never a silent
    overwrite.
    """
    used: set[str] = set()
    for t in tickets:
        path = (t.get("filepath") or "").strip()
        if not path:
            m = _PATH_IN_TEXT.search(f"{t.get('title', '')} {t.get('description', '')}")
            path = m.group(1) if m else ""
        if not path:
            directory, ext = _DEFAULT_DIR.get(
                t.get("assigned_to") or "backend", _DEFAULT_DIR["backend"])
            # CONVENTIONAL stem (menu, orders, stripe), not the full-title slug,
            # so a sibling's `from backend.app.routes.menu import ...` resolves.
            stem = _conventional_stem(t.get("title") or "", t.get("id") or "")
            path = (f"{directory}/{stem}/page.{ext}"
                    if t.get("assigned_to") in ("frontend", "mobile")
                    else f"{directory}/{stem}.{ext}")

        if path in used:
            head, _, base = path.rpartition("/")
            suffix = _slug(t.get("id") or "dup")
            if base in _STRUCTURAL_BASENAMES:
                # Renaming would break framework routing — move it instead.
                path = f"{head}/{suffix}/{base}"
            else:
                stem, _, ext = base.rpartition(".")
                path = f"{head}/{stem}_{suffix}.{ext}"
            n = 2
            while path in used:      # pathological: same id twice
                path = f"{path.rpartition('.')[0]}{n}.{path.rpartition('.')[2]}"
                n += 1
            logger.warning(
                "Ticket %s collided on an already-assigned filepath; moved to %s",
                t.get("id"), path,
            )
        used.add(path)
        t["filepath"] = path
    return tickets


def _frontend_layout_ticket() -> dict:
    """The Next.js App Router root layout.

    Step 5's first real `next build` failed with "doesn't have a root layout —
    make sure every page has a root layout". The App Router REQUIRES
    app/layout.tsx (it renders the <html>/<body> that wrap every page); without
    it, no page can build. This is the same class as FND-3 and APP-1 — the
    framework needs a specific file that no feature ticket owns, so the Architect
    must commission it deterministically rather than hope a page ticket happens
    to add it.

    FND-* so it lands in the first wave with the manifest; no dependencies.
    """
    return {
        "id": "FND-4",
        "title": "Frontend root layout",
        "assigned_to": "frontend",
        "filepath": "frontend/app/layout.tsx",
        "description": (
            "Create frontend/app/layout.tsx — the Next.js App Router ROOT "
            "LAYOUT, which the framework requires before any page can build. It "
            "MUST export a default React component named RootLayout that takes "
            "`{ children }: { children: React.ReactNode }` and returns "
            "<html lang=\"en\"><body>{children}</body></html> — the <html> and "
            "<body> tags are mandatory and must appear exactly once here. Keep "
            "it minimal: no data fetching, no auth, no client-only hooks. You "
            "may export `metadata`. This file is server-only — do NOT add "
            "\"use client\"."
        ),
        "dependencies": [],
    }


def _frontend_globals_ticket() -> dict:
    """The stylesheet the App Router root layout imports by convention.

    Next.js `create-next-app` scaffolds `app/globals.css` and the root layout
    imports it, so the model writes `import "./globals.css"` in layout.tsx
    whether or not anything asked it to — a real baseline run failed with
    `Module not found: Can't resolve './globals.css'` for exactly this reason.
    Rather than fight that strong convention in the layout, guarantee the file
    exists. Third foundation file the Architect had been failing to commission,
    after the manifest (FND-3) and the root layout (FND-4).

    FND-* so it lands in the first wave; no dependencies.
    """
    return {
        "id": "FND-5",
        "title": "Frontend global stylesheet",
        "assigned_to": "frontend",
        "filepath": "frontend/app/globals.css",
        "is_boilerplate": True,
        "description": (
            "Create frontend/app/globals.css — the global stylesheet the App "
            "Router root layout imports. Keep it minimal and plain CSS: a "
            "box-sizing reset, `body { margin: 0 }`, and a system font stack. "
            "Do NOT use @tailwind directives or any preprocessor syntax unless a "
            "Tailwind/PostCSS config file also exists in this project — plain CSS "
            "only, so `next build` cannot fail on an unresolved directive."
        ),
        "dependencies": [],
    }


def _security_ticket() -> dict:
    return {
        "id": "SEC-1",
        "title": "Security hardening",
        "assigned_to": "backend",
        # Conventional path — code imports middleware/helpers from
        # `backend.app.security`, not a title-slug.
        "filepath": "backend/app/security.py",
        "description": "Enforce AUTHORIZATION on every protected endpoint "
        "(authentication itself is delegated to the identity provider in AUTH-1 — "
        "do NOT build custom auth here), input validation/sanitization, rate "
        "limiting, HTTPS/TLS, encryption of sensitive data at rest, and secrets in "
        "environment variables.",
        "dependencies": ["BE-1"],
    }


def _entrypoint_ticket(other_ids: list[str]) -> dict:
    """The file that actually STARTS the app.

    Week-6 QA caught that a real blueprint commissioned five routers and no
    application to mount them on: not one generated file created a FastAPI
    instance, so nothing could boot. Weeks 3-5 all passed it because each file
    is individually valid — only running the app reveals it.

    Deliberately NOT named FND-*: the developer orchestrator runs every FND-*
    ticket in the FIRST wave, but an entrypoint has to import the routers the
    other tickets produce, so it can only be written once they exist. Hence its
    dependencies are every other ticket, which puts it in the final wave.
    """
    return {
        "id": "APP-1",
        "title": "Application entrypoint (FastAPI app + router registration)",
        "assigned_to": "backend",
        # Signals the Developer layer to inject the EXACT list of router modules
        # (derived from the routers actually generated) into this ticket's
        # prompt, so the entrypoint imports them by their real paths instead of
        # guessing conventional names. See developers/agents._router_modules —
        # a real baseline run booted-failed because main.py imported
        # `routes.menu` while the generated file was `routes/impl_menu_...py`.
        "is_entrypoint": True,
        "description": (
            "Create backend/app/main.py — the file that starts the application. "
            "It MUST: (1) create the FastAPI instance as a module-level variable "
            "named exactly `app`; (2) import EVERY router module listed in the "
            "already-generated files (use their real paths) and register each "
            "with app.include_router(...); (3) expose GET /health returning "
            "{\"status\": \"ok\"}; (4) configure CORS with an explicit allowed "
            "origin list read from an environment variable — NEVER "
            "allow_origins=[\"*\"] together with allow_credentials=True. "
            "Import shared models and the database session from the existing "
            "app.models / app.database modules — never redefine them. The app "
            "object MUST be importable as `app` (uvicorn loads "
            "`backend.app.main:app`).\n"
            "DO NOT hide import errors behind try/except — if a router cannot be "
            "imported the application must fail loudly, not start up missing "
            "features. DO NOT set, default, mock or invent ANY environment "
            "variable (no os.environ[...] = ...); configuration comes from the "
            "real environment only, and a missing required secret must fail fast."
        ),
        "dependencies": list(other_ids),
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
        f"variables. Expose FastAPI dependencies named EXACTLY `get_current_user` "
        f"and `get_current_admin_user` from this module, so other routers import "
        f"authorization from `backend.app.auth` — the conventional path. "
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
        # Conventional path: protected routers import `from backend.app.auth
        # import get_current_admin_user` by strong FastAPI convention. A real
        # build failed on `No module named 'backend.app.auth'` because this had a
        # title-slug name; pin it where the imports actually point.
        "filepath": "backend/app/auth.py",
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
    # FND-3 (manifest) and FND-4 (root layout) join it so the generated UI is a
    # buildable Next.js project rather than loose pages; without the manifest
    # `next build` cannot start, and without the root layout no page can build.
    tickets = (_foundation_tickets()
               + [_frontend_foundation_ticket(), _frontend_layout_ticket(),
                  _frontend_globals_ticket()]
               + list(creative.get("sprint_tickets", [])))

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

    # Entrypoint LAST — it registers the routers every other ticket produced,
    # so it depends on all of them and lands in the final build wave.
    tickets.append(_entrypoint_ticket([t.get("id") for t in tickets if t.get("id")]))

    # LAST: every ticket gets one explicit, unique output path. Two tickets
    # sharing a path meant one silently overwrote the other — see
    # _assign_filepaths for the real failure this caused.
    _assign_filepaths(tickets)

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
