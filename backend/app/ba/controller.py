"""Deterministic BA conversation controller.

Owns the locked question order and every stage transition. The LLM is
only ever used for phrasing/analysis elsewhere — the flow itself is
fully deterministic so we never ask two questions at once, never skip a
step, and never hallucinate the conversation.
"""
import asyncio
import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app import competitive_intel, llm
from app.ba import state as st
from app.ba import understanding
from app.models import DesignPreference, Project, Requirement
from app.redis_client import redis_client

logger = logging.getLogger("ba.controller")

MOBILE_KEYWORDS = ("mobile", "phone", "iphone", "android", "app store", "play store")

PLAN_OPTIONS = [
    {
        "id": "quick",
        "name": "Quick launch",
        "summary": "Just the core features to get you live fast",
        "time": "about 20 minutes",
        "price": "around $15/month",
    },
    {
        "id": "production",
        "name": "Production ready",
        "summary": "The full set of features, polished and ready for real customers",
        "time": "about 45 minutes",
        "price": "around $50/month",
    },
    {
        "id": "scale",
        "name": "Scale ready",
        "summary": "Everything, plus automatic scaling for lots of growth",
        "time": "about 90 minutes",
        "price": "around $150/month",
    },
]

VIBE_OPTIONS = [
    "Clean minimal",
    "Bold colorful",
    "Professional",
    "Warm friendly",
    "Luxury premium",
    "Fun energetic",
]

# Fields the user can jump back and edit from the confirmation summary.
EDIT_FIELDS = [
    ("What we're building", st.ASK_BUILD),
    ("Business name", st.ASK_BUSINESS_NAME),
    ("Location", st.ASK_LOCATION),
    ("Who it's for", st.ASK_AUDIENCE),
    ("Expected users", st.ASK_USER_COUNT),
    ("Budget", st.ASK_BUDGET),
    ("Timing", st.ASK_TIMELINE),
    ("Growth plans", st.ASK_GROWTH),
    ("Plan", st.PRESENT_PLAN),
    ("Design feel", st.ASK_DESIGN_VIBE),
    ("Brand color", st.ASK_DESIGN_COLOR),
]


def parse_edit_target(message: str) -> str | None:
    low = message.strip().lower()
    for label, stage in EDIT_FIELDS:
        ll = label.lower()
        if ll in low or low in ll:
            return stage
    return None


MOBILE_OPTIONS = [
    {
        "id": "native",
        "title": "A phone app you download",
        "detail": "Lives in the app stores. Needs a developer account and the stores take a few days to approve it.",
    },
    {
        "id": "web",
        "title": "An app that works in any phone's browser",
        "detail": "Works on every phone, can be live in minutes, and there's no app store waiting.",
    },
    {
        "id": "both",
        "title": "Both",
        "detail": "Start with the browser version now so you're live quickly, and add the downloadable app later.",
    },
]


def detect_mobile(message: str) -> bool:
    low = message.lower()
    return any(k in low for k in MOBILE_KEYWORDS)


# --- Competitive intelligence caching (overlaps with the user typing) -----
def _ci_key(project_id: int) -> str:
    return f"ba:ci:{project_id}"


async def conversational_redirect(message: str) -> str:
    """When the user greets or makes small talk instead of giving an idea,
    reply warmly and human — greet back, then gently invite their idea."""
    reply = await llm.chat(
        "You are a warm, friendly guide helping a non-technical person start "
        "building an app or website. They haven't described their idea yet — "
        "they may be greeting you, making small talk, or unsure. Reply in 1-2 "
        "short, natural sentences: if they greeted you, greet back warmly and "
        "answer briefly, then gently invite them to share what they'd like to "
        "build. Sound human and friendly, never robotic. No technical words. "
        "NEVER assume or suggest whether they want an app or a website — do not "
        "pick one for them; if you mention it, say 'app or website'.",
        message,
        temperature=0.7,
    )
    return reply or (
        "No worries if it's rough — just tell me in a sentence what you'd like "
        "to build. For example: 'an online store for my bakery'."
    )


