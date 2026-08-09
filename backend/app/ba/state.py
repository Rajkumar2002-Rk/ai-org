"""BA conversation state, persisted in Redis while a project is in progress.

The projects table is intentionally locked to four columns, so all the
in-flight answers the BA agent collects live here until the user confirms
and they are written into the requirements / design_preferences tables.
"""
import json
from dataclasses import asdict, dataclass, field

from app.redis_client import redis_client

# --- Ordered conversation stages (the deterministic controller) ----------
ASK_BUILD = "ask_build"
ASK_PLATFORM = "ask_platform"
ASK_BUSINESS_NAME = "ask_business_name"
ASK_LOCATION = "ask_location"
ASK_AUDIENCE = "ask_audience"
ASK_MENU = "ask_menu"  # food businesses only: type-in vs upload-a-PDF menu
ASK_USER_COUNT = "ask_user_count"
ASK_BUDGET = "ask_budget"
ASK_TIMELINE = "ask_timeline"
ASK_GROWTH = "ask_growth"
PRESENT_CI = "present_ci"
PRESENT_PLAN = "present_plan"
ASK_DESIGN_VIBE = "ask_design_vibe"
ASK_DESIGN_REFS = "ask_design_refs"
ASK_DESIGN_COLOR = "ask_design_color"
CONFIRM = "confirm"
DONE = "done"

# Special stages (not part of the linear order).
MOBILE_CHOICE = "mobile_choice"
EDIT_SELECT = "edit_select"  # "what would you like to change?" menu
BLOCKED = "blocked"  # idea rejected by the safety guardrail (terminal)

ORDER = [
    ASK_BUILD,
    ASK_PLATFORM,
    ASK_BUSINESS_NAME,
    ASK_LOCATION,
    ASK_AUDIENCE,
    ASK_MENU,
    ASK_USER_COUNT,
    ASK_BUDGET,
    ASK_TIMELINE,
    ASK_GROWTH,
    PRESENT_CI,
    PRESENT_PLAN,
    ASK_DESIGN_VIBE,
    ASK_DESIGN_REFS,
    ASK_DESIGN_COLOR,
    CONFIRM,
    DONE,
]


def next_stage(stage: str) -> str:
    idx = ORDER.index(stage)
    return ORDER[min(idx + 1, len(ORDER) - 1)]


@dataclass
class BAState:
    project_id: int
    stage: str = ASK_BUILD
    fields: dict = field(default_factory=dict)
    ci: dict | None = None  # competitive intelligence findings
    # When a mobile interrupt fires we remember where to resume.
    resume_stage: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "BAState":
        return cls(**json.loads(raw))


def _key(project_id: int) -> str:
    return f"ba:state:{project_id}"


async def load(project_id: int) -> BAState | None:
    raw = await redis_client.get(_key(project_id))
    return BAState.from_json(raw) if raw else None


async def save(state: BAState) -> None:
    # Keep in-progress conversations for 7 days.
    await redis_client.set(_key(state.project_id), state.to_json(), ex=7 * 24 * 3600)
