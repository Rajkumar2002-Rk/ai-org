"""Content safety guardrail for the BA stage.

Screens the user's app idea AND every free-text answer, plus a final
re-screen of the confirmed summary, before anything gets built. Blocks
clearly illegal or harmful concepts while letting legitimate ideas
through — including ones that merely *mention* a sensitive topic (e.g.
"an app to help people quit gambling", "a phishing-awareness trainer").

See docs/SAFETY_POLICY.md for the full policy and rationale.

Three layers, combined conservatively:
  1. OpenAI Moderation API  — hard categories (sexual/minors, violence).
  2. LLM policy classifier  — nuanced, category-aware judgement.
  3. Keyword fallback       — works with no LLM (mock mode).
"""
import logging
import re

from app import llm

logger = logging.getLogger("ba.safety")

# Human-readable policy the classifier enforces (mirrors SAFETY_POLICY.md).
_POLICY = """\
Disallow content whose PURPOSE is any of the following:
- Real-money gambling, betting, sportsbooks, casinos, or lotteries
- Deepfakes, face/voice swapping to deceive, or non-consensual intimate imagery
- Any sexual content involving minors (never allowed)
- Selling illegal drugs, weapons, firearms, explosives, fake IDs, or stolen goods
- Fraud or scams: phishing, carding, counterfeiting, money laundering,
  fake reviews, pyramid/Ponzi schemes, academic-cheating services
- Malware, ransomware, keyloggers, botnets, DDoS, credential theft, or tools
  to hack or bypass security
- Stalkerware, secretly tracking/recording a person, doxxing, or scraping and
  selling personal data without consent
- Terrorism, violent extremism, or instructions for weapons/attacks
- Promoting or facilitating suicide, self-harm, or eating disorders
- Platforms whose purpose is harassment or hateful targeting of people
- Spam, engagement fraud, or large-scale disinformation tooling
Allow legitimate businesses even if they mention a sensitive topic (for
example an app that helps people STOP gambling, a mental-health support app,
a phishing-AWARENESS trainer, or a normal fintech/healthcare/dating app)."""

_SAFETY_SYS = (
    "You are a safety reviewer for an app-building platform. You are given a "
    "message from a user describing or adding to an app they want built. "
    "Decide whether it CLEARLY requests something disallowed.\n" + _POLICY + "\n"
    "IMPORTANT: Only block content that clearly and primarily requests a "
    "disallowed thing. Ordinary, benign, vague, or incomplete details — a "
    "budget, a color, a city, a number of users, a business name, a normal app "
    "feature — are ALLOWED. When in doubt, allow.\n"
    'Return JSON {"allowed": true|false, "category": "<short category or empty>", '
    '"reason": "<one short plain-English sentence>"}'
)

# Conservative keyword fallback (used mainly when no LLM is configured).
_BLOCK_PATTERNS = [
    (r"\b(sports?\s*betting|betting\s*app|sportsbook|casino|gambl(e|ing)|"
     r"lottery|poker\s*for\s*real\s*money)\b", "gambling"),
    (r"\b(de?ep[\s-]?fake|face[\s-]?swap|voice\s*clon|nudify|undress(ing)?\s*app|"
     r"non[\s-]?consensual)\b", "synthetic_media"),
    (r"\b(child|minor|underage)\b.{0,20}\b(sexual|porn|explicit|nude)\b", "minors"),
    (r"\b(malware|ransomware|keylogger|spyware|phishing\s*(kit|page|site)|ddos|"
     r"botnet|credential\s*(steal|stuff)|account\s*takeover|exploit\s*kit)\b", "malware"),
    (r"\b(buy|sell|sale\s*of|marketplace\s*for)\s*(cocaine|meth|heroin|fentanyl|"
     r"illegal\s*drugs|guns?|firearms?|explosives?)\b", "illegal_goods"),
    (r"\b(stalk(er)?ware|spy\s*on\s*(my|someone)|secretly\s*track|track\s*(my\s*)?"
     r"(ex|girlfriend|boyfriend|wife|husband|someone)|dox(x)?ing)\b", "surveillance"),
    (r"\b(fake\s*id|counterfeit|money\s*launder|carding|stolen\s*credit\s*card|"
     r"fake\s*reviews?|ponzi|pyramid\s*scheme|pump\s*and\s*dump)\b", "fraud"),
    (r"\b(ghost\s*gun|untraceable\s*(gun|firearm)|3d\s*printed\s*gun|bomb\s*making|"
     r"how\s*to\s*make\s*(a\s*)?(bomb|weapon))\b", "weapons"),
    (r"\b(terroris|violent\s*extremis|human\s*traffic)\w*", "extremism"),
]

# Moderation categories we treat as an immediate hard block.
_HARD_MOD = ("sexual/minors", "csam", "child")

# Moderation categories that alone shouldn't override a nuanced "allowed".
_SOFT_MOD = {"harassment", "harassment/threatening", "hate", "hate/threatening",
             "violence", "violence/graphic", "self-harm", "self-harm/intent",
             "self-harm/instructions"}


def _keyword_hit(text: str) -> str | None:
    low = text.lower()
    for pattern, category in _BLOCK_PATTERNS:
        if re.search(pattern, low):
            return category
    return None


def _is_soft(categories: list[str]) -> bool:
    return all(c in _SOFT_MOD for c in categories) if categories else True


async def screen(
    text: str, context: str | None = None
) -> tuple[bool, str | None, str | None]:
    """Screen a single piece of user text. Returns (allowed, category, reason).

    ``context`` (the app idea so far) is supplied for later answers so the
    classifier judges them in context instead of paranoid in isolation.
    """
    if not text or not text.strip():
        return True, None, None

    keyword = _keyword_hit(text)

    moderation = await llm.moderate(text)
    if moderation and moderation["flagged"]:
        cats = moderation["categories"]
        if any(any(h in c for h in _HARD_MOD) for c in cats):
            return False, "minors", "This content isn't allowed."

    if context:
        user = f"App being built: {context}\nNew detail from the user: {text}"
    else:
        user = f"User message: {text}"
    verdict = await llm.complete_json(_SAFETY_SYS, user, temperature=0.0)
    if verdict is not None:
        if not bool(verdict.get("allowed", True)):
            return False, verdict.get("category") or "policy", verdict.get("reason")
        # Classifier allows it — trust its nuance over a keyword false-positive,
        # but still respect a hard (non-soft) moderation flag.
        if moderation and moderation["flagged"] and not _is_soft(moderation["categories"]):
            return False, "moderation", "This content isn't allowed."
        return True, None, None

    # No classifier (mock mode): fall back to keyword + moderation signals.
    if keyword:
        return False, keyword, "This type of app isn't something we can build."
    if moderation and moderation["flagged"]:
        return False, "moderation", "This content isn't allowed."
    return True, None, None


async def screen_summary(fields: dict) -> tuple[bool, str | None, str | None]:
    """Final re-screen of the whole confirmed idea before locking it in."""
    parts = [
        fields.get("build", ""),
        fields.get("growth", ""),
        fields.get("reference_sites", "") or "",
        fields.get("brand_color", "") or "",
        " ".join(fields.get("selected_ci", []) or []),
    ]
    combined = ". ".join(p for p in parts if p).strip()
    return await screen(combined)
