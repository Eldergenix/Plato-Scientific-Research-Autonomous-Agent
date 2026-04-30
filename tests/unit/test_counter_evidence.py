"""Unit tests for the Workflow-#11 counter-evidence search node."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import pytest

from plato.langgraph_agents import counter_evidence as ce
from plato.state.models import Source


def _src(idx: int, *, doi: str | None = None, arxiv: str | None = None,
         title: str | None = None) -> Source:
    return Source(
        id=f"src-{idx:03d}",
        doi=doi,
        arxiv_id=arxiv,
        title=title or f"Paper {idx}",
        retrieved_via="arxiv",
        fetched_at=datetime.now(timezone.utc),
    )


def _state(*, query="dark matter halos", existing=None, idea_text=None) -> dict:
    state: dict = {
        "literature": {
            "query": query,
            "sources": list(existing or []),
        },
        "idea": {"idea": idea_text or "Use ML to find DM halos."},
        "domain": "astro",
    }
    return state


def _run(state):
    return asyncio.run(ce.counter_evidence_search(state, None))


def test_dispatches_three_variants_with_steering_phrases():
    state = _state()
    seen_queries: list[str] = []

    async def fake_retrieve(query, limit, *, profile=None, adapter_names=None):
        seen_queries.append(query)
        return []

    with patch.object(ce, "retrieve", side_effect=fake_retrieve):
        result = _run(state)

    assert result == {"counter_evidence_sources": []}
    assert len(seen_queries) == 3
    # Confirm the canonical Workflow-#11 steering phrases are appended.
    joined = " | ".join(seen_queries)
    assert "fail to replicate" in joined
    assert "null result" in joined
    assert "limitations" in joined


def test_dedup_against_already_retrieved_by_doi():
    """A source already in literature.sources must be skipped via DOI."""
    existing = [_src(0, doi="10.1/already-have")]
    fresh_src = _src(1, doi="10.1/new")
    duplicate = _src(2, doi="10.1/already-have", title="Different Title")
    state = _state(existing=existing)

    async def fake_retrieve(query, limit, *, profile=None, adapter_names=None):
        return [fresh_src, duplicate]

    with patch.object(ce, "retrieve", side_effect=fake_retrieve):
        result = _run(state)

    out = result["counter_evidence_sources"]
    # 3 variants × 2 hits each, but dedup collapses to 1 (fresh) since
    # duplicate matches existing AND across-variant repeats also collapse.
    assert len(out) == 1
    assert out[0].doi == "10.1/new"


def test_dedup_against_already_retrieved_by_arxiv_id():
    existing = [_src(0, arxiv="2401.0001")]
    same_arxiv = _src(1, arxiv="2401.0001", title="Title Variation")
    fresh = _src(2, arxiv="2401.9999")
    state = _state(existing=existing)

    async def fake_retrieve(query, limit, *, profile=None, adapter_names=None):
        return [same_arxiv, fresh]

    with patch.object(ce, "retrieve", side_effect=fake_retrieve):
        result = _run(state)

    out = result["counter_evidence_sources"]
    assert {s.arxiv_id for s in out} == {"2401.9999"}


def test_dedup_falls_back_to_lowercased_title():
    existing = [_src(0, title="Halo Mergers")]
    same_title = _src(1, title="halo mergers")  # case difference
    state = _state(existing=existing)

    async def fake_retrieve(query, limit, *, profile=None, adapter_names=None):
        return [same_title]

    with patch.object(ce, "retrieve", side_effect=fake_retrieve):
        result = _run(state)

    assert result["counter_evidence_sources"] == []


def test_no_seed_query_returns_empty():
    state: dict = {"literature": {"query": ""}, "idea": {"idea": ""}}
    with patch.object(ce, "retrieve", new=AsyncMock()) as mocked:
        result = _run(state)
    mocked.assert_not_called()
    assert result == {"counter_evidence_sources": []}


def test_falls_back_to_idea_text_when_literature_query_missing():
    state: dict = {
        "literature": {},
        "idea": {"idea": "Test idea about exoplanet transits"},
        "domain": "astro",
    }
    captured: list[str] = []

    async def fake_retrieve(query, limit, *, profile=None, adapter_names=None):
        captured.append(query)
        return []

    with patch.object(ce, "retrieve", side_effect=fake_retrieve):
        _run(state)

    assert all("Test idea about exoplanet transits" in q for q in captured)


def test_failing_variant_is_logged_and_skipped():
    """If one variant raises, the other variants still contribute."""
    state = _state()
    good = _src(99, doi="10.1/good")

    async def fake_retrieve(query, limit, *, profile=None, adapter_names=None):
        if "null result" in query:
            raise RuntimeError("adapter blew up")
        return [good]

    with patch.object(ce, "retrieve", side_effect=fake_retrieve):
        result = _run(state)

    out = result["counter_evidence_sources"]
    assert len(out) == 1
    assert out[0].doi == "10.1/good"


def test_variants_reuse_state_sources_slot():
    """Sources already cached on state['sources'] (not literature) are also seen."""
    cached = _src(7, doi="10.1/cached")
    state = _state()
    state["sources"] = [cached]

    async def fake_retrieve(query, limit, *, profile=None, adapter_names=None):
        return [_src(8, doi="10.1/cached")]

    with patch.object(ce, "retrieve", side_effect=fake_retrieve):
        result = _run(state)
    assert result["counter_evidence_sources"] == []
