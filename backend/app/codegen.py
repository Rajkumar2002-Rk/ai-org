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


async def _via_openai(model: str, system: str, user: str, temperature: float) -> str | None:
    if _openai is None:
        return None
    resp = await _openai.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
    )
    return (resp.choices[0].message.content or "").strip()


async def _via_anthropic(model: str, system: str, user: str, temperature: float) -> str | None:
    if not settings.anthropic_api_key:
        return None
    import anthropic  # imported lazily so the app runs without the extra dep
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    # Newer Claude models reject `temperature`, so we omit it.
    resp = await client.messages.create(
        model=_ANTHROPIC_IDS.get(model, "claude-sonnet-5"),
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


async def _via_google(model: str, system: str, user: str, temperature: float) -> str | None:
    if not settings.gemini_api_key:
        return None
    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    gm = genai.GenerativeModel(_GEMINI_IDS.get(model, "gemini-2.5-flash-lite"),
                               system_instruction=system)
    resp = await gm.generate_content_async(
        user, generation_config={"temperature": temperature}
    )
    return (resp.text or "").strip()


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
            text = await _via_anthropic(model, system, user, temperature)
            if text is not None:
                return text, label
        elif provider == "google":
            text = await _via_google(model, system, user, temperature)
            if text is not None:
                return text, label
        else:
            text = await _via_openai(model, system, user, temperature)
            if text is not None:
                return text, label
    except Exception:  # pragma: no cover - network/credential failures
        logger.exception("codegen via %s failed; falling back to OpenAI", provider)

    # Fallback: OpenAI GPT-4o (the key we always have in this project).
    if provider != "openai":
        try:
            text = await _via_openai(_OPENAI_FALLBACK, system, user, temperature)
            if text is not None:
                return text, f"{model} (fell back to {_OPENAI_FALLBACK})"
        except Exception:  # pragma: no cover
            logger.exception("OpenAI fallback failed")
    return None, model
