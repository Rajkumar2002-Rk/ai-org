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


_STRIPE_STEPS = [
    "Go to stripe.com and sign up for a free account.",
    "Open the 'Developers' menu, then click 'API keys'.",
    "Copy your 'Secret key'.",
    "Paste it here when we ask for it.",
]

_PAYMENT_WORDS = ("payment", "pay ", "checkout", "buy", "purchase", "order",
                  "subscription", "stripe", "billing", "sell")
_MESSAGING_WORDS = ("email", "notify", "notification", "sms", "text message",
                    "reminder", "confirmation", "alert", "updates")


def _third_party_apis(summary: dict) -> list[dict]:
    blob = _text_blob(summary)
    apis: list[dict] = []

    if any(w in blob for w in _PAYMENT_WORDS):
        apis.append({
            "name": "Stripe",
            "purpose": "Accept online payments securely",
            "who_handles": "user",
            "setup_steps": _STRIPE_STEPS,
        })

    if any(w in blob for w in _MESSAGING_WORDS):
        apis.append({
            "name": "Email & SMS notifications",
            "purpose": "Send customers confirmations and updates",
            "who_handles": "platform",
            "setup_steps": [],
        })

    return apis


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


def _security_section(summary: dict, apis: list[dict]) -> dict:
    """A concrete, mandated security baseline for every build — so the
    blueprint is secure by design, not basic CRUD. The Code Reviewer /
    Security agent (Claude Opus 4.8) enforces this on the real code later."""
    measures = [
        "Authentication: hash passwords with bcrypt; issue short-lived JWT session tokens.",
        "Authorization: enforce access checks on every protected endpoint (no public data leaks).",
        "Input validation: validate and sanitize all inputs to prevent SQL injection and XSS.",
        "Transport security: HTTPS/TLS on all traffic; secure cookies.",
        "Rate limiting: throttle auth and public endpoints to stop brute-force and abuse.",
        "Secrets management: keep all keys and credentials in environment variables, never in code.",
        "Data protection: encrypt sensitive data at rest; least-privilege database access.",
        "Dependency hygiene: scan dependencies for known vulnerabilities.",
        "Follow the OWASP Top-10 protections throughout.",
    ]
    if any(a["name"] == "Stripe" for a in apis):
        measures.append(
            "Payments (PCI): never store raw card data; use Stripe-hosted payment flows."
        )
    if summary.get("customer_facing", True):
        measures.append(
            "Privacy: support user data export and deletion; collect only what's needed."
        )
    return {
        "review_model": "claude-opus-4-8",  # security review is ALWAYS Opus
        "measures": measures,
    }


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
        "description": "Enforce auth on every endpoint, input validation/sanitization, "
        "rate limiting, HTTPS/TLS, encryption of sensitive data, and secrets in "
        "environment variables.",
        "dependencies": ["BE-1"],
    }


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
    "mobile, integration. Ticket ids like BE-1, FE-1, INT-1. No prose."
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

    creative = await _generate_creative(summary, mobile, third_party)
    if creative is None:
        creative = _mock_creative(summary, mobile)

    # Foundation first — the shared contract every other ticket builds against.
    tickets = _foundation_tickets() + list(creative.get("sprint_tickets", []))

    # Deterministic guarantees on top of the creative output:
    if mobile and not any(t.get("assigned_to") == "mobile" for t in tickets):
        tickets += _mobile_tickets()
    if third_party and not any(t.get("assigned_to") == "integration" for t in tickets):
        tickets.append(_integration_ticket(third_party))
    # Security is mandatory on every build.
    tickets.append(_security_ticket())

    return {
        "tech_stack": creative.get("tech_stack", {}),
        "database_schema": creative.get("database_schema", []),
        "api_endpoints": creative.get("api_endpoints", []),
        "third_party_apis": third_party,
        "sprint_tickets": tickets,
        "security": _security_section(summary, third_party),
        "llm_routing": _llm_routing(),
        "cloud_config": _cloud_config(tier),
    }