async def summarize_idea(build: str) -> str:
    """A short, clean paraphrase of the idea for acknowledgements — so we
    never echo the user's whole sentence back at them."""
    result = await llm.chat(
        "Summarize the user's idea as a short noun phrase, at most 8 words, "
        "plain English, with no trailing punctuation. Stay faithful to what "
        "they said — do NOT invent a format like 'app' or 'website' if they "
        "didn't mention one.",
        build,
        temperature=0.0,
    )
    if result:
        return result.strip().strip('"').rstrip(".")
    return " ".join(build.split()[:8])


async def _derive_business_category(build: str, business_name: str | None) -> str:
    """Turn the free-text idea into a short business category (e.g.
    'coffee shop') so the competitor search finds *competitors*, not the
    user's own business or the whole sentence."""
    result = await llm.chat(
        "You identify the type of local business from a short description. "
        "Reply with ONLY the business type in 1-3 words, lowercase. Examples: "
        "'coffee shop', 'car repair shop', 'barbershop', 'dental clinic', "
        "'gym'. Only reply 'business' if you genuinely cannot tell.",
        f"Business name: {business_name or 'n/a'}. Idea: {build}",
        temperature=0.0,
    )
    if result:
        category = result.strip().strip('.').strip('"').lower()
        if 0 < len(category) <= 40:
            return category
    # Fallback when no LLM is configured: best-effort, never the raw sentence.
    return (business_name or "local business").lower()


async def start_ci(state: st.BAState) -> None:
    """Kick off competitive intelligence in the background while the user
    answers the growth question."""
    category = state.fields.get("business_type")
    if not category:
        category = await _derive_business_category(
            state.fields.get("build", ""), state.fields.get("business_name")
        )
        state.fields["business_type"] = category
    city = state.fields.get("city", "")
    region = state.fields.get("state", "")
    if await redis_client.get(_ci_key(state.project_id)):
        return  # already running / done

    async def _run():
        try:
            result = await competitive_intel.run(category, city, region)
            await redis_client.set(
                _ci_key(state.project_id), json.dumps(result), ex=24 * 3600
            )
        except Exception:  # pragma: no cover
            logger.exception("CI background run failed")

    asyncio.create_task(_run())


async def ci_ready(project_id: int) -> bool:
    return bool(await redis_client.get(_ci_key(project_id)))


async def get_ci(project_id: int, business_type: str, city: str, region: str) -> dict:
    """Return CI findings, waiting briefly for the background run, then
    computing inline as a fallback."""
    for _ in range(20):  # up to ~10s
        raw = await redis_client.get(_ci_key(project_id))
        if raw:
            return json.loads(raw)
        await asyncio.sleep(0.5)
    result = await competitive_intel.run(business_type, city, region)
    await redis_client.set(_ci_key(project_id), json.dumps(result), ex=24 * 3600)
    return result


# --- Ingesting the user's answer for the current stage --------------------
_SKIP_WORDS = {"no", "not yet", "none", "nope", "skip", "n/a"}

# Phrases that mean "I don't have a business name yet".
_NO_NAME_HINTS = ("don't", "dont", "do not", "no name", "not yet", "notyet",
                  "none", "nope", "haven't", "havent", "without",
                  "no business name", "nothing")


def _is_no_name(msg: str) -> bool:
    low = msg.strip().lower()
    if low in _SKIP_WORDS:
        return True
    return any(h in low for h in _NO_NAME_HINTS)


def ingest(state: st.BAState, message: str) -> None:
    stage = state.stage
    msg = message.strip()
    f = state.fields

    if stage == st.ASK_BUILD:
        f["build"] = msg
    elif stage == st.ASK_BUSINESS_NAME:
        f["business_name"] = None if _is_no_name(msg) else msg
    elif stage == st.ASK_LOCATION:
        f["location"] = msg
        if "," in msg:
            city, region = msg.split(",", 1)
            f["city"], f["state"] = city.strip(), region.strip()
        else:
            f["city"], f["state"] = msg, ""
    elif stage == st.ASK_AUDIENCE:
        f["audience"] = msg
    elif stage == st.ASK_MENU:
        f["menu_setup"] = _parse_menu_setup(msg)
    elif stage == st.ASK_USER_COUNT:
        f["user_count"] = msg
    elif stage == st.ASK_BUDGET:
        f["budget"] = msg
    elif stage == st.ASK_TIMELINE:
        f["timeline"] = msg
    elif stage == st.ASK_GROWTH:
        f["growth"] = msg
    elif stage == st.PRESENT_CI:
        f["selected_ci"] = _parse_ci_selection(msg, state.ci)
    elif stage == st.PRESENT_PLAN:
        f["plan"] = _parse_plan(msg)
    elif stage == st.ASK_DESIGN_VIBE:
        f["style_vibe"] = msg
    elif stage == st.ASK_DESIGN_REFS:
        f["reference_sites"] = None if msg.lower() in _SKIP_WORDS else msg
    elif stage == st.ASK_DESIGN_COLOR:
        f["brand_color"] = msg
    elif stage == st.ASK_PLATFORM:
        f["platform"], f["mobile_choice"] = _parse_platform(msg)
    elif stage == st.MOBILE_CHOICE:
        f["mobile_choice"] = _parse_mobile(msg)


