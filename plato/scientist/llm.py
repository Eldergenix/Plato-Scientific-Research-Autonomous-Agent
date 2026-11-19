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
import functools
import json
import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar

import pydantic
from pydantic import BaseModel

from plato.llm import claude55haiku

from .db.store import DualGraphStore

logger = logging.getLogger(__name__)

DEFAULT_MODEL = claude55haiku.name


def resolve_model(model: str | None = None) -> str:
    """Explicit model, else ``PLATO_SCIENTIST_MODEL``, else Claude Haiku 5.5."""
    return model or os.environ.get("PLATO_SCIENTIST_MODEL", DEFAULT_MODEL)


# Calls that may use the writing reserve: the paper and its review must still happen when
# the research budget is spent. Review calls after the first draft are best effort.
WRITING_PURPOSES = frozenset(
    {
        "manuscript",
        "peer_review",
        "peer_review_check",
        "manuscript_revision",
        "evidence_matrix",
        "review_methodology",
        "review_statistics",
        "review_novelty",
        "review_writing",
        "publication_format",
    }
)
Effort = Literal["low", "medium", "high", "xhigh", "max"]
T = TypeVar("T", bound=BaseModel)
# Receives the accumulated output text while a call streams (used to show the paper live).
TextSink = Callable[[str], Awaitable[None]]


class ModelRefusal(RuntimeError):
    """The model declined the request (stop_reason == "refusal")."""


class ModelOutputError(RuntimeError):
    """The model's output was truncated or failed schema validation."""


@dataclass
class ToolTurn:
    """One assistant turn of a tool-use conversation.

    ``content`` is the response's content blocks exactly as returned; they must be sent
    back unchanged in the next request (thinking blocks carry signatures)."""

    content: list[Any]
    stop_reason: str | None
    tool_uses: list[tuple[str, str, dict[str, Any]]]
    text: str


def _block_get(block: Any, key: str) -> Any:
    return block.get(key) if isinstance(block, dict) else getattr(block, key, None)


