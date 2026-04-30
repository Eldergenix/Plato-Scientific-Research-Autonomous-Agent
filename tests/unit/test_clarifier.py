"""Unit tests for the Workflow-#1 research-question clarifier."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from plato.langgraph_agents.clarifier import research_question_clarifier


def _state(skip: bool = False) -> dict:
    state: dict = {
        "data_description": "Predict galaxy cluster masses from photometric survey data.",
        "llm": {"llm": object(), "stream_verbose": False, "max_output_tokens": 1024},
        "tokens": {"ti": 0, "to": 0, "i": 0, "o": 0},
        "files": {"f_stream": "/tmp/_unused", "LLM_calls": "/tmp/_unused"},
    }
    if skip:
        state["skip_clarification"] = True
    return state


def _run(state):
    return asyncio.run(research_question_clarifier(state, None))


def test_skip_clarification_short_circuits_no_llm_call():
    """skip_clarification=True must return immediately without calling the LLM."""
    state = _state(skip=True)
    with patch(
        "plato.langgraph_agents.clarifier.LLM_call_stream"
    ) as mocked:
        result = _run(state)
    mocked.assert_not_called()
    assert result == {"clarifying_questions": [], "needs_clarification": False}


def test_happy_path_returns_three_questions():
    payload = (
        "```json\n"
        "[\"Which photometric survey?\", \"What redshift range?\", \"What target accuracy?\"]\n"
        "```"
    )
    state = _state()
    with patch(
        "plato.langgraph_agents.clarifier.LLM_call_stream",
        return_value=(state, payload),
    ) as mocked:
        result = _run(state)

    assert mocked.call_count == 1
    qs = result["clarifying_questions"]
    assert len(qs) == 3
    assert all(isinstance(q, str) and q for q in qs)
    assert result["needs_clarification"] is True


def test_empty_array_means_no_clarification_needed():
    payload = "```json\n[]\n```"
    state = _state()
    with patch(
        "plato.langgraph_agents.clarifier.LLM_call_stream",
        return_value=(state, payload),
    ):
        result = _run(state)
    assert result["clarifying_questions"] == []
    assert result["needs_clarification"] is False


def test_malformed_response_retries_then_returns_no_questions():
    state = _state()
    with patch(
        "plato.langgraph_agents.clarifier.LLM_call_stream",
        return_value=(state, "this is not JSON"),
    ) as mocked:
        result = _run(state)
    # Three retries, all fail.
    assert mocked.call_count == 3
    assert result["clarifying_questions"] == []
    assert result["needs_clarification"] is False


def test_retry_recovers_on_second_attempt():
    bad = "totally not JSON"
    good = "```json\n[\"What time range?\"]\n```"
    state = _state()
    with patch(
        "plato.langgraph_agents.clarifier.LLM_call_stream",
        side_effect=[(state, bad), (state, good)],
    ) as mocked:
        result = _run(state)
    assert mocked.call_count == 2
    assert result["clarifying_questions"] == ["What time range?"]
    assert result["needs_clarification"] is True


def test_blank_strings_are_filtered_out():
    """Whitespace-only entries should not flip needs_clarification."""
    payload = "```json\n[\"\", \"   \"]\n```"
    state = _state()
    with patch(
        "plato.langgraph_agents.clarifier.LLM_call_stream",
        return_value=(state, payload),
    ):
        result = _run(state)
    assert result["clarifying_questions"] == []
    assert result["needs_clarification"] is False