def _parse_ci_selection(msg: str, ci: dict | None) -> list[str]:
    if msg.lower() in _SKIP_WORDS:
        return []
    findings = (ci or {}).get("findings", [])
    selected: list[str] = []
    # Accept "1,3" style index selection.
    for token in msg.replace(" ", "").split(","):
        if token.isdigit():
            i = int(token) - 1
            if 0 <= i < len(findings):
                selected.append(findings[i]["suggestion"])
    if not selected and msg.lower() not in _SKIP_WORDS:
        # Fall back to treating the message as a free-text wish.
        selected.append(msg)
    return selected


def _parse_menu_setup(msg: str) -> str:
    """"pdf" if they want to upload a menu PDF, else "manual" (type items in)."""
    low = msg.lower()
    return "pdf" if ("pdf" in low or "upload" in low or "file" in low) else "manual"


def _parse_plan(msg: str) -> str:
    low = msg.lower()
    if "quick" in low or "1" in low:
        return "quick"
    if "scale" in low or "3" in low:
        return "scale"
    return "production"


_PLAN_COSTS = {"quick": 15, "production": 50, "scale": 150}


def _budget_number(budget: str) -> int | None:
    m = re.search(r"(\d+(?:\.\d+)?)", (budget or "").replace(",", ""))
    return int(float(m.group(1))) if m else None


def _recommended_plan_id(budget: str) -> str | None:
    """The best plan that fits the stated budget (cheapest if none fit)."""
    b = _budget_number(budget)
    if b is None:
        return None
    affordable = [pid for pid, c in _PLAN_COSTS.items() if c <= b]
    return max(affordable, key=lambda p: _PLAN_COSTS[p]) if affordable else "quick"


def next_applicable(state: st.BAState) -> str:
    """Advance to the next stage that actually applies to this idea, skipping
    ones that don't (e.g. 'how many users' for a single-user tool)."""
    stage = st.next_stage(state.stage)
    while stage != st.DONE and _should_skip(stage, state):
        if stage == st.ASK_USER_COUNT:
            state.fields.setdefault("user_count", "1")
        stage = st.next_stage(stage)
    return stage


def _needs_market_research(f: dict) -> bool:
    """Competitor research (and thus the location question) only makes sense
    for a LOCAL business that serves CUSTOMERS — not an internal/staff tool
    (even at a local business) and not a global app."""
    return bool(f.get("is_local", False) and f.get("customer_facing", True))


def _should_skip(stage: str, state: st.BAState) -> bool:
    f = state.fields
    if stage == st.ASK_PLATFORM and f.get("mobile_choice"):
        return True  # platform already known from the idea
    if stage == st.ASK_LOCATION and not _needs_market_research(f):
        return True
    if stage == st.ASK_MENU and not f.get("is_food", False):
        return True  # menu setup only matters for food/restaurant businesses
    if stage == st.ASK_USER_COUNT and understanding.is_single_user(f):
        return True
    if stage == st.PRESENT_CI and not _needs_market_research(f):
        return True
    return False


def _parse_platform(msg: str) -> tuple[str, str]:
    """Return (platform, mobile_choice) from the platform question answer."""
    low = msg.lower()
    if "both" in low or low.strip() == "3":
        return "both", "both"
    if "phone" in low or "app" in low or low.strip() == "2":
        return "app", "native"
    return "website", "web"


def _parse_mobile(msg: str) -> str:
    low = msg.lower()
    if "native" in low or "download" in low or "1" == low.strip():
        return "native"
    if "both" in low or "3" == low.strip():
        return "both"
    return "web"


