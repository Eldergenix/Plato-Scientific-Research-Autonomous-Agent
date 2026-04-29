"""Phase 3 — R6: multi-reviewer panel.

Four independent reviewer nodes that each critique the current paper draft from
a single specialized angle (methodology, statistics, novelty, writing). Every
reviewer calls the LLM via :func:`plato.paper_agents.tools.LLM_call`, parses the
JSON response, and writes the resulting critique into ``state['critiques']``
under its own key.

Each critique conforms to::

    {
        "severity": int,   # 0..5
        "issues": [
            {"section": "methods", "issue": "...", "fix": "..."},
            ...
        ],
    }

The reviewers are deliberately lightweight (`LLM_call`, not the streaming
variant): outputs are short structured JSON.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from .parameters import GraphState
from .prompts import (
    methodology_review_prompt,
    novelty_review_prompt,
    statistics_review_prompt,
    writing_review_prompt,
)
from .tools import LLM_call, json_parser3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_severity(value: Any) -> int:
    """Parse severity into an int in [0, 5]; default to 0 on failure."""
    try:
        sev = int(value)
    except (TypeError, ValueError):
        return 0
    if sev < 0:
        return 0
    if sev > 5:
        return 5
    return sev


def _coerce_issues(value: Any) -> list[dict]:
    """Coerce the issues field into a clean list of {section, issue, fix} dicts."""
    if not isinstance(value, list):
        return []
    cleaned: list[dict] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        cleaned.append(
            {
                "section": str(entry.get("section", "")),
                "issue": str(entry.get("issue", "")),
                "fix": str(entry.get("fix", "")),
            }
        )
    return cleaned


def _parse_critique(raw: str) -> dict:
    """Best-effort parse of an LLM JSON critique into a sane dict."""
    try:
        parsed = json_parser3(raw)
    except Exception:
        return {"severity": 0, "issues": []}
    if not isinstance(parsed, dict):
        return {"severity": 0, "issues": []}
    return {
        "severity": _coerce_severity(parsed.get("severity")),
        "issues": _coerce_issues(parsed.get("issues")),
    }


def _run_reviewer(
    state: GraphState,
    prompt_fn,
    reviewer_key: str,
) -> dict:
    """Shared reviewer body: call LLM, parse JSON, merge into state['critiques']."""
    prompt = prompt_fn(state)
    state, raw = LLM_call(prompt, state)
    critique = _parse_critique(raw)

    existing = state.get("critiques") or {}
    merged = {**existing, reviewer_key: critique}

    return {
        "critiques": merged,
        "tokens": state["tokens"],
    }


# ---------------------------------------------------------------------------
# Reviewer nodes
# ---------------------------------------------------------------------------


def methodology_reviewer(state: GraphState, config: RunnableConfig):
    """Critique the paper from a methodology standpoint."""
    return _run_reviewer(state, methodology_review_prompt, "methodology")


def statistics_reviewer(state: GraphState, config: RunnableConfig):
    """Critique the paper from a statistics / rigor standpoint."""
    return _run_reviewer(state, statistics_review_prompt, "statistics")


def novelty_reviewer(state: GraphState, config: RunnableConfig):
    """Critique the paper from a novelty / related-work standpoint."""
    return _run_reviewer(state, novelty_review_prompt, "novelty")


def writing_reviewer(state: GraphState, config: RunnableConfig):
    """Critique the paper from a clarity / writing standpoint."""
    return _run_reviewer(state, writing_review_prompt, "writing")


__all__ = [
    "methodology_reviewer",
    "statistics_reviewer",
    "novelty_reviewer",
    "writing_reviewer",
]
