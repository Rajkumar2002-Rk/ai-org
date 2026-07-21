"""Thin async wrapper around the BA agent's LLM (GPT-4o mini).

When no OpenAI key is configured every call returns ``None`` so callers
fall back to deterministic templates. This keeps the whole BA flow
working end-to-end with zero external dependencies.

TOKEN CAPTURE: this module is a SECOND LLM path, entirely separate from
``codegen.generate()``. BA, Product Intelligence, the Architect,
competitive intel and design explanations all call through here, so an
instrumentation that covered only codegen would report a pipeline total
with the Architect missing from it — a low number that looks plausible.
Both paths therefore record into ``llm_usage``.

``moderate()`` is deliberately NOT recorded: OpenAI's moderation endpoint
is free and returns no usage block, so recording it would emit a stream of
capture_ok=false rows and make genuine capture failures harder to spot.
That is an intentional exclusion, not an oversight.
"""
import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app import usage
from app.config import settings

logger = logging.getLogger("ba.llm")

_client: AsyncOpenAI | None = None
if settings.openai_api_key:
    _client = AsyncOpenAI(api_key=settings.openai_api_key)


def is_live() -> bool:
    return _client is not None


async def chat(
    system: str,
    user: str,
    temperature: float = settings.ba_temperature,
) -> str | None:
    """Return a plain-text completion, or None if the LLM is unavailable."""
    if _client is None:
        return None
    try:
        resp = await _client.chat.completions.create(
            model=settings.ba_model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        await usage.record("openai", settings.ba_model, settings.ba_model,
                           usage.extract_openai(resp))
        return (resp.choices[0].message.content or "").strip()
    except Exception:  # pragma: no cover - network/credential failures
        logger.exception("LLM chat call failed; falling back to template")
        return None


async def moderate(text: str) -> dict | None:
    """Run OpenAI's moderation endpoint. Returns {flagged, categories} or
    None if unavailable."""
    if _client is None:
        return None
    try:
        resp = await _client.moderations.create(
            model="omni-moderation-latest", input=text
        )
        result = resp.results[0]
        cats = result.categories
        flagged_cats = [
            name for name, on in (cats.model_dump().items()) if on
        ]
        return {"flagged": bool(result.flagged), "categories": flagged_cats}
    except Exception:  # pragma: no cover
        logger.exception("Moderation call failed")
        return None


async def complete_json(
    system: str,
    user: str,
    temperature: float = 0.2,
    model: str | None = None,
) -> Any | None:
    """Return parsed JSON from the model, or None on any failure.

    ``model`` lets callers (e.g. the Architect) pick a bigger model than the
    BA default; when omitted it uses the BA model.
    """
    if _client is None:
        return None
    try:
        chosen = model or settings.ba_model
        resp = await _client.chat.completions.create(
            model=chosen,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        await usage.record("openai", chosen, chosen, usage.extract_openai(resp))
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception:  # pragma: no cover
        logger.exception("LLM json call failed; falling back")
        return None
