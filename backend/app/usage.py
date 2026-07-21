"""Token + cost instrumentation for every LLM call (Week 6 verification, Step 6).

Until this module existed, `codegen.generate()` returned `(text, model_used)` and
captured NO usage anywhere in the codebase, so every cost figure in CONTEXT.md
was an estimate. Step 6 asks for measured numbers, and measuring requires a
measurement.

TWO DESIGN RULES, both taken from the standing principle in CONTEXT.md —
"absence of evidence is not evidence of success":

1. **A failed capture must never look like a cheap call.** If a provider response
   carries no usable usage block, the row is written with `capture_ok=False` and
   NULL token counts — never 0. A silent 0 would understate spend and read as
   good news, which is exactly the failure mode this project keeps finding. Any
   analysis MUST check for `capture_ok = false` rows before trusting a total.
2. **Tokens are the durable fact; cost is derived.** `cost_usd` is NULL whenever
   no confirmed rate exists, and is always recomputable later from the stored
   token counts and `model_used` — whereas a token count not captured at call
   time is gone forever. Rates also expire: a promotional rate that silently
   goes stale is the same failure as a check that cannot fail, so `_RATE_EXPIRY`
   is an active tripwire the test suite asserts on.

Attribution reuses the QA pass's existing `run_id` (migration 0008) through a
contextvar, so no call site has to thread an extra argument down through the
agent layers.
"""
import contextvars
import logging

logger = logging.getLogger("usage")

# Set once per pass by whoever owns the run id (currently qa.orchestrator.run).
# A contextvar propagates through await chains and is copied into tasks created
# by asyncio.gather, so parallel agent calls inherit it automatically.
_run_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "llm_run_ctx", default={}
)


def set_run_context(run_id: str | None = None, project_id: int | None = None,
                    stage: str | None = None):
    """Tag every LLM call made downstream of here. Returns the reset token."""
    return _run_ctx.set({"run_id": run_id, "project_id": project_id, "stage": stage})


def reset_run_context(token) -> None:
    try:
        _run_ctx.reset(token)
    except ValueError:      # pragma: no cover - reset from a different context
        pass


def current_context() -> dict:
    return dict(_run_ctx.get() or {})


# --------------------------------------------------------------- extraction
# One function per provider, deliberately NOT merged into a single getattr
# cascade: each provider names these fields differently, and a shared helper
# that "handles" all three would silently return zeros for whichever shape it
# failed to match. Each path is separately provable because each is separate.

def extract_openai(resp) -> tuple[int, int] | None:
    """OpenAI: resp.usage.prompt_tokens / .completion_tokens."""
    u = getattr(resp, "usage", None)
    if u is None:
        return None
    prompt = getattr(u, "prompt_tokens", None)
    completion = getattr(u, "completion_tokens", None)
    if prompt is None or completion is None:
        return None
    return int(prompt), int(completion)


def extract_anthropic(resp) -> tuple[int, int] | None:
    """Anthropic: resp.usage.input_tokens / .output_tokens (no total field)."""
    u = getattr(resp, "usage", None)
    if u is None:
        return None
    prompt = getattr(u, "input_tokens", None)
    completion = getattr(u, "output_tokens", None)
    if prompt is None or completion is None:
        return None
    return int(prompt), int(completion)


def extract_google(resp) -> tuple[int, int] | None:
    """Gemini: resp.usage_metadata.prompt_token_count / .candidates_token_count."""
    u = getattr(resp, "usage_metadata", None)
    if u is None:
        return None
    prompt = getattr(u, "prompt_token_count", None)
    completion = getattr(u, "candidates_token_count", None)
    if prompt is None or completion is None:
        return None
    return int(prompt), int(completion)


# ----------------------------------------------------------------- pricing
# USD per 1,000,000 tokens, as (input, output).
#
# ONLY rates actually confirmed for this project belong here. An invented rate
# produces a confident wrong number, which is worse than no number at all — so
# anything unconfirmed is simply absent, `cost_usd` comes out NULL, and the token
# counts remain available to price later. Rates confirmed 2026-07-21.
_PRICING: dict[str, tuple[float, float]] = {
    "gemini-flash-lite-latest": (0.10, 0.40),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-opus-4-8": (5.00, 25.00),
    # INTRODUCTORY pricing — time-bound, see _RATE_EXPIRY below.
    "claude-sonnet-5": (2.00, 10.00),
}

# Rates that are promotional and WILL become wrong on a known date. A rate that
# silently goes stale is the same failure as a check that cannot fail: the number
# still looks confident, and nothing announces that it stopped being true. So
# this is an active tripwire, not a comment — `stale_rates()` is asserted by
# tests/test_token_instrumentation.py, which starts FAILING once the date passes
# and names what to do about it.
_RATE_EXPIRY: dict[str, str] = {
    "claude-sonnet-5": "2026-08-31",
}


def stale_rates(today: str | None = None) -> list[str]:
    """Models whose promotional rate has expired and must be re-confirmed.

    Compared as ISO date strings, which sort correctly and need no tz handling.
    """
    if today is None:
        from datetime import date
        today = date.today().isoformat()
    return sorted(m for m, expires in _RATE_EXPIRY.items() if today > expires)


def price(model_used: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    key = (model_used or "").lower()
    rate = _PRICING.get(key)
    if rate is None:
        return None
    if key in _RATE_EXPIRY and stale_rates():
        # Still computed — the token counts are real and this is the best figure
        # available — but never silently.
        logger.warning(
            "Pricing %s with an EXPIRED introductory rate (lapsed %s). "
            "cost_usd for this call is not trustworthy until _PRICING is updated.",
            key, _RATE_EXPIRY[key],
        )
    return round(prompt_tokens / 1e6 * rate[0] + completion_tokens / 1e6 * rate[1], 8)


# -------------------------------------------------------------- persistence
async def record(provider: str, model_requested: str, model_used: str,
                 tokens: tuple[int, int] | None, fell_back: bool = False) -> None:
    """Write one usage row. NEVER raises — instrumentation must not be able to
    break a pipeline run. A write that fails is logged loudly, because a missing
    row understates spend."""
    # Imported here so `app.usage` stays importable without a DB (the extraction
    # helpers above are pure and are unit-tested on their own).
    from app.database import async_session
    from app.models import LLMUsage

    ctx = current_context()
    prompt_tokens = tokens[0] if tokens else None
    completion_tokens = tokens[1] if tokens else None
    capture_ok = tokens is not None

    if not capture_ok:
        # Loud on purpose: this is the case that would otherwise look free.
        logger.warning(
            "LLM usage NOT captured for %s/%s — provider returned no usable usage "
            "block. Row recorded with capture_ok=false; totals are incomplete.",
            provider, model_used,
        )

    try:
        async with async_session() as db:
            db.add(LLMUsage(
                run_id=ctx.get("run_id"),
                project_id=ctx.get("project_id"),
                stage=ctx.get("stage"),
                provider=provider,
                model_requested=model_requested,
                model_used=model_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=(prompt_tokens + completion_tokens) if capture_ok else None,
                cost_usd=(price(model_used, prompt_tokens, completion_tokens)
                          if capture_ok else None),
                capture_ok=capture_ok,
                fell_back=fell_back,
            ))
            await db.commit()
    except Exception:   # pragma: no cover - never break the pipeline
        logger.exception("Failed to persist LLM usage row (%s/%s)", provider, model_used)
