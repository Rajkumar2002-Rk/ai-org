"""Product Intelligence reviewer.

Runs between the BA and the Architect. Hybrid: deterministic Python owns
the budget-vs-scale reality check (predictable, never drifts); GPT-4o @ 0.4
does the judgement work — feature relevance/pruning, must vs nice-to-have
priorities, and spotting missing essentials. Falls back to a deterministic
review when no LLM is configured.
"""
import logging
import re

from app import llm
from app.config import settings

logger = logging.getLogger("pi.reviewer")

_PLAN_COSTS = {"quick": 15, "production": 50, "scale": 150}


def _budget_number(text: str) -> int | None:
    m = re.search(r"(\d+(?:\.\d+)?)", (text or "").replace(",", ""))
    return int(float(m.group(1))) if m else None


def _needs_heavier_infra(summary: dict) -> bool:
    """Does the scope realistically cost more than a bare-minimum server?"""
    mobile = (summary.get("mobile_choice") or "").lower() in ("native", "both")
    blob = " ".join([
        summary.get("build", ""),
        " ".join(summary.get("competitor_features", []) or []),
    ]).lower()
    payments = any(w in blob for w in ("payment", "pay", "checkout", "stripe", "billing"))
    return mobile or payments


def _budget_assessment(summary: dict) -> dict:
    budget = _budget_number(summary.get("budget", ""))
    plan_id = (summary.get("plan") or {}).get("id", "production")
    plan_cost = _PLAN_COSTS.get(plan_id, 50)
    heavy = _needs_heavier_infra(summary)

    if budget is None:
        return {
            "verdict": "unknown",
            "recommended_tier": plan_id,
            "detail": "No clear budget was given, so we'll size it to the plan you picked.",
        }

    # Over the plan they chose.
    if budget < plan_cost:
        return {
            "verdict": "tight",
            "recommended_tier": next(
                (p for p, c in sorted(_PLAN_COSTS.items(), key=lambda kv: kv[1])
                 if c <= budget), "quick"),
            "detail": (
                f"Your budget of about ${budget}/month is below the "
                f"~${plan_cost}/month this plan usually needs. We can start "
                f"smaller and grow later."
            ),
        }

    # Comfortable on the plan, but heavy scope on a tiny budget is still risky.
    if heavy and budget < 30:
        return {
            "verdict": "tight",
            "recommended_tier": plan_id,
            "detail": (
                f"About ${budget}/month is workable to start, but payments and/or "
                f"a mobile app usually need a bit more headroom as you grow."
            ),
        }

    return {
        "verdict": "comfortable",
        "recommended_tier": plan_id,
        "detail": f"About ${budget}/month comfortably covers this plan.",
    }


_PI_SYSTEM = (
    "You are a pragmatic product manager reviewing a plan BEFORE it is built. "
    "Given the product summary, return JSON with keys:\n"
    '- "product_read": one short sentence describing what this really is.\n'
    '- "recommendations": array of {"title","detail"} — 2 to 4 concise PM notes.\n'
    '- "features_kept": array of feature strings that genuinely fit this app.\n'
    '- "features_dropped": array of {"feature","reason"} for features that do '
    "NOT fit (e.g. customer-facing features in an internal tool). Empty if none.\n"
    '- "priorities": {"must_have": [...], "nice_to_have": [...]}.\n'
    '- "missing_essentials": array of short strings for obvious things the idea '
    "needs but the user did not mention (e.g. secure login for a payroll tool).\n"
    "Be concise, plain English, no technical jargon, JSON only."
)


async def _llm_review(summary: dict) -> dict | None:
    context = {
        "idea": summary.get("build"),
        "app_kind": summary.get("app_kind"),
        "customer_facing": summary.get("customer_facing"),
        "audience": summary.get("audience"),
        "platform": summary.get("platform"),
        "budget": summary.get("budget"),
        "growth": summary.get("growth"),
        "candidate_features": summary.get("competitor_features", []),
    }
    result = await llm.complete_json(
        _PI_SYSTEM,
        f"Product summary: {context}",
        temperature=settings.pi_temperature,
        model=settings.pi_model,
    )
    return result if isinstance(result, dict) else None


def _fallback_review(summary: dict) -> dict:
    features = summary.get("competitor_features", []) or []
    return {
        "product_read": (summary.get("build") or "your idea")[:120],
        "recommendations": [],
        "features_kept": features,
        "features_dropped": [],
        "priorities": {
            "must_have": [summary.get("build", "core functionality")],
            "nice_to_have": features,
        },
        "missing_essentials": [],
    }


async def build_review(summary: dict) -> dict:
    """Produce the Product Intelligence review for a confirmed summary."""
    budget = _budget_assessment(summary)

    review = await _llm_review(summary)
    if review is None:
        review = _fallback_review(summary)

    # Deterministic budget verdict is authoritative; surface it as the first
    # recommendation too so the user always sees it.
    review["budget_assessment"] = budget
    recs = review.get("recommendations") or []
    if budget["verdict"] in ("tight", "unknown"):
        recs.insert(0, {"title": "Budget check", "detail": budget["detail"]})
    review["recommendations"] = recs

    # Normalise the shape so callers/UI can rely on it.
    review.setdefault("features_kept", summary.get("competitor_features", []))
    review.setdefault("features_dropped", [])
    review.setdefault("priorities", {"must_have": [], "nice_to_have": []})
    review.setdefault("missing_essentials", [])
    review.setdefault("product_read", (summary.get("build") or "")[:120])
    return review
