"""The research engineer's tool-use loop inside a sandbox workspace.

The loop is deliberately plain: the model gets the task and the workspace tools, every
tool call runs against the live sandbox, results go back as ``tool_result`` blocks
(framed as untrusted program output), and the session ends when a submission is
accepted, the turn cap is reached, or the model stops without submitting twice.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..guard import frame_untrusted
from ..llm import ScientistModel
from .tools import TOOL_SPECS, Workspace

logger = logging.getLogger(__name__)

TurnHook = Callable[[int], Awaitable[None]]


@dataclass(frozen=True)
class SessionLimits:
    max_turns: int = 40
    max_tokens_per_turn: int = 16_000
    effort: str = "medium"
    max_stalls: int = 2  # turns that end without a tool call before giving up


DEFAULT_SESSION_LIMITS = SessionLimits()


@dataclass
class SessionOutcome:
    submitted: Any
    turns: int
    reason: str
    signals: list[str] = field(default_factory=list)


async def run_session(
    *,
    model: ScientistModel,
    campaign_id: uuid.UUID,
    system: str,
    task: str,
    workspace: Workspace,
    nonce: str,
    limits: SessionLimits = DEFAULT_SESSION_LIMITS,
    on_turn: TurnHook | None = None,
    purpose: str = "workspace_engineer",
) -> SessionOutcome:
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    stalls = 0
    signals: list[str] = []
    for turn in range(1, limits.max_turns + 1):
        if on_turn is not None:
            await on_turn(turn)
        reply = await model.converse(
            campaign_id=campaign_id,
            purpose=purpose,
            system=system,
            messages=messages,
            tools=TOOL_SPECS,
            max_tokens=limits.max_tokens_per_turn,
            effort=limits.effort,  # type: ignore[arg-type]
        )
        messages.append({"role": "assistant", "content": reply.content})
        if not reply.tool_uses:
            stalls += 1
            if stalls > limits.max_stalls:
                return SessionOutcome(None, turn, "stopped without submitting", signals)
            note = (
                "Your reply was cut off by the output limit; continue with smaller steps."
                if reply.stop_reason == "max_tokens"
                else "Continue working with the tools. The session only ends when "
                "submit_experiment accepts a run."
            )
            messages.append({"role": "user", "content": note})
            continue
        stalls = 0
        results: list[dict[str, Any]] = []
        accepted: Any = None
        for tool_id, name, args in reply.tool_uses:
            result = await workspace.call(name, args)
            framed = frame_untrusted(result.text, source=f"tool:{name}", nonce=nonce)
            signals.extend(framed.injection_signals)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": framed.text,
                    "is_error": result.is_error,
                }
            )
            if result.submitted is not None and accepted is None:
                accepted = result.submitted
        if accepted is not None:
            return SessionOutcome(accepted, turn, "submitted", signals)
        if workspace.exhausted:
            return SessionOutcome(None, turn, "submissions exhausted", signals)
        remaining = limits.max_turns - turn
        if remaining <= 3:
            results.append(
                {
                    "type": "text",
                    "text": f"{remaining} turn(s) left. Submit your best working experiment now.",
                }
            )
        messages.append({"role": "user", "content": results})
    return SessionOutcome(None, limits.max_turns, "turn limit reached", signals)
