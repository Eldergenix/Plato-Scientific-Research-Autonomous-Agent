"""Research-question clarifier node (Workflow gap #1).

Sits between ``preprocess_node`` and ``maker`` in the idea graph. Asks the
LLM for ~3 short clarifying questions that the user should answer before
the maker/hater debate spins up. Callers that already know exactly what
they want can opt out by setting ``state['skip_clarification'] = True``.

Returns a partial state update with:

* ``clarifying_questions`` — a (possibly empty) list[str].
* ``needs_clarification`` — True when at least one question was produced.

The downstream :func:`plato.langgraph_agents.routers.clarifier_router`
converts that boolean into a graph-edge decision.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

import json5

from .parameters import GraphState
from .prompts import clarifier_prompt
from ..paper_agents.tools import LLM_call_stream


_CLARIFIER_RETRIES = 3


def _parse_questions(text: str) -> list[str]:
    """Extract a JSON array of strings from an LLM response.

    Mirrors ``claim_extractor._parse_claims_json`` but keeps only string
    elements.
    """
    m = re.search(r"```json\s*(\[.*?\])\s*```", text, re.DOTALL | re.IGNORECASE)
    if not m:
        m = re.search(r"```\s*(\[.*?\])\s*```", text, re.DOTALL)
    if not m:
        m = re.search(r"(\[.*?\])", text, re.DOTALL)
    if not m:
        raise ValueError("No JSON array found in clarifier response.")

    payload = m.group(1)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        data = json5.loads(payload)

    if not isinstance(data, list):
        raise ValueError("Clarifier response is not a JSON array.")
    return [str(q).strip() for q in data if str(q).strip()]


async def research_question_clarifier(
    state: GraphState, config: Optional[RunnableConfig] = None
):
    # Note: ``Optional[RunnableConfig]`` (not ``RunnableConfig | None``)
    # because LangGraph's annotation introspection only whitelists the
    # ``Optional[...]`` and bare-``RunnableConfig`` forms.
    """Generate up to 3 clarifying questions for the supplied data description."""

    if isinstance(state, dict) and state.get("skip_clarification"):
        return {"clarifying_questions": [], "needs_clarification": False}

    prompt = clarifier_prompt(state)

    questions: list[str] = []
    for _ in range(_CLARIFIER_RETRIES):
        state, raw = LLM_call_stream(prompt, state)
        try:
            questions = _parse_questions(raw)
            break
        except Exception:
            questions = []
            continue

    return {
        "clarifying_questions": questions,
        "needs_clarification": bool(questions),
    }


__all__ = ["research_question_clarifier"]
