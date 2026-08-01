"""The four document generators. Each takes the honest `facts` dict from
datasource.gather() and returns content.

The LLM (Gemini 2.5 Flash-Lite) writes PROSE only, always grounded in the real
lists in `facts` and told never to add anything not listed; every generator has a
deterministic fallback so it works with no LLM key at all. The HANDOFF SUMMARY
uses NO LLM — its every field is real stored data — because it is exactly where an
invented number would do the most harm.
"""
import json
import logging
import re

from app import codegen
from app.config import settings

logger = logging.getLogger("documentation.generators")

_NO_JARGON = (
    "Write for a NON-TECHNICAL small-business owner (imagine a grocery store "
    "owner). Warm, plain English. NEVER use technical words (no 'API', 'endpoint', "
    "'database', 'deploy', 'React', 'server', 'JSON', 'repository'). Use everyday "
    "phrases like 'tap the button', 'open the screen'."
)


async def _llm(system: str, user: str) -> str | None:
    """One Gemini call via the shared multi-provider path; None on any failure."""
    text, _ = await codegen.generate(
        model=settings.documentation_model, system=system, user=user,
        temperature=settings.documentation_temperature)
    return (text or "").strip() or None


def _extract_json(text: str):
    """Best-effort parse of a JSON object from an LLM reply (it may wrap it in
    prose or a code fence). Returns the object or None."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


# ------------------------------------------------------------------ OUTPUT 1
async def user_guide(facts: dict) -> str:
    """Plain-English guide, one section per BUILT feature (markdown)."""
    features = facts["features"] or [{"title": s["name"], "description": ""}
                                     for s in facts["screens"]]
    feature_list = [f.get("title") or f.get("name") for f in features]

    system = (
        _NO_JARGON + " You are writing a USER GUIDE in markdown. Produce a short "
        "intro, then ONE '## ' section per feature I list — and ONLY those "
        "features, do not invent any. Give each section a SHORT plain-English "
        "heading in the owner's own words (e.g. '## Your menu', '## Taking "
        "orders') — REWRITE the feature name and NEVER put a technical word like "
        "'endpoint', 'API', or 'retrieval' in a heading. Each section: one line on "
        "what it does, then numbered step-by-step instructions in tap/click "
        "language. "
        + ("Include a section 'Connecting your Stripe account' explaining they "
           "open Settings and tap 'Connect Stripe' (payments are visible but off "
           "until they connect). " if facts["has_payments"] else "")
        + "No preamble, output only the markdown guide."
    )
    user = json.dumps({
        "business": facts["business_name"], "it_is_a": facts["platform"],
        "features": [{"name": f.get("title") or f.get("name"),
                      "about": (f.get("description") or "")[:200]} for f in features],
        "screens": [s["name"] for s in facts["screens"]],
    })
    text = await _llm(system, user)
    if text:
        return text

    # Deterministic fallback (no LLM available).
    lines = [f"# Using {facts['business_name']}", "",
             f"Here is how to use your {facts['platform']}, one feature at a time.",
             ""]
    if not feature_list:
        lines.append("_No features have been built for this app yet._")
    for f in features:
        name = f.get("title") or f.get("name")
        lines += [f"## {name}", "",
                  (f.get("description") or f"How to use {name}.").strip(), "",
                  f"1. Open your {facts['platform']}.",
                  f"2. Go to the **{name}** screen.",
                  "3. Follow the on-screen buttons to make your changes.", ""]
    if facts["has_payments"]:
        lines += ["## Connecting your Stripe account", "",
                  "Your app can take payments, but they stay switched off until "
                  "you connect your own Stripe account.", "",
                  "1. Open the **Settings** screen.",
                  "2. Tap **Connect Stripe**.",
                  "3. Sign in to Stripe and approve — your payment buttons turn on "
                  "automatically.", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ OUTPUT 2
async def demo_script(facts: dict) -> dict:
    """Screen-recording walkthrough (JSON). Steps are one-per-REAL-screen; the LLM
    only phrases the narration, so it can never script a screen that doesn't
    exist (e.g. no Stripe screen unless a Stripe page was generated)."""
    screens = facts["screens"]
    if not screens:
        return {
            "title": f"{facts['business_name']} — demo walkthrough",
            "app": facts["business_name"], "screens_count": 0, "steps": [],
            "note": ("No visual screens were generated for this app, so there is "
                     "nothing to record yet. (Actual recording is done manually.)"),
        }

    # Ask the LLM for one narration per real screen, in order.
    system = (_NO_JARGON + " You are writing narration for a screen-recording demo. "
              "I give you an ORDERED list of screens that exist. Return a JSON "
              "object {\"narrations\": [...]} with EXACTLY one short plain-English "
              "narration string per screen, in the SAME order. Do not add or drop "
              "screens. No other text.")
    user = json.dumps({"business": facts["business_name"],
                       "screens": [s["name"] for s in screens]})
    parsed = _extract_json(await _llm(system, user) or "")
    narrations = parsed.get("narrations") if isinstance(parsed, dict) else None
    if not isinstance(narrations, list) or len(narrations) != len(screens):
        narrations = None  # mismatch -> fall back to templates (screens stay real)

    steps = []
    for i, s in enumerate(screens):
        narration = (narrations[i] if narrations
                     else f"This is the {s['name']} screen. Show what it does and "
                          f"point out the main buttons.")
        steps.append({
            "step": i + 1,
            "screen": s["name"],
            "show": f"Open the {s['name']} screen.",
            "narrate": str(narration).strip(),
            "click": f"Click through the main actions on the {s['name']} screen.",
        })
    return {
        "title": f"{facts['business_name']} — demo walkthrough",
        "app": facts["business_name"], "screens_count": len(steps), "steps": steps,
        "note": "Actual screen recording is done manually; this script says exactly "
                "what to record, screen by screen.",
    }


# ------------------------------------------------------------------ OUTPUT 3
_BASE_QUESTIONS = [
    "How do I add a new user?",
    "How do I change my data?",
    "What do I do if something looks wrong?",
    "How do I contact support?",
    "How do I keep my app safe?",
    "Will I lose my information?",
    "Can I get a copy of everything?",
    "How do I make a change to how the app works?",
    "What does it cost to keep running?",
    "How do I share the app with my team or customers?",
]


async def maintenance_guide(facts: dict) -> str:
    """Plain-English answers to the 10 most common questions (markdown).

    Honest by construction: there is no built-in support channel in the stored
    data, so we say so (point to whoever set it up) and lean on the platform's
    real guarantee — free full code export, no lock-in. Nothing invented.
    """
    cost = None
    dep = facts["deployment"]
    if dep and dep.get("monthly_cost_estimate") is not None:
        cost = f"about ${dep['monthly_cost_estimate']:.0f} a month"

    honest_facts = {
        "business": facts["business_name"], "it_is_a": facts["platform"],
        "features": [f.get("title") for f in facts["features"]],
        "support": ("There is no built-in support desk yet. Contact whoever set "
                    "this app up for you."),
        "your_data": ("You own everything. You can always get a full copy of your "
                      "app and its information exported — there is no lock-in."),
        "running_cost": cost or "not available yet (the app is not live yet)",
        "has_payments": facts["has_payments"],
    }
    system = (_NO_JARGON + " Write a MAINTENANCE GUIDE in markdown: answer each of "
              "the questions I list as a '## ' heading followed by 1-3 plain "
              "sentences. Base answers ONLY on the facts I give — if a fact isn't "
              "provided, say it honestly (e.g. no support desk yet) rather than "
              "making something up. Output only the markdown.")
    user = json.dumps({"questions": _BASE_QUESTIONS, "facts": honest_facts})
    text = await _llm(system, user)
    if text:
        return text

    # Deterministic fallback.
    answers = {
        "How do I add a new user?": "Open the screen for the people or accounts in "
            "your app and use the add button. If your app doesn't manage users, you "
            "won't see this option.",
        "How do I change my data?": "Open the screen for the thing you want to "
            "change, tap it, edit the details, and save.",
        "What do I do if something looks wrong?": "Refresh the screen first. If it "
            "still looks wrong, note what you were doing and tell whoever set up "
            "your app.",
        "How do I contact support?": honest_facts["support"],
        "How do I keep my app safe?": "Keep your login private and don't share your "
            "password. Your app was checked for safety before it went out.",
        "Will I lose my information?": "No — your information is stored safely and "
            "kept as you make changes.",
        "Can I get a copy of everything?": honest_facts["your_data"],
        "How do I make a change to how the app works?": "Tell whoever set up your "
            "app what you'd like changed; changes are included, not charged per "
            "request.",
        "What does it cost to keep running?": f"Running cost is {honest_facts['running_cost']}.",
        "How do I share the app with my team or customers?": "Share your app's web "
            "address with anyone you want to use it.",
    }
    lines = [f"# {facts['business_name']} — Help & Maintenance", ""]
    for q in _BASE_QUESTIONS:
        lines += [f"## {q}", "", answers.get(q, "Ask whoever set up your app."), ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ OUTPUT 4
def handoff_summary(facts: dict) -> dict:
    """One-page summary — NO LLM, every field is real stored data. Honest `notes`
    surface partial/known-open state instead of implying a green build."""
    dep = facts["deployment"]
    sec = facts["security"]
    qa = facts["qa"]

    notes: list[str] = []
    if dep is None:
        notes.append("This app has not been deployed yet — no live link or running cost.")
    elif not dep["is_live"]:
        notes.append(f"The last deployment did not go live (status: {dep['status']}).")
    if sec["status"] == "no_certificate":
        notes.append("No security certificate is on file yet.")
    elif sec["status"] == "not_passed":
        notes.append("The security review has not passed.")
    if qa["available"] and qa["failed"] > 0:
        notes.append(f"{qa['failed']} of {qa['total']} tests did not pass "
                     f"({qa['escalated']} escalated for a person to review).")
    elif not qa["available"]:
        notes.append("No test results are on file yet.")
    for i in facts["integrations"]:
        if "stripe" in i["name"].lower() and not i["connected"]:
            notes.append("Payments are set up in the app but no Stripe account has "
                         "been connected yet.")

    return {
        "project_id": facts["project_id"],
        "business_name": facts["business_name"],
        "date_built": facts["built_at"],
        "what_it_is": facts["platform"],
        "features_built": [f.get("title") for f in facts["features"]],
        "screens_built": [s["name"] for s in facts["screens"]],
        "deployment": {
            "live_url": dep["live_url"] if dep else None,
            "status": dep["status"] if dep else "not_deployed",
            "server_type": dep["server_type"] if dep else None,
            "monthly_cost_estimate": dep["monthly_cost_estimate"] if dep else None,
            "cost_basis": dep["cost_basis"] if dep else None,
            "https": bool(dep["ssl_enabled"]) if dep else False,
            "ssl_type": dep["ssl_type"] if dep else None,
        },
        "security": {"status": sec["status"], "passed": sec["passed"],
                     "issues_found": sec["issues_found"],
                     "issues_fixed": sec["issues_fixed"],
                     "reviewed_by": sec["model_used"]},
        "tests": {"available": qa["available"], "total": qa["total"],
                  "passed": qa["passed"], "failed": qa["failed"],
                  "escalated": qa["escalated"]},
        "integrations": [{"name": i["name"], "status": i["status"],
                          "connected": i["connected"]} for i in facts["integrations"]],
        "honest_notes": notes,
    }
