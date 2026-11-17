"""Model access for the scientist swarm (Claude Haiku 5.5 via the official Anthropic SDK).

Every call:

* reserves its worst-case token cost against the campaign budget *before* the request
  (``BudgetExceeded`` stops the call) and settles to the real usage afterwards;
* uses structured outputs (``messages.parse`` + a Pydantic schema), so node code never
  parses free text;
* sends no ``temperature`` (non-default sampling parameters are rejected by Haiku 5.5)
  and no assistant prefill; depth is controlled with ``output_config.effort``;
* treats ``stop_reason == "refusal"`` and truncated output as errors instead of
  silently continuing with an empty result.

The :class:`ScientistModel` protocol lets tests inject a deterministic model.
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

from plato.llm import claude55haiku

from .db.store import DualGraphStore

logger = logging.getLogger(__name__)

DEFAULT_MODEL = claude55haiku.name


def resolve_model(model: str | None = None) -> str:
    """Explicit model, else ``PLATO_SCIENTIST_MODEL``, else Claude Haiku 5.5."""
    return model or os.environ.get("PLATO_SCIENTIST_MODEL", DEFAULT_MODEL)

WRITING_PURPOSES = frozenset({"manuscript", "peer_review", "manuscript_revision"})
Effort = Literal["low", "medium", "high", "xhigh", "max"]
T = TypeVar("T", bound=BaseModel)


class ModelRefusal(RuntimeError):
    """The model declined the request (stop_reason == "refusal")."""


class ModelOutputError(RuntimeError):
    """The model's output was truncated or failed schema validation."""


class ScientistModel(Protocol):
    async def structured(self, *, campaign_id: uuid.UUID, purpose: str, system: str, prompt: str,
                         schema: type[T], max_tokens: int = 8000, effort: Effort = "medium",
                         images: list[bytes] | None = None) -> T: ...


def _estimate_input_tokens(*texts: str, images: int = 0) -> int:
    # Conservative upper bound (~3 chars/token) plus a flat allowance per image.
    return sum(len(t) for t in texts) // 3 + 64 + images * 1600


class AnthropicScientistModel:
    """Production implementation backed by ``anthropic.AsyncAnthropic``."""

    def __init__(self, store: DualGraphStore, *, model: str | None = None,
                 client: object | None = None, max_concurrency: int = 8,
                 writing_reserve_tokens: int = 80_000) -> None:
        import asyncio

        import anthropic

        self._store = store
        self._model = resolve_model(model)
        # The SDK resolves credentials itself (ANTHROPIC_API_KEY, ...); retries 429/5xx.
        self._client = client or anthropic.AsyncAnthropic(max_retries=4, timeout=300.0)
        self._sem = asyncio.Semaphore(max_concurrency)
        # Research calls must leave this much budget so the paper can always be written.
        self._writing_reserve = writing_reserve_tokens

    @property
    def model(self) -> str:
        return self._model

    async def structured(self, *, campaign_id: uuid.UUID, purpose: str, system: str, prompt: str,
                         schema: type[T], max_tokens: int = 8000, effort: Effort = "medium",
                         images: list[bytes] | None = None) -> T:
        content: list[dict] = []
        for png in images or []:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png",
                           "data": base64.standard_b64encode(png).decode("ascii")},
            })
        content.append({"type": "text", "text": prompt})

        reserved = _estimate_input_tokens(system, prompt, images=len(images or [])) + max_tokens
        keep_free = 0 if purpose in WRITING_PURPOSES else self._writing_reserve
        await self._store.reserve_tokens(campaign_id, reserved, keep_free=keep_free)
        # Until a response arrives the real usage is unknown; a failed request (network
        # error, 4xx) is not billed for output, so it is settled to zero.
        actual = 0
        try:
            async with self._sem:
                response = await self._client.messages.parse(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": content}],
                    output_config={"effort": effort},
                    output_format=schema,
                    metadata={"user_id": f"campaign-{campaign_id}"},
                )
            usage = response.usage
            actual = (usage.input_tokens + usage.output_tokens
                      + (usage.cache_creation_input_tokens or 0) + (usage.cache_read_input_tokens or 0))
            logger.info("llm %s: model=%s in=%s out=%s stop=%s request_id=%s", purpose, self._model,
                        usage.input_tokens, usage.output_tokens, response.stop_reason,
                        getattr(response, "_request_id", None))
            if response.stop_reason == "refusal":
                details = getattr(response, "stop_details", None)
                raise ModelRefusal(f"{purpose}: model refused ({getattr(details, 'category', None)})")
            if response.stop_reason == "max_tokens":
                raise ModelOutputError(f"{purpose}: output truncated at max_tokens={max_tokens}")
            parsed = response.parsed_output
            if parsed is None:
                raise ModelOutputError(f"{purpose}: no structured output returned")
            return parsed
        finally:
            await self._store.settle_tokens(campaign_id, reserved, actual)
