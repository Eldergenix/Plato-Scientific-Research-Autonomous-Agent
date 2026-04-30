"""Phase 2 (R4) wiring tests for the literature node.

The unit under test is :func:`plato.langgraph_agents.literature.semantic_scholar`,
which used to hit Semantic Scholar directly. After Phase 2 wiring it pulls
from the multi-source orchestrator and wraps abstracts in ``<external>``
markers (R12).
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from plato.langgraph_agents import literature as literature_mod
from plato.state.models import Source


def _make_source(arxiv_id: str, title: str, abstract: str) -> Source:
    return Source(
        id=f"arxiv:{arxiv_id}",
        arxiv_id=arxiv_id,
        title=title,
        authors=["A. Author", "B. Author"],
        year=2024,
        abstract=abstract,
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        url=f"https://arxiv.org/abs/{arxiv_id}",
        retrieved_via="arxiv",
        fetched_at=datetime.now(timezone.utc),
    )


def _stub_state(tmpdir: str) -> dict:
    return {
        "literature": {
            "query": "dark matter halos",
            "messages": "",
            "papers": "",
            "next_agent": "",
            "iteration": 0,
            "max_iterations": 7,
            "decision": "",
            "num_papers": 0,
        },
        "files": {
            "literature_log": os.path.join(tmpdir, "literature.log"),
            "papers": os.path.join(tmpdir, "papers_processed.log"),
        },
        "domain": "astro",
    }


@pytest.mark.asyncio
async def test_semantic_scholar_uses_orchestrator_and_wraps_abstracts():
    sources = [
        _make_source(
            "2401.0001",
            "Halos at z=2",
            "We measure halo formation in cosmological simulations.",
        ),
        _make_source(
            "2401.0002",
            "Subhalo Statistics",
            "Subhalo mass functions are derived from N-body runs.",
        ),
    ]

    async def fake_retrieve(query, limit, *, profile=None, adapter_names=None):  # noqa: ARG001
        # Return canned, deduped Sources without doing any network I/O.
        assert limit == 20
        return list(sources)

    with tempfile.TemporaryDirectory() as tmpdir:
        state = _stub_state(tmpdir)

        with patch.object(literature_mod, "retrieve", fake_retrieve):
            out = await literature_mod.semantic_scholar(state, config={})

        lit = out["literature"]
        assert lit["num_papers"] == 2
        assert isinstance(lit["sources"], list)
        assert len(lit["sources"]) == 2
        assert all(isinstance(s, Source) for s in lit["sources"])
        assert {s.arxiv_id for s in lit["sources"]} == {"2401.0001", "2401.0002"}

        joined = "\n".join(lit["papers"])
        # R12: every abstract is wrapped before going into the prompt context.
        assert joined.count('<external kind="abstract">') == 2
        assert joined.count("</external>") == 2
        # Original abstract content is preserved inside the marker.
        assert "halo formation" in joined
        assert "Subhalo mass functions" in joined
        # Paper-info shape is intact.
        assert "1. Halos at z=2 (2024)" in joined
        assert "2. Subhalo Statistics (2024)" in joined
        assert "Authors: A. Author, B. Author" in joined
        # arXiv link is appended for arxiv-derived sources.
        assert "https://arxiv.org/pdf/2401.0001" in joined

        # Files were persisted exactly like the legacy code did.
        with open(state["files"]["literature_log"]) as f:
            log_contents = f.read()
        assert '<external kind="abstract">' in log_contents
        with open(state["files"]["papers"]) as f:
            papers_contents = f.read()
        assert '<external kind="abstract">' in papers_contents


@pytest.mark.asyncio
async def test_semantic_scholar_handles_empty_search():
    async def empty_search(query, limit, *, profile=None, adapter_names=None):  # noqa: ARG001
        return []

    with tempfile.TemporaryDirectory() as tmpdir:
        state = _stub_state(tmpdir)
        with patch.object(literature_mod, "retrieve", empty_search):
            out = await literature_mod.semantic_scholar(state, config={})
        lit = out["literature"]
        assert lit["num_papers"] == 0
        assert lit["sources"] == []
        assert lit["papers"] == ["No papers found with the query.\n"]


@pytest.mark.asyncio
async def test_semantic_scholar_skips_sources_without_abstract():
    sources = [
        _make_source("2401.X", "Has abstract", "non-empty abstract"),
        Source(
            id="arxiv:2401.Y",
            arxiv_id="2401.Y",
            title="No abstract",
            retrieved_via="arxiv",
            fetched_at=datetime.now(timezone.utc),
            abstract=None,
        ),
    ]

    async def fake_search(query, limit, *, profile=None, adapter_names=None):  # noqa: ARG001
        return list(sources)

    with tempfile.TemporaryDirectory() as tmpdir:
        state = _stub_state(tmpdir)
        with patch.object(literature_mod, "retrieve", fake_search):
            out = await literature_mod.semantic_scholar(state, config={})
        lit = out["literature"]
        # Only the source with an abstract is counted.
        assert lit["num_papers"] == 1
        # But all retrieved sources are preserved in `sources` for downstream
        # auditing — abstract-less ones are still legitimate hits.
        assert len(lit["sources"]) == 2
