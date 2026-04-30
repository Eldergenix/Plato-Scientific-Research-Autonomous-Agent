"""Unit tests for the Workflow-#12 research-gap detector.

The detector is pure analysis (no LLM calls), so these tests are
straightforward synchronous arrange/act/assert.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from plato.langgraph_agents.gap_detector import gap_detector
from plato.state.models import Claim, EvidenceLink, Source


def _src(idx: int, *, title: str, abstract: str) -> Source:
    return Source(
        id=f"src-{idx:03d}",
        title=title,
        abstract=abstract,
        retrieved_via="arxiv",
        fetched_at=datetime.now(timezone.utc),
    )


_DEFAULT_IDEA = "Test idea"


def _state(*, sources=None, claims=None, evidence_links=None, idea=_DEFAULT_IDEA) -> dict:
    return {
        "sources": list(sources or []),
        "claims": list(claims or []),
        "evidence_links": list(evidence_links or []),
        "idea": {"idea": idea},
    }


def _run(state):
    return asyncio.run(gap_detector(state, None))


def test_contradiction_cluster_detected():
    """A claim with both supports and refutes is a contradiction gap."""
    claims = [
        Claim(id="d-001", text="DM is 27% of universe", source_id=None),
    ]
    links = [
        EvidenceLink(claim_id="d-001", source_id="src-1", support="supports", strength="strong"),
        EvidenceLink(claim_id="d-001", source_id="src-2", support="refutes", strength="moderate"),
    ]
    sources = [
        _src(1, title="Foo", abstract="bar"),
        _src(2, title="Foo", abstract="bar"),
    ]
    state = _state(sources=sources, claims=claims, evidence_links=links)

    result = _run(state)
    contradictions = [g for g in result["gaps"] if g["kind"] == "contradiction"]
    assert len(contradictions) == 1
    g = contradictions[0]
    assert "d-001" in g["description"]
    assert "src-1" in g["evidence"] and "src-2" in g["evidence"]
    assert 0 <= g["severity"] <= 5


def test_no_contradiction_when_only_supports():
    claims = [Claim(id="d-001", text="x", source_id=None)]
    links = [
        EvidenceLink(claim_id="d-001", source_id="src-1", support="supports", strength="strong"),
        EvidenceLink(claim_id="d-001", source_id="src-2", support="supports", strength="moderate"),
    ]
    state = _state(claims=claims, evidence_links=links)
    result = _run(state)
    assert not [g for g in result["gaps"] if g["kind"] == "contradiction"]


def test_coverage_hole_when_keyword_absent():
    """An idea keyword appearing in <2 sources is a coverage hole."""
    sources = [
        _src(1, title="Halo formation", abstract="We study halos"),
        _src(2, title="More halos", abstract="halo halo halo"),
    ]
    # 'transformer' never appears in sources; should be flagged.
    state = _state(
        sources=sources,
        idea="Use transformer architectures to predict halo masses from photometric inputs",
    )
    result = _run(state)
    coverage = [g for g in result["gaps"] if g["kind"] == "coverage"]
    keywords_flagged = {ev for g in coverage for ev in g["evidence"]}
    assert "transformer" in keywords_flagged
    assert "photometric" in keywords_flagged
    # 'halo' occurs in both abstracts so it should NOT be flagged.
    assert "halo" not in keywords_flagged
    # Stopwords/short tokens like 'the', 'to', 'use' are filtered.
    assert "the" not in keywords_flagged


def test_methodology_homogeneity_detected():
    """All sources sharing the same method keyword fires a homogeneity gap."""
    sources = [
        _src(1, title="DM halos", abstract="We use a transformer model"),
        _src(2, title="Halo masses", abstract="Transformer-based predictions"),
        _src(3, title="Subhalos", abstract="Our transformer achieves SOTA"),
    ]
    state = _state(sources=sources, idea="anything")
    result = _run(state)
    homogeneity = [g for g in result["gaps"] if g["kind"] == "homogeneity"]
    assert len(homogeneity) == 1
    assert "transformer" in homogeneity[0]["evidence"]


def test_no_homogeneity_with_diverse_methods():
    sources = [
        _src(1, title="X", abstract="We use transformer architectures"),
        _src(2, title="Y", abstract="Random forest baseline"),
        _src(3, title="Z", abstract="Bayesian inference using mcmc"),
    ]
    state = _state(sources=sources)
    result = _run(state)
    assert not [g for g in result["gaps"] if g["kind"] == "homogeneity"]


def test_no_sources_with_keywords_yields_coverage_summary():
    state = _state(idea="study transformer halos")
    result = _run(state)
    coverage = [g for g in result["gaps"] if g["kind"] == "coverage"]
    assert len(coverage) == 1
    assert coverage[0]["severity"] == 5
    assert "transformer" in coverage[0]["evidence"]
    assert "halos" in coverage[0]["evidence"]


def test_empty_state_with_empty_idea_yields_empty_gaps():
    """No sources, no claims, no evidence, blank idea — no gaps to surface."""
    state = _state(idea="")
    # state['idea']['idea'] == "" → keyword extraction returns [] → no
    # coverage summary is fired even though the corpus is empty.
    result = _run(state)
    assert result == {"gaps": []}


def test_empty_corpus_with_idea_keywords_fires_coverage_summary():
    """An idea with extractable keywords + no corpus emits a single coverage gap."""
    state = _state(idea="study transformer halos at high redshift")
    result = _run(state)
    coverage = [g for g in result["gaps"] if g["kind"] == "coverage"]
    assert len(coverage) == 1
    assert coverage[0]["severity"] == 5
    # Only the empty-corpus summary is emitted, not per-keyword gaps.
    assert "uncovered" in coverage[0]["description"]


def test_single_source_does_not_trigger_homogeneity():
    sources = [_src(1, title="X", abstract="Transformer model used")]
    state = _state(sources=sources)
    result = _run(state)
    assert not [g for g in result["gaps"] if g["kind"] == "homogeneity"]


def test_unclear_links_do_not_create_contradictions():
    """A claim with supports + unclear (no refutes) is NOT a contradiction."""
    claims = [Claim(id="d-001", text="x")]
    links = [
        EvidenceLink(claim_id="d-001", source_id="src-1", support="supports", strength="strong"),
        EvidenceLink(claim_id="d-001", source_id="src-2", support="unclear", strength="weak"),
    ]
    state = _state(claims=claims, evidence_links=links)
    result = _run(state)
    assert not [g for g in result["gaps"] if g["kind"] == "contradiction"]


def test_returns_dict_with_required_keys():
    """Each gap dict has kind/description/severity/evidence."""
    sources = [_src(1, title="x", abstract="y")]
    state = _state(sources=sources, idea="needs transformer halo")
    result = _run(state)
    for g in result["gaps"]:
        assert set(g.keys()) >= {"kind", "description", "severity", "evidence"}
        assert isinstance(g["severity"], int)
        assert 0 <= g["severity"] <= 5
        assert g["kind"] in {"contradiction", "coverage", "homogeneity"}
