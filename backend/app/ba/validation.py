"""Answer sanity-checking for the BA conversation.

Free-text answers to the key questions are checked for being clear and
on-topic. Vague / non-committal / gibberish answers ("I don't know",
"Ну?", "asdf") trigger a gentle re-ask. A hard try cap means a user who
genuinely can't answer is never trapped forever.
"""
from app import llm
from app.ba import state as st

# Re-ask up to this many times, then accept whatever they gave so the
# conversation can never get stuck in a loop.
MAX_TRIES = 3

_NUMBER_WORDS = ("hundred", "thousand", "million", "billion", "dozen", "few",
                 "couple", "many", "lot", "several", "k ", "k.")


def _has_digit(text: str) -> bool:
    return any(c.isdigit() for c in text)

# Obvious non-answers we reject without spending an LLM call.
_NONCOMMITTAL = {
    "", "?", "??", "idk", "i don't know", "i dont know", "dont know",
    "don't know", "dunno", "not sure", "no idea", "maybe", "whatever",
    "na", "n/a", "ну", "ну?", "huh", "hmm", "asdf", "test",
}

# Stages that get validated, with a hint describing a usable answer.
# Quick-choice stages (audience, timeline, vibe, plan) are intentionally
# excluded — their answers come from buttons and shouldn't be second-guessed.
_HINTS = {
    st.ASK_BUILD: "any mention of a business, product, or app/website type they "
    "want to build — even a brief one like 'a coffee shop' or 'a gym app' is "
    "enough. Only unclear if it's a greeting, small talk, a question back to "
    "you, or gibberish with no idea at all",
    st.ASK_BUSINESS_NAME: "a business name, OR a clear statement that they don't have one yet",
    st.ASK_LOCATION: "a city and/or state or region",
    st.ASK_USER_COUNT: "a rough number or range of expected users",
    st.ASK_BUDGET: "a rough monthly amount of money",
    st.ASK_GROWTH: "any answer about future plans, including clearly having no plans",
}

_DEFAULT_NUDGES = {
    st.ASK_BUILD: "No worries if it's rough — just tell me in a sentence what you'd like to build. For example: 'an online store for my bakery'.",
    st.ASK_BUSINESS_NAME: "That's okay — do you have a business name? If you don't have one yet, just say 'not yet'.",
    st.ASK_LOCATION: "Could you tell me the city and state you're in? For example: 'Austin, Texas'.",
    st.ASK_AUDIENCE: "Just so I get it right — will this be used by just you, or by other people too?",
    st.ASK_USER_COUNT: "A rough guess is fine — about how many people do you expect? For example: 'a few hundred'.",
    st.ASK_BUDGET: "Roughly what monthly amount feels comfortable? Even a ballpark like '$20 a month' helps.",
    st.ASK_GROWTH: "No problem — do you think you'll want to grow this later, or are you happy keeping it small for now?",
}

_SYS = (
    "You judge whether a user's answer is a clear, on-topic, usable response "
    "to a question, or whether it is vague, gibberish, or non-committal. "
    "Accept brief but on-topic answers (a business type, a product, a city). "
    "Only mark it unclear if it is a greeting, small talk, a question back to "
    "you, empty, or gibberish with no real answer. When in doubt, accept. "
    'Return JSON {"clear": true|false, "nudge": "a short, friendly, one-sentence '
    're-ask in plain English with no technical words, optionally with an example"}.'
)


async def check(stage: str, message: str) -> tuple[bool, str | None]:
    """Return (is_clear, nudge). nudge is None when the answer is fine."""
    if stage not in _HINTS:
        return True, None

    answer = message.strip()
    low = answer.lower().rstrip("?. ")

    # Business name is optional — a clear "I don't have one yet" is a fine
    # answer and should never be re-asked.
    if stage == st.ASK_BUSINESS_NAME and any(
        h in low for h in ("don't", "dont", "do not", "no name", "not yet",
                           "notyet", "none", "nope", "haven't", "havent",
                           "without", "nothing")
    ):
        return True, None

    if len(low) < 2 or low in _NONCOMMITTAL:
        return False, _DEFAULT_NUDGES[stage]

    # Stage-specific quick-accepts so we never nag on a perfectly good answer.
    if stage == st.ASK_BUDGET:
        # Any amount (a digit, "$", or "free") is enough.
        return (True, None) if (_has_digit(answer) or "$" in answer or "free" in low) \
            else (False, _DEFAULT_NUDGES[stage])
    if stage == st.ASK_USER_COUNT:
        ok = _has_digit(answer) or any(w in low for w in _NUMBER_WORDS)
        return (True, None) if ok else (False, _DEFAULT_NUDGES[stage])
    if stage == st.ASK_GROWTH:
        # Low-stakes and open-ended — any real answer (including clearly having
        # no plans) is fine; only empties/gibberish were caught above.
        return True, None

    # Higher-stakes free text (idea, location, business name) — use the LLM to
    # catch gibberish, with a reliable, friendly deterministic nudge.
    result = await llm.complete_json(
        _SYS,
        f"What counts as a usable answer: {_HINTS[stage]}\nUser's answer: {answer}",
        temperature=0.0,
    )
    if result is None or result.get("clear", True):
        return True, None
    return False, _DEFAULT_NUDGES[stage]
