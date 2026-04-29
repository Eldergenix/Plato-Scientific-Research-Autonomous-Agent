"""Phase 3 — R6: redraft node.

Consumes ``state['critique_digest']`` plus the current ``state['paper']``
sections, asks the LLM to produce updated sections that address every issue,
and writes the revised text back to ``state['paper']``. Increments the
revision iteration counter so the conditional router can terminate the loop.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from .parameters import GraphState
from .prompts import redraft_prompt
from .tools import LLM_call, json_parser3


# Sections we allow the LLM to redraft. Title/Keywords/References are out of
# scope (citations are added in a later node; titles rarely need rewriting at
# this stage).
_REDRAFTABLE_SECTIONS: tuple[str, ...] = (
    "Abstract",
    "Introduction",
    "Methods",
    "Results",
    "Conclusions",
)


def _safe_parse_redraft(raw: str) -> dict:
    """Best-effort parse of the LLM redraft JSON; never raise."""
    try:
        parsed = json_parser3(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def redraft_node(state: GraphState, config: RunnableConfig):
    """Apply reviewer critiques to the paper and bump the iteration counter.

    Returns a partial state update with:

    - ``paper``: the existing paper merged with any fields the LLM rewrote.
    - ``revision_state``: same dict with ``iteration`` incremented.
    - ``tokens``: updated token bookkeeping.

    If the LLM call or JSON parse fails, the paper is left unchanged but the
    iteration still advances, so the loop is guaranteed to terminate at
    ``max_iterations``.
    """
    prompt = redraft_prompt(state)
    state, raw = LLM_call(prompt, state)
    parsed = _safe_parse_redraft(raw)

    paper: dict[str, Any] = dict(state.get("paper") or {})
    for section in _REDRAFTABLE_SECTIONS:
        new_text = parsed.get(section)
        if isinstance(new_text, str) and new_text.strip():
            paper[section] = new_text

    revision_state = dict(state.get("revision_state") or {})
    revision_state["iteration"] = int(revision_state.get("iteration", 0) or 0) + 1
    revision_state.setdefault("max_iterations", 2)

    return {
        "paper": paper,
        "revision_state": revision_state,
        "tokens": state["tokens"],
        # Reset critiques so the next reviewer pass starts fresh.
        "critiques": {},
    }


__all__ = ["redraft_node"]
