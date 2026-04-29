"""Unit tests for the Phase 2 R5 claim-extraction LangGraph node.

These tests never make real LLM calls. They patch
``plato.langgraph_agents.claim_extractor.LLM_call_stream`` to return
deterministic mock responses so the extractor's parsing, span resolution,
retry behaviour, and state-merge semantics can be verified in isolation.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from plato.langgraph_agents.claim_extractor import claim_extractor
from plato.state.models import Claim, Source


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

ABSTRACT = (
    "Dark matter constitutes roughly 27% of the universe's mass-energy content. "
    "Recent observations from JWST suggest unexpectedly bright galaxies at high redshift. "
    "These findings challenge standard ΛCDM cosmology."
)


def _make_source(idx: int = 0, abstract: str | None = ABSTRACT) -> Source:
    return Source(
        id=f"src-{idx:03d}",
        title=f"Test paper {idx}",
        abstract=abstract,
        retrieved_via="arxiv",
        fetched_at=datetime.now(timezone.utc),
    )


def _state(sources=None, papers=None, claims=None):
    """Build a minimal GraphState-like dict for the extractor."""
    state: dict = {
        "llm": {"llm": object(), "stream_verbose": False, "max_output_tokens": 1024},
        "tokens": {"ti": 0, "to": 0, "i": 0, "o": 0},
        "files": {"f_stream": "/tmp/_unused", "LLM_calls": "/tmp/_unused"},
    }
    if sources is not None:
        state["sources"] = sources
    if papers is not None:
        state["literature"] = {"papers": papers, "num_papers": 0}
    if claims is not None:
        state["claims"] = claims
    return state


def _run(state):
    return asyncio.run(claim_extractor(state, None))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_extracts_claims_with_correct_quote_span():
    """When span_text matches the abstract, quote_span = (start, end) offsets."""
    span = "Dark matter constitutes roughly 27% of the universe's mass-energy content."
    claim_text = "Dark matter is about 27% of the universe."
    payload = (
        "```json\n"
        f'[{{"text": "{claim_text}", "span_text": "{span}"}}]\n'
        "```"
    )
    state = _state(sources=[_make_source(0)])

    with patch(
        "plato.langgraph_agents.claim_extractor.LLM_call_stream",
        return_value=(state, payload),
    ) as mocked:
        result = _run(state)

    assert mocked.call_count == 1
    claims = result["claims"]
    assert len(claims) == 1
    c = claims[0]
    assert isinstance(c, Claim)
    assert c.text == claim_text
    assert c.source_id == "src-000"
    assert c.section == "abstract"
    assert c.quote_span is not None
    start, end = c.quote_span
    assert ABSTRACT[start:end] == span


def test_unfindable_span_yields_none_quote_span():
    """If span_text isn't a verbatim substring of the abstract, quote_span is None."""
    payload = (
        "```json\n"
        '[{"text": "Galaxies are bright.", "span_text": "this exact phrase is not present anywhere"}]\n'
        "```"
    )
    state = _state(sources=[_make_source(1)])

    with patch(
        "plato.langgraph_agents.claim_extractor.LLM_call_stream",
        return_value=(state, payload),
    ):
        result = _run(state)

    claims = result["claims"]
    assert len(claims) == 1
    assert claims[0].quote_span is None
    assert claims[0].source_id == "src-001"
    assert claims[0].text == "Galaxies are bright."


def test_malformed_json_triggers_retry_then_returns_no_claims():
    """3 malformed JSON responses → retry loop exhausts → empty claim list."""
    state = _state(sources=[_make_source(2)])

    with patch(
        "plato.langgraph_agents.claim_extractor.LLM_call_stream",
        return_value=(state, "this is definitely not JSON at all"),
    ) as mocked:
        result = _run(state)

    # exactly 3 retry attempts per source, all malformed
    assert mocked.call_count == 3
    assert result["claims"] == []


def test_existing_claims_are_preserved_and_new_appended():
    """Pre-existing claims in state must survive; new claims are appended after."""
    existing = [
        Claim(id="prev-001", text="Pre-existing claim", source_id="src-prev", section="results"),
    ]
    state = _state(sources=[_make_source(3)], claims=existing)

    payload = (
        "```json\n"
        '[{"text": "JWST sees bright galaxies.", "span_text": "JWST suggest unexpectedly bright galaxies"}]\n'
        "```"
    )
    with patch(
        "plato.langgraph_agents.claim_extractor.LLM_call_stream",
        return_value=(state, payload),
    ):
        result = _run(state)

    claims = result["claims"]
    assert len(claims) == 2
    # original is first, new claim is appended
    assert claims[0].id == "prev-001"
    assert claims[0].text == "Pre-existing claim"
    assert claims[1].text == "JWST sees bright galaxies."
    assert claims[1].source_id == "src-003"
    assert claims[1].section == "abstract"


def test_falls_back_to_literature_papers_when_sources_absent():
    """If state['sources'] is missing, the legacy literature.papers list is used."""
    paper_str = (
        "1. Some Title (2024)\n"
        "Authors: Jane Doe\n"
        f"Abstract: {ABSTRACT}\n"
        "URL: https://example.org/paper"
    )
    state = _state(papers=[paper_str])

    payload = (
        "```json\n"
        '[{"text": "Dark matter is 27% of the universe.", '
        '"span_text": "Dark matter constitutes roughly 27%"}]\n'
        "```"
    )
    with patch(
        "plato.langgraph_agents.claim_extractor.LLM_call_stream",
        return_value=(state, payload),
    ):
        result = _run(state)

    claims = result["claims"]
    assert len(claims) == 1
    assert claims[0].source_id == "literature-0"
    assert claims[0].quote_span is not None


def test_retry_recovers_after_initial_malformed_response():
    """If the 1st response is bad but the 2nd is good, the claim should land."""
    bad = "totally not json"
    good = (
        "```json\n"
        '[{"text": "Recovered claim", "span_text": "ΛCDM cosmology"}]\n'
        "```"
    )
    state = _state(sources=[_make_source(4)])

    with patch(
        "plato.langgraph_agents.claim_extractor.LLM_call_stream",
        side_effect=[(state, bad), (state, good)],
    ) as mocked:
        result = _run(state)

    assert mocked.call_count == 2
    assert len(result["claims"]) == 1
    assert result["claims"][0].text == "Recovered claim"
    assert result["claims"][0].quote_span is not None


def test_no_inputs_yields_empty_claims():
    """No sources and no literature.papers → empty claim update, no LLM calls."""
    state = _state()

    with patch(
        "plato.langgraph_agents.claim_extractor.LLM_call_stream",
    ) as mocked:
        result = _run(state)

    mocked.assert_not_called()
    assert result["claims"] == []
