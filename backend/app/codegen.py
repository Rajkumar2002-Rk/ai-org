"""Multi-provider code-generation LLM layer (Week 4).

Developer agents pick their model from the blueprint's ``llm_routing``.
This routes a model name to the right provider — Anthropic for
``claude-*``, Google for ``gemini-*``, OpenAI otherwise — and gracefully
falls back to OpenAI GPT-4o when the requested provider has no API key.
When no provider is available at all it returns a deterministic stub so
the whole build still completes offline.
"""
import logging

from openai import AsyncOpenAI

from app import usage
from app.config import settings

logger = logging.getLogger("codegen")

_openai: AsyncOpenAI | None = (
    AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
)

# Friendly routing names -> concrete model ids per provider.
_ANTHROPIC_IDS = {"claude-sonnet": "claude-sonnet-5", "claude-opus-4-8": "claude-opus-4-8"}
# Use the "-latest" alias so Google retiring a dated model id never breaks us.
_GEMINI_IDS = {"gemini-2.5-flash-lite": "gemini-flash-lite-latest",
               "gemini": "gemini-flash-lite-latest"}
_OPENAI_FALLBACK = "gpt-4o"


def resolve_provider(model: str) -> str:
    m = (model or "").lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "google"
    return "openai"


# Each provider helper returns (text, token_usage, concrete_model_id), or None
# when that provider is not configured. The token usage is whatever the provider
# actually reported — `None` means it reported nothing usable, which is recorded
# as UNKNOWN rather than zero (see app/usage.py). `concrete_model_id` is the id
# actually billed, which is not always the routing name that was requested.
_Result = tuple[str, tuple[int, int] | None, str]


async def _via_openai(model: str, system: str, user: str, temperature: float) -> _Result | None:
    if _openai is None:
        return None
    resp = await _openai.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
    )
    text = (resp.choices[0].message.content or "").strip()
    return text, usage.extract_openai(resp), model


def _hit_token_ceiling(resp) -> bool:
    """A response truncated at max_tokens is INCOMPLETE, not empty.

    The generated file is cut off mid-content and won't parse — and without this
    check that is silently converted to a placeholder stub, indistinguishable
    from "the model returned nothing". A real baseline run stubbed the
    Stripe-payment page exactly this way, capped at 8192 tokens. `stop_reason ==
    "max_tokens"` is the signal (it does not populate `stop_details`, which is
    refusals only)."""
    return getattr(resp, "stop_reason", None) == "max_tokens"


async def _via_anthropic(model: str, system: str, user: str, temperature: float) -> _Result | None:
    if not settings.anthropic_api_key:
        return None
    import anthropic  # imported lazily so the app runs without the extra dep
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    concrete = _ANTHROPIC_IDS.get(model, "claude-sonnet-5")
    # STREAM: a high max_tokens ceiling requires streaming — the SDK refuses
    # large non-streaming requests to avoid HTTP timeouts. Streaming lets a big
    # generated file complete instead of truncating at a low cap. Newer Claude
    # models reject `temperature`, so we omit it.
    async with client.messages.stream(
        model=concrete,
        max_tokens=settings.codegen_max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        resp = await stream.get_final_message()
    if _hit_token_ceiling(resp):
        # Loud on purpose: truncation must never masquerade as an empty result.
        logger.warning(
            "Anthropic %s hit the max_tokens ceiling (%d) and was TRUNCATED — "
            "the generated file is incomplete. Raise codegen_max_tokens or split "
            "the ticket; this is not a normal empty response.",
            concrete, settings.codegen_max_tokens,
        )
    text = "".join(b.text for b in resp.content
                   if getattr(b, "type", "") == "text").strip()
    return text, usage.extract_anthropic(resp), concrete


async def _via_google(model: str, system: str, user: str, temperature: float) -> _Result | None:
    if not settings.gemini_api_key:
        return None
    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    concrete = _GEMINI_IDS.get(model, "gemini-2.5-flash-lite")
    gm = genai.GenerativeModel(concrete, system_instruction=system)
    resp = await gm.generate_content_async(
        user, generation_config={"temperature": temperature}
    )
    return (resp.text or "").strip(), usage.extract_google(resp), concrete


async def generate(
    model: str,
    system: str,
    user: str,
    temperature: float = 0.1,
    bypass_cheap: bool = False,
) -> tuple[str | None, str]:
    """Generate text with the routed model. Returns (text, model_used).

    Falls back to OpenAI GPT-4o if the routed provider isn't configured,
    and returns (None, model) if no provider is available at all.

    When CODEGEN_MODE=cheap, every request is redirected to the budget model
    so testing costs pennies. The blueprint still records the model the
    routing *intended*; only the actual call is swapped. ``bypass_cheap=True``
    disables that override — used by the security review, which must ALWAYS
    run on Claude Opus 4.8 regardless of cost or mode (core rule).
    """
    requested = model
    if settings.codegen_mode.lower() == "cheap" and not bypass_cheap:
        model = settings.codegen_cheap_model

    provider = resolve_provider(model)
    label = model if requested == model else f"{model} (cheap mode, intended {requested})"
    try:
        if provider == "anthropic":
            result = await _via_anthropic(model, system, user, temperature)
        elif provider == "google":
            result = await _via_google(model, system, user, temperature)
        else:
            result = await _via_openai(model, system, user, temperature)
        if result is not None:
            text, tokens, concrete = result
            await usage.record(provider, requested, concrete, tokens)
            return text, label
    except Exception:  # pragma: no cover - network/credential failures
        logger.exception("codegen via %s failed; falling back to OpenAI", provider)

    # Fallback: OpenAI GPT-4o (the key we always have in this project).
    if provider != "openai":
        try:
            result = await _via_openai(_OPENAI_FALLBACK, system, user, temperature)
            if result is not None:
                text, tokens, concrete = result
                await usage.record("openai", requested, concrete, tokens, fell_back=True)
                return text, f"{model} (fell back to {_OPENAI_FALLBACK})"
        except Exception:  # pragma: no cover
            logger.exception("OpenAI fallback failed")
    return None, model
