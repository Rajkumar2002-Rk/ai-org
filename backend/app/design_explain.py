"""Plain-English explanation of the technical blueprint for the user.

Shown (collapsed) on the 'Design complete' message so a non-technical
owner can optionally see WHAT we designed and WHY — never any code.
"""
from app import llm

_SYS = (
    "You explain a software design to a NON-TECHNICAL business owner. Warm, "
    "professional, plain English — absolutely no code and no technical jargon "
    "(no 'API', 'schema', 'endpoint', 'React', etc.). In 3-5 short sentences or "
    "bullets, cover: what we're building for them, the main pieces in everyday "
    "terms, and WHY we made the key choices (their budget/plan, keeping their "
    "and their customers' data safe, and whether it's a website and/or app). "
    "Speak to them as 'your'."
)


def _platform_word(mobile_choice: str | None) -> str:
    return {"native": "app", "both": "website and app", "web": "website"}.get(
        mobile_choice or "web", "website"
    )


def headline(summary: dict) -> str:
    name = summary.get("business_name") or summary.get("app_kind") or "your idea"
    word = _platform_word(summary.get("mobile_choice"))
    return f"Designing your {name} {word} is done — now building the actual {word}."


async def explanation(summary: dict, blueprint: dict) -> str:
    context = {
        "business": summary.get("business_name"),
        "idea": summary.get("build"),
        "plan": (summary.get("plan") or {}).get("name"),
        "budget": summary.get("budget"),
        "website_or_app": _platform_word(summary.get("mobile_choice")),
        "key_features": (summary.get("priorities", {}) or {}).get("must_have", []),
        "protects_payments": any(
            "stripe" in (a.get("name") or "").lower()
            for a in blueprint.get("third_party_apis", [])
        ),
    }
    text = await llm.chat(_SYS, f"Details: {context}", temperature=0.5)
    return text or (
        "We've planned out everything your idea needs — the core features first, "
        "a design that fits your budget, and strong protections to keep your data "
        "and your customers safe. Now we'll build it."
    )