def _estimate_messages_chars(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += len(content)
            continue
        for block in content or []:
            for key in ("text", "thinking", "content", "input"):
                value = _block_get(block, key)
                if value is not None:
                    total += len(
                        value
                        if isinstance(value, str)
                        else json.dumps(value, default=str)
                    )
    return total


class ScientistModel(Protocol):
    async def structured(
        self,
        *,
        campaign_id: uuid.UUID,
        purpose: str,
        system: str,
        prompt: str,
        schema: type[T],
        max_tokens: int = 8000,
        effort: Effort = "medium",
        images: list[bytes] | None = None,
        on_text: TextSink | None = None,
    ) -> T: ...

    async def converse(
        self,
        *,
        campaign_id: uuid.UUID,
        purpose: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 16000,
        effort: Effort = "medium",
    ) -> ToolTurn: ...


@functools.cache
def _json_schema(schema: type[pydantic.BaseModel]) -> dict:
    import anthropic

    return anthropic.transform_schema(schema.model_json_schema())


def _estimate_input_tokens(*texts: str, images: int = 0) -> int:
    # Conservative upper bound (~3 chars/token) plus a flat allowance per image.
    return sum(len(t) for t in texts) // 3 + 64 + images * 1600


class AnthropicScientistModel:
    """Production implementation backed by ``anthropic.AsyncAnthropic``."""

    def __init__(
        self,
        store: DualGraphStore,
        *,
        model: str | None = None,
        client: object | None = None,
        api_key: str | None = None,
        max_concurrency: int = 8,
        writing_reserve_tokens: int = 80_000,
    ) -> None:
        import asyncio

        import anthropic

        self._store = store
        self._model = resolve_model(model)
        # A campaign paid for with its owner's key gets that key; otherwise the SDK resolves
        # credentials itself (ANTHROPIC_API_KEY, ...). Retries 429/5xx.
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key, max_retries=4, timeout=300.0
        )
        self._sem = asyncio.Semaphore(max_concurrency)
        # Research calls must leave this much budget so the paper can always be written.
        self._writing_reserve = writing_reserve_tokens

    @property
    def model(self) -> str:
        return self._model

    async def structured(
        self,
        *,
        campaign_id: uuid.UUID,
        purpose: str,
        system: str,
        prompt: str,
        schema: type[T],
        max_tokens: int = 8000,
        effort: Effort = "medium",
        images: list[bytes] | None = None,
        on_text: TextSink | None = None,
    ) -> T:
        content: list[dict] = []
        for png in images or []:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.standard_b64encode(png).decode("ascii"),
                    },
                }
            )
        content.append({"type": "text", "text": prompt})

        reserved = (
            _estimate_input_tokens(system, prompt, images=len(images or []))
            + max_tokens
        )
        keep_free = 0 if purpose in WRITING_PURPOSES else self._writing_reserve
        await self._store.reserve_tokens(campaign_id, reserved, keep_free=keep_free)
        # Until a response arrives the real usage is unknown; a failed request (network
        # error, 4xx) is not billed for output, so it is settled to zero.
        actual = 0
        try:
            # Streaming: a long manuscript (tens of thousands of thinking + output
            # tokens) would exceed a non-streaming request timeout.
            async with (
                self._sem,
                self._client.messages.stream(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=[
                        {
                            "type": "text",
                            "text": system,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": content}],
                    # The schema goes in as a plain JSON-schema dict so the SDK does not
                    # parse mid-stream: a truncated body must surface as a stop_reason after
                    # usage is known, not as a validation error that loses the token count.
                    output_config={
                        "effort": effort,
                        "format": {
                            "type": "json_schema",
                            "schema": _json_schema(schema),
                        },
                    },
                    metadata={"user_id": f"campaign-{campaign_id}"},
                ) as stream,
            ):
                if on_text is not None:
                    text_so_far = ""
                    async for delta in stream.text_stream:
                        text_so_far += delta
                        try:
                            await on_text(text_so_far)
                        except Exception:  # a display sink must never fail the call
                            logger.warning(
                                "on_text sink failed for %s", purpose, exc_info=True
                            )
                response = await stream.get_final_message()
            usage = response.usage
            actual = (
                usage.input_tokens
                + usage.output_tokens
                + (usage.cache_creation_input_tokens or 0)
                + (usage.cache_read_input_tokens or 0)
            )
            logger.info(
                "llm %s: model=%s in=%s out=%s stop=%s request_id=%s",
                purpose,
                self._model,
                usage.input_tokens,
                usage.output_tokens,
                response.stop_reason,
                getattr(response, "_request_id", None),
            )
            if response.stop_reason == "refusal":
                details = getattr(response, "stop_details", None)
                raise ModelRefusal(
                    f"{purpose}: model refused ({getattr(details, 'category', None)})"
                )
            if response.stop_reason == "max_tokens":
                raise ModelOutputError(
                    f"{purpose}: output truncated at max_tokens={max_tokens}"
                )
            text = "".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            )
            if not text:
                raise ModelOutputError(f"{purpose}: no structured output returned")
            try:
                return schema.model_validate_json(text)
            except pydantic.ValidationError as exc:
                raise ModelOutputError(
                    f"{purpose}: output failed schema validation: {exc.errors()[:3]}"
                ) from exc
        finally:
            await self._store.settle_tokens(campaign_id, reserved, actual)

    async def converse(
        self,
        *,
        campaign_id: uuid.UUID,
        purpose: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 16000,
        effort: Effort = "medium",
    ) -> ToolTurn:
        """One request of a client-side tool loop (the caller runs the tools).

        The conversation only grows, so top-level ``cache_control`` caches the whole prefix
        and each turn pays full price only for what is new. Cache reads are charged to
        the campaign budget at a tenth of their count, matching their price; everything
        else counts in full."""
        reserved = (
            _estimate_input_tokens(system, json.dumps(tools))
            + _estimate_messages_chars(messages) // 3
            + max_tokens
        )
        await self._store.reserve_tokens(
            campaign_id, reserved, keep_free=self._writing_reserve
        )
        actual = 0
        try:
            async with self._sem:
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                    tools=tools,
                    tool_choice={"type": "auto"},
                    cache_control={"type": "ephemeral"},
                    output_config={"effort": effort},
                    metadata={"user_id": f"campaign-{campaign_id}"},
                )
            usage = response.usage
            actual = (
                usage.input_tokens
                + usage.output_tokens
                + (usage.cache_creation_input_tokens or 0)
                + -(-(usage.cache_read_input_tokens or 0) // 10)
            )
            logger.info(
                "llm %s: model=%s in=%s out=%s cache_read=%s stop=%s request_id=%s",
                purpose,
                self._model,
                usage.input_tokens,
                usage.output_tokens,
                usage.cache_read_input_tokens,
                response.stop_reason,
                getattr(response, "_request_id", None),
            )
            if response.stop_reason == "refusal":
                details = getattr(response, "stop_details", None)
                raise ModelRefusal(
                    f"{purpose}: model refused ({getattr(details, 'category', None)})"
                )
            tool_uses = [
                (b.id, b.name, dict(b.input or {}))
                for b in response.content
                if getattr(b, "type", None) == "tool_use"
            ]
            text = "".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            )
            return ToolTurn(
                list(response.content), response.stop_reason, tool_uses, text
            )
        finally:
            await self._store.settle_tokens(campaign_id, reserved, actual)
