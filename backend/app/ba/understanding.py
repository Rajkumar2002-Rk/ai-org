"""LLM understanding layer for the BA agent.

The deterministic controller still owns the flow (one question at a time,
safety first, correct order). This module gives it the *meaning* it needs
to act well: what kind of app is this, what's the real business name, how
many users, etc. Every function degrades gracefully to a sensible default
when no LLM is configured.
"""
import logging

from app import llm

logger = logging.getLogger("ba.understanding")


_CLASSIFY_SYS = (
    "You classify a software idea for a build platform. Return JSON with keys:\n"
    '- "customer_facing": true if the app is used by the business\'s customers/'
    "the public; false if it is an internal or personal tool used only by the "
    "owner or staff (e.g. bookkeeping, payroll, inventory, admin dashboards).\n"
    '- "platform": one of "website", "app", "both", or "unknown". Only pick a '
    'specific value if the user clearly indicated it; otherwise "unknown". '
    'IMPORTANT: "a website OR an app" means they are UNDECIDED -> use "unknown" '
    'so we can ask. Only use "both" if they clearly want website AND app.\n'
    '- "kind": a short label, e.g. "internal tool", "online store", "booking", '
    '"informational", "social", "marketplace".\n'
    '- "is_local": true ONLY if the app serves customers of a specific local, '
    "physical business tied to a place (coffee shop, salon, gym, restaurant, "
    "auto shop). false for global/online apps (social, SaaS, marketplaces) and "
    "for internal/personal tools.\n"
    '- "is_food": true if the business sells food or drink and would have a '
    "MENU — restaurant, cafe, coffee shop, bakery, bar, food truck, deli, "
    "juice bar, ice-cream shop. false otherwise.\n"
    "Return ONLY that JSON object."
)


async def classify(build: str) -> dict:
    """Classify the idea. Safe defaults when no LLM: treat as customer-facing,
    platform unknown (so we ask)."""
    result = await llm.complete_json(_CLASSIFY_SYS, f"Idea: {build}", temperature=0.0)
    if not isinstance(result, dict):
        return {
            "customer_facing": True, "platform": "unknown",
            "kind": "unknown", "is_local": False, "is_food": False,
        }
    platform = str(result.get("platform", "unknown")).lower()
    if platform not in ("website", "app", "both", "unknown"):
        platform = "unknown"
    # Safety net: "website or app" is undecided, not "both" — force a question.
    low = build.lower()
    if platform == "both" and " or " in low and "both" not in low and " and " not in low:
        platform = "unknown"
    return {
        "customer_facing": bool(result.get("customer_facing", True)),
        "platform": platform,
        "kind": str(result.get("kind", "unknown")),
        "is_local": bool(result.get("is_local", False)),
        "is_food": bool(result.get("is_food", False)),
    }


_NAME_SYS = (
    "Extract the business or brand name from the user's reply. If they clearly "
    "do not have a name yet, use an empty string. Return JSON {\"name\": string}. "
    'Example: "yes my store name is raja" -> {"name": "raja"}. '
    '"not yet" -> {"name": ""}.'
)


async def extract_name(message: str) -> str | None:
    """Pull the actual business name out of a sentence; None if no name."""
    result = await llm.complete_json(_NAME_SYS, f"Reply: {message}", temperature=0.0)
    if isinstance(result, dict):
        name = str(result.get("name", "")).strip()
        return name or None
    # Fallback: use the raw text unless it's an obvious "no name".
    return None if _looks_like_no_name(message) else message.strip()


_USERS_SYS = (
    "Convert the user's answer about how many people will use the app into a "
    "short, clean value. 'just me' / 'only me' / 'myself' -> '1'. Extract "
    "numbers or ranges otherwise. Return JSON {\"count\": string}. "
    'Examples: "bro its just me" -> {"count": "1"}; "around 2000" -> '
    '{"count": "around 2000"}; "a million or two" -> {"count": "1-2 million"}.'
)


async def normalize_users(message: str) -> str:
    """Return a clean user-count string ('1' for single-user)."""
    result = await llm.complete_json(_USERS_SYS, f"Reply: {message}", temperature=0.0)
    if isinstance(result, dict):
        count = str(result.get("count", "")).strip()
        if count:
            return count
    return message.strip()


_NO_NAME = ("don't", "dont", "do not", "no name", "not yet", "none",
            "haven't", "havent", "without", "nothing")


def _looks_like_no_name(message: str) -> bool:
    low = message.strip().lower()
    return low in {"no", "nope", "n/a"} or any(h in low for h in _NO_NAME)


def is_single_user(state_fields: dict) -> bool:
    """True when only the owner will use it (skip 'how many users').

    Keyed on the audience answer — an internal *staff* tool can still have
    many users, so we don't skip just because it isn't customer-facing.
    """
    audience = (state_fields.get("audience") or "").lower()
    return "just" in audience and "other" not in audience
