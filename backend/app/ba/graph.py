"""LangGraph graph that processes a single conversation turn.

The graph wires three deterministic steps — ingest the answer, advance
the stage, compose the next message — with a conditional edge that lets
a mobile-detection interrupt skip the advance step. State transitions
stay fully under the controller's control; LangGraph orchestrates the
per-turn flow.
"""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.ba import controller, safety, understanding, validation
from app.ba import state as st


class TurnState(TypedDict, total=False):
    state: st.BAState
    message: str | None
    is_first: bool
    interrupt: bool
    skip_advance: bool
    reask: bool
    nudge: str | None
    editing: bool
    output: dict[str, Any]


_NEGATIVE = {"no", "nope", "not right", "wrong", "change", "incorrect"}

# Free-text stages whose answers get safety-screened. Button/quick-choice
# stages are excluded — their values come from a fixed option set.
_SCREENED_STAGES = {
    st.ASK_BUILD,
    st.ASK_BUSINESS_NAME,
    st.ASK_LOCATION,
    st.ASK_USER_COUNT,
    st.ASK_BUDGET,
    st.ASK_GROWTH,
    st.ASK_DESIGN_REFS,
    st.ASK_DESIGN_COLOR,
}


def _block(state: st.BAState, turn: TurnState, category: str | None) -> TurnState:
    state.fields["block_category"] = category
    state.stage = st.BLOCKED
    turn["skip_advance"] = True
    return turn


async def _ingest(turn: TurnState) -> TurnState:
    state = turn["state"]
    message = turn.get("message")
    turn["interrupt"] = False
    turn["skip_advance"] = False
    turn["reask"] = False
    turn["nudge"] = None
    turn["editing"] = False

    if turn.get("is_first") or message is None:
        # First turn — just compose the opening question.
        turn["skip_advance"] = True
        return turn

    # Blocked is terminal — keep showing the refusal, never advance.
    if state.stage == st.BLOCKED:
        turn["skip_advance"] = True
        return turn

    # Resuming from a mobile interrupt: record the choice and jump back.
    if state.stage == st.MOBILE_CHOICE:
        controller.ingest(state, message)
        state.stage = state.resume_stage or st.ASK_BUILD
        state.resume_stage = None
        turn["skip_advance"] = True
        return turn

    # Edit menu: jump to the chosen field, then return to the summary.
    if state.stage == st.EDIT_SELECT:
        target = controller.parse_edit_target(message)
        if target is None:
            turn["skip_advance"] = True  # unclear pick — re-show the menu
            return turn
        state.fields["_return_to_confirm"] = True
        state.stage = target
        turn["skip_advance"] = True
        turn["editing"] = True
        return turn

    # Safety guardrail runs FIRST on every free-text answer — a disallowed
    # request is blocked outright, before any clarity re-ask could give it
    # another pass. Users can try to sneak it in anywhere, not just the idea.
    if state.stage in _SCREENED_STAGES:
        # The idea itself is screened alone; later answers are screened with
        # the idea as context so benign fragments aren't judged in isolation.
        context = None if state.stage == st.ASK_BUILD else state.fields.get("build")
        allowed, category, _reason = await safety.screen(message, context=context)
        if not allowed:
            return _block(state, turn, category)

    # Sanity-check the answer; re-ask (up to a cap) if it's vague/gibberish.
    ok, nudge = await validation.check(state.stage, message)
    if not ok:
        tries = state.fields.setdefault("_tries", {})
        count = tries.get(state.stage, 0) + 1
        tries[state.stage] = count
        if count < validation.MAX_TRIES:
            # At the idea stage, respond like a person — greet back / redirect
            # naturally instead of repeating a canned nudge.
            if state.stage == st.ASK_BUILD:
                nudge = await controller.conversational_redirect(message)
            turn["reask"] = True
            turn["nudge"] = nudge
            turn["skip_advance"] = True
            return turn
        # Cap reached — accept gracefully so the user is never trapped.
        tries[state.stage] = 0
    elif state.fields.get("_tries"):
        state.fields["_tries"].pop(state.stage, None)

    controller.ingest(state, message)

    # LLM understanding layer — give the deterministic flow real meaning.
    if state.stage == st.ASK_BUILD:
        state.fields["build_summary"] = await controller.summarize_idea(message)
        info = await understanding.classify(message)
        state.fields["customer_facing"] = info["customer_facing"]
        state.fields["platform"] = info["platform"]
        state.fields["app_kind"] = info["kind"]
        state.fields["is_local"] = info["is_local"]
        state.fields["is_food"] = info["is_food"]
        # If the idea already made the platform clear, skip asking it.
        if info["platform"] in ("website", "app", "both"):
            state.fields["mobile_choice"] = {
                "website": "web", "app": "native", "both": "both"
            }[info["platform"]]
    elif state.stage == st.ASK_BUSINESS_NAME:
        state.fields["business_name"] = await understanding.extract_name(message)
    elif state.stage == st.ASK_USER_COUNT:
        state.fields["user_count"] = await understanding.normalize_users(message)

    # Mobile detection can fire on any answer — interrupt once.
    if "mobile_choice" not in state.fields and controller.detect_mobile(message):
        state.resume_stage = controller.next_applicable(state)
        state.stage = st.MOBILE_CHOICE
        turn["interrupt"] = True
    return turn


def _route_after_ingest(turn: TurnState) -> str:
    if turn.get("interrupt") or turn.get("skip_advance"):
        return "compose"
    return "advance"


async def _advance(turn: TurnState) -> TurnState:
    state = turn["state"]

    # Just finished editing a single field — go straight back to the summary.
    if state.fields.pop("_return_to_confirm", False):
        state.stage = st.CONFIRM
        return turn

    # Confirmation gate: agree -> done; "change something" -> edit menu.
    if state.stage == st.CONFIRM:
        msg = (turn.get("message") or "").strip().lower()
        if any(neg in msg for neg in _NEGATIVE):
            state.stage = st.EDIT_SELECT
            return turn
        # Final safety re-screen of the whole confirmed idea before locking.
        allowed, category, _reason = await safety.screen_summary(state.fields)
        if not allowed:
            return _block(state, turn, category)
        state.fields["confirmed"] = True
        state.stage = st.DONE
        return turn

    state.stage = controller.next_applicable(state)
    return turn


async def _compose(turn: TurnState) -> TurnState:
    out = await controller.compose(turn["state"])
    if turn.get("reask") and turn.get("nudge"):
        # Replace the question with the friendly nudge (keeps any buttons).
        out = {**out, "reply": turn["nudge"]}
    elif turn.get("editing"):
        out = {**out, "reply": "Sure — let's update that. " + out["reply"]}
    turn["output"] = out
    return turn


def _build():
    g = StateGraph(TurnState)
    g.add_node("ingest", _ingest)
    g.add_node("advance", _advance)
    g.add_node("compose", _compose)
    g.add_edge(START, "ingest")
    g.add_conditional_edges(
        "ingest", _route_after_ingest, {"advance": "advance", "compose": "compose"}
    )
    g.add_edge("advance", "compose")
    g.add_edge("compose", END)
    return g.compile()


_GRAPH = _build()


async def process_turn(
    state: st.BAState, message: str | None, is_first: bool = False
) -> dict[str, Any]:
    result = await _GRAPH.ainvoke(
        {"state": state, "message": message, "is_first": is_first}
    )
    return result["output"]