# --- Composing the BA message for the current stage -----------------------
def _ack(state: st.BAState) -> str:
    """A short, deterministic acknowledgement that references what was just
    said — proves we remember without an LLM."""
    f = state.fields
    stage = state.stage
    if stage == st.ASK_BUSINESS_NAME and f.get("build"):
        idea = f.get("build_summary") or "your idea"
        return f"Love it — {idea}. "
    if stage == st.ASK_LOCATION and f.get("business_name"):
        return f"Great, {f['business_name']}. "
    if stage == st.ASK_AUDIENCE and f.get("city"):
        return f"Got it, based in {f['city']}. "
    return ""


async def compose(state: st.BAState) -> dict:
    stage = state.stage
    f = state.fields

    if stage == st.ASK_BUILD:
        return _text(
            "Hi! I'm here to help bring your idea to life. "
            "To start — what would you like to build?"
        )
    if stage == st.ASK_PLATFORM:
        return _choices(
            _ack(state) + "Would you like this as a website, a phone app, or both?",
            ["A website", "A phone app", "Both"],
        )
    if stage == st.ASK_BUSINESS_NAME:
        return _text(_ack(state) + "Does your business have a name yet? "
                     "If not, just say 'not yet'.")
    if stage == st.ASK_LOCATION:
        return _text(_ack(state) + "Which city and state are you in? "
                     "(For example: Austin, Texas)")
    if stage == st.ASK_AUDIENCE:
        return _choices(
            _ack(state) + "Who's going to use this — just you, or other people too?",
            ["Just me", "Other people too"],
        )
    if stage == st.ASK_MENU:
        return _choices(
            _ack(state) + "Would you like to type in your menu items yourself, "
            "or upload a PDF of your menu and we'll pull the items out for you?",
            ["Type them in myself", "Upload a PDF"],
        )
    if stage == st.ASK_USER_COUNT:
        return _text("Roughly how many people do you expect to use it?")
    if stage == st.ASK_BUDGET:
        return _text("What's a rough monthly amount you'd be comfortable spending?")
    if stage == st.ASK_TIMELINE:
        return _choices(
            "How's your timing on this?",
            ["I need it urgently", "I'm relaxed about timing"],
        )
    if stage == st.ASK_GROWTH:
        # Only research the market for local businesses — a global app or an
        # internal tool has no nearby competitors to compare against.
        researching = _needs_market_research(f)
        if researching:
            await start_ci(state)
        return {
            **_text("Last quick question — do you have any plans to grow "
                    "this down the road?"),
            "researching": researching,
        }
    if stage == st.PRESENT_CI:
        category = state.fields.get("business_type") or "businesses like yours"
        city = state.fields.get("city", "you")
        ci = await get_ci(
            state.project_id, category, city, state.fields.get("state", "")
        )
        state.ci = ci
        findings = ci.get("findings", [])[:5]
        intro = (
            f"Before we start building — I looked at what customers are saying "
            f"about {category}s near {city}."
            if not category.endswith("s")
            else f"Before we start building — I looked at what customers are "
            f"saying about {category} near {city}."
        )
        return {
            "reply": intro + " Here's what keeps coming up, and how we could "
            "turn each one into an advantage for you:",
            "ui": {
                "kind": "ci_findings",
                "findings": [
                    {
                        "index": i + 1,
                        "theme": x["theme"],
                        "count": x["count"],
                        "suggestion": x["suggestion"],
                    }
                    for i, x in enumerate(findings)
                ],
                # Real places we looked at — names + map links, shown for trust
                # and kept separate from the anonymized complaint themes above.
                "sources": ci.get("sources", []),
                "attribution": ci.get("attribution"),
                "prompt": "Want me to add features that solve these? Pick any that "
                "sound good (or say 'none').",
            },
        }
    if stage == st.PRESENT_PLAN:
        selected = state.fields.get("selected_ci") or []
        ack = ""
        if selected:
            n = len(selected)
            ack = f"Great — I'll add {'that' if n == 1 else f'those {n}'} " \
                  f"advantage{'' if n == 1 else 's'} to your build. "

        # Budget-aware: recommend the plan that fits what they told us, and
        # mark pricier ones so we never dangle an over-budget option silently.
        budget = f.get("budget", "")
        rec_id = _recommended_plan_id(budget)
        budget_num = _budget_number(budget)
        intro = "Here are three ways we can build this — which feels right?"
        plans = PLAN_OPTIONS
        if rec_id:
            rec_name = next(p["name"] for p in PLAN_OPTIONS if p["id"] == rec_id)
            intro = (
                f"You mentioned about {budget}, so **{rec_name}** fits your "
                f"budget best. Here are all three — the pricier ones do more, "
                f"but it's your call:"
            )
            plans = [
                {
                    **p,
                    "recommended": p["id"] == rec_id,
                    "over_budget": budget_num is not None
                    and _PLAN_COSTS[p["id"]] > budget_num,
                }
                for p in PLAN_OPTIONS
            ]
        return {
            "reply": ack + intro,
            "ui": {"kind": "plan_options", "plans": plans},
        }
    if stage == st.ASK_DESIGN_VIBE:
        return {
            "reply": "Now the fun part — how do you want your app to feel?",
            "ui": {"kind": "design_vibe", "options": VIBE_OPTIONS},
        }
    if stage == st.ASK_DESIGN_REFS:
        return _text("Are there any apps or websites whose design you love? "
                     "Even one example helps a lot. (Or say 'none'.)")
    if stage == st.ASK_DESIGN_COLOR:
        return _text("Do you have a brand color? Tell me the color — or I can "
                     "pick one that fits your style.")
    if stage == st.CONFIRM:
        return {
            "reply": _summary(state),
            "ui": {"kind": "summary", "confirm_label": "Yes, this is right"},
        }
    if stage == st.BLOCKED:
        return {
            "reply": "I'm really sorry, but that's not something I'm able to help "
            "build. I can help with all sorts of legitimate apps and websites, "
            "though — feel free to start over with a different idea whenever "
            "you're ready.",
            "ui": {"kind": "blocked"},
        }
    if stage == st.EDIT_SELECT:
        return {
            "reply": "No problem — what would you like to change?",
            "ui": {"kind": "choices", "options": [label for label, _ in EDIT_FIELDS]},
        }
    if stage == st.MOBILE_CHOICE:
        return {
            "reply": "It sounds like you'd like people to use this on their "
            "phones. There are a few ways to do that — which sounds best to you?",
            "ui": {"kind": "mobile_options", "options": MOBILE_OPTIONS},
        }
    if stage == st.DONE:
        return {
            "reply": "Perfect — everything's locked in and your idea is ready "
            "for the team to start building. I'll take it from here!",
            "ui": {"kind": "done"},
        }
    return _text("")


