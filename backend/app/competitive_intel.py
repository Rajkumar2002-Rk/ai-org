"""Competitive intelligence: gather competitor reviews, mine complaints,
turn the top themes into plain-English feature suggestions.
"""
import logging

from app import llm
from app.config import settings
from app.providers import fetch_competitors

logger = logging.getLogger("ba.ci")

_COMPLAINT_SYSTEM = (
    "You analyze customer reviews for a business owner who is building an app "
    "or website. Find the most common customer complaints. Group by theme. "
    "Count mentions per theme. For each theme, write a short, plain-English "
    "feature THAT THE APP OR WEBSITE ITSELF CAN PROVIDE to address the "
    "complaint (one sentence, no technical words). "
    "STRICT RULE: suggest only digital app/website features. Do NOT suggest "
    "operational or offline changes such as hiring or training staff, changing "
    "recipes or the menu itself, adding parking, or renovating the space. If a "
    "complaint is about something offline, suggest the closest digital feature "
    "(for example, for 'menu is confusing' suggest a clear, searchable online "
    "menu with photos and dietary labels; for 'long waits' suggest order-ahead "
    "with live status). Return JSON. Format: "
    '{"themes": [{"theme": string, "count": number, "example": string, '
    '"suggestion": string}]}'
)

# Maps recurring complaint keywords to a plain-English feature the new app
# can offer to solve them. Used for the fallback path and to phrase
# suggestions consistently.
_THEME_TO_FEATURE = [
    (("slow", "wait", "waiting", "minutes"), "Live wait-time updates and order-ahead so customers skip the line"),
    (("rude", "staff", "service"), "Friendly automated updates so customers always feel looked after"),
    (("crash", "app", "website", "online", "payment", "failed"), "A rock-solid online ordering and payment experience that just works"),
    (("price", "expensive", "quality"), "Clear pricing and a loyalty program that rewards repeat customers"),
    (("phone", "call", "booking", "reservation", "confirm"), "Instant online booking with automatic confirmations"),
    (("dirty", "clean"), "A clean, modern experience that builds trust from the first visit"),
    (("track", "order", "delivery"), "Real-time order tracking so customers know exactly what's happening"),
    (("loyalty", "rewards", "points"), "A loyalty and rewards program that actually applies at checkout"),
]


def _feature_for_theme(theme: str) -> str:
    low = theme.lower()
    for keywords, feature in _THEME_TO_FEATURE:
        if any(k in low for k in keywords):
            return feature
    return f"A built-in way to fix the \"{theme.lower()}\" problem customers keep mentioning"


def _fallback_themes(competitors: list[dict]) -> list[dict]:
    """Keyword-count complaints locally when no LLM is available."""
    counts: dict[str, dict] = {}
    for comp in competitors:
        for review in comp["reviews"]:
            low = review.lower()
            for keywords, _feature in _THEME_TO_FEATURE:
                if any(k in low for k in keywords):
                    theme = keywords[0]
                    entry = counts.setdefault(
                        theme, {"theme": theme, "count": 0, "example": review}
                    )
                    entry["count"] += 1
                    break
    themes = sorted(counts.values(), key=lambda t: t["count"], reverse=True)
    return themes[:5]


async def run(business_type: str, city: str, state: str) -> dict:
    """Return CI findings as plain-English suggestions for the user."""
    competitors, used_live, yelp_used = await fetch_competitors(
        business_type, city, state
    )
    all_reviews = [r for c in competitors for r in c["reviews"]]

    themes: list[dict] | None = None
    if all_reviews:
        result = await llm.complete_json(
            _COMPLAINT_SYSTEM,
            "Reviews:\n" + "\n".join(f"- {r}" for r in all_reviews),
            temperature=0.1,
        )
        if isinstance(result, dict) and isinstance(result.get("themes"), list):
            themes = result["themes"]

    if not themes:
        themes = _fallback_themes(competitors)

    findings = []
    for t in themes[:5]:
        theme = str(t.get("theme", "")).strip() or "common complaint"
        # Prefer the LLM's tailored suggestion; fall back to the keyword map
        # only when no LLM is configured (mock mode).
        suggestion = str(t.get("suggestion", "")).strip() or _feature_for_theme(theme)
        findings.append(
            {
                "theme": theme,
                "count": int(t.get("count", 1)),
                "example": str(t.get("example", "")),
                "suggestion": suggestion,
            }
        )

    # Neutral attribution list of the real places we looked at — shown to the
    # user for trust, kept separate from the (anonymized) complaint themes so
    # no named business is ever tied to a specific complaint. We deliberately
    # do NOT persist the raw reviews; only these names + map links surface.
    sources = [
        {"name": c["name"], "maps_url": c.get("maps_url")} for c in competitors
    ]
    if used_live:
        attribution = "Insights based on public reviews from Google" + (
            " and Yelp" if yelp_used else ""
        )
    else:
        attribution = "Sample insights — add market data keys to see real local businesses"

    return {
        "business_type": business_type,
        "city": city,
        "competitors_reviewed": len(competitors),
        "used_live_data": used_live and llm.is_live(),
        "findings": findings,
        "sources": sources,
        "attribution": attribution,
    }