def _text(reply: str) -> dict:
    return {"reply": reply, "ui": {"kind": "text"}}


def _choices(reply: str, options: list[str]) -> dict:
    return {"reply": reply, "ui": {"kind": "choices", "options": options}}


def _summary(state: st.BAState) -> str:
    f = state.fields
    plan = next((p for p in PLAN_OPTIONS if p["id"] == f.get("plan")), PLAN_OPTIONS[1])
    lines = ["Here's everything I've got — please check it over:", ""]
    lines.append(f"• What we're building: {f.get('build', '—')}")
    if f.get("business_name"):
        lines.append(f"• Business name: {f['business_name']}")
    if f.get("location"):
        lines.append(f"• Location: {f['location']}")
    lines.append(f"• Who it's for: {f.get('audience', '—')}")
    if f.get("is_food") and f.get("menu_setup"):
        lines.append(
            "• Your menu: "
            + ("upload a PDF and we'll pull the items out (you review before "
               "anything goes live)" if f["menu_setup"] == "pdf"
               else "you'll type in your menu items")
        )
    lines.append(f"• Expected users: {f.get('user_count', '—')}")
    lines.append(f"• Monthly budget: {f.get('budget', '—')}")
    lines.append(f"• Timing: {f.get('timeline', '—')}")
    lines.append(f"• Growth plans: {f.get('growth', '—')}")
    if f.get("mobile_choice"):
        choice_map = {"native": "A downloadable phone app",
                      "web": "A website (works in any browser)",
                      "both": "A website now, downloadable app later"}
        lines.append(f"• Platform: {choice_map.get(f['mobile_choice'])}")
    if f.get("selected_ci"):
        lines.append("• Extra advantages over competitors:")
        for s in f["selected_ci"]:
            lines.append(f"   – {s}")
    lines.append(f"• Plan: {plan['name']} ({plan['price']}, {plan['time']})")
    lines.append("• Design:")
    lines.append(f"   – Feel: {f.get('style_vibe', '—')}")
    if f.get("reference_sites"):
        lines.append(f"   – Inspiration: {f['reference_sites']}")
    lines.append(f"   – Color: {f.get('brand_color', '—')}")
    lines.append("")
    lines.append("Is everything right? Once you confirm, I'll lock it in.")
    return "\n".join(lines)


# --- Persistence on confirmation ------------------------------------------
def build_summary_dict(state: st.BAState) -> dict:
    """Assemble the full confirmed summary — the Architect's input."""
    f = state.fields
    plan = next((p for p in PLAN_OPTIONS if p["id"] == f.get("plan")), PLAN_OPTIONS[1])
    return {
        "build": f.get("build", ""),
        "business_name": f.get("business_name"),
        "business_type": f.get("business_type"),
        "location": f.get("location"),
        "city": f.get("city"),
        "state": f.get("state"),
        "audience": f.get("audience", ""),
        "user_count": f.get("user_count", ""),
        "budget": f.get("budget", ""),
        "timeline": f.get("timeline", ""),
        "growth": f.get("growth", ""),
        "mobile_choice": f.get("mobile_choice"),
        "platform": f.get("platform"),
        "customer_facing": f.get("customer_facing", True),
        "is_local": f.get("is_local", False),
        "is_food": f.get("is_food", False),
        "menu_setup": f.get("menu_setup"),
        "app_kind": f.get("app_kind"),
        "plan": {"id": plan["id"], "name": plan["name"]},
        "competitor_features": f.get("selected_ci", []),
        "design": {
            "style_vibe": f.get("style_vibe"),
            "reference_sites": f.get("reference_sites"),
            "brand_color": f.get("brand_color"),
        },
    }


async def persist_on_confirm(db: AsyncSession, state: st.BAState) -> None:
    """Write the confirmed requirements and design preferences, locking them."""
    f = state.fields
    project = await db.get(Project, state.project_id)
    if project is not None:
        project.status = "requirements_confirmed"
        if f.get("build"):
            project.prompt = f["build"]
        # Store the full summary as JSON for the Architect to read.
        project.summary_json = json.dumps(build_summary_dict(state))

    def add_req(text: str, source: str):
        db.add(
            Requirement(
                project_id=state.project_id,
                requirement=text,
                source=source,
                is_locked=True,
            )
        )

    add_req(f"What to build: {f.get('build', '')}", "user_stated")
    if f.get("business_name"):
        add_req(f"Business name: {f['business_name']}", "user_stated")
    if f.get("location"):
        add_req(f"Location: {f['location']}", "user_stated")
    add_req(f"Audience: {f.get('audience', '')}", "user_stated")
    add_req(f"Expected users: {f.get('user_count', '')}", "user_stated")
    add_req(f"Monthly budget: {f.get('budget', '')}", "user_stated")
    add_req(f"Timeline: {f.get('timeline', '')}", "user_stated")
    add_req(f"Growth plans: {f.get('growth', '')}", "user_stated")
    if f.get("mobile_choice"):
        add_req(f"Phone experience: {f['mobile_choice']}", "user_stated")
    if f.get("is_food") and f.get("menu_setup"):
        _menu_label = (
            "upload a PDF menu and have items extracted (with a review step)"
            if f["menu_setup"] == "pdf"
            else "add menu items manually"
        )
        add_req(f"Menu setup: {_menu_label}", "user_stated")

    for suggestion in f.get("selected_ci", []):
        add_req(suggestion, "competitor_insight")

    plan = next((p for p in PLAN_OPTIONS if p["id"] == f.get("plan")), PLAN_OPTIONS[1])
    add_req(f"Plan tier: {plan['name']} — {plan['summary']}", "platform_suggested")

    db.add(
        DesignPreference(
            project_id=state.project_id,
            style_vibe=f.get("style_vibe"),
            reference_sites=f.get("reference_sites"),
            brand_color=f.get("brand_color"),
        )
    )
    await db.commit()
