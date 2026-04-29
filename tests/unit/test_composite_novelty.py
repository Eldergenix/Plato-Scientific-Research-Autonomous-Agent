"""Tests for the composite (LLM + embedding) novelty scorer."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from plato.novelty import (
    CompositeNoveltyScore,
    CompositeNoveltyScorer,
    EmbeddingScorer,
    NoveltyResult,
)
from plato.state.models import Source


class _FixedEmbeddingScorer(EmbeddingScorer):
    """EmbeddingScorer stand-in that returns a preset score."""

    def __init__(self, score: float, *, max_sim: float | None = None):
        # Skip parent __init__ so we don't autoselect a backend.
        self._fixed_score = score
        self._fixed_max_sim = 1.0 - score if max_sim is None else max_sim

    async def score(self, idea: str, corpus: list[Source]) -> NoveltyResult:  # type: ignore[override]
        return NoveltyResult(
            score=self._fixed_score,
            max_similarity=self._fixed_max_sim,
            nearest_source_id=None,
        )


def _src(idx: int) -> Source:
    return Source(
        id=f"s{idx}",
        title=f"Source {idx}",
        abstract="abs",
        retrieved_via="arxiv",
        fetched_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_high_agreement_when_scores_close():
    scorer = CompositeNoveltyScorer(
        embedding_scorer=_FixedEmbeddingScorer(0.85),
        llm_weight=0.5,
    )
    out = await scorer.score(idea="x", corpus=[_src(1)], llm_score=0.9)
    assert isinstance(out, CompositeNoveltyScore)
    assert out.llm_score == 0.9
    assert out.embedding_score == 0.85
    assert out.combined == pytest.approx(0.875)
    assert out.agreement is True


@pytest.mark.asyncio
async def test_low_agreement_when_scores_diverge():
    scorer = CompositeNoveltyScorer(
        embedding_scorer=_FixedEmbeddingScorer(0.9),
        llm_weight=0.5,
    )
    out = await scorer.score(idea="x", corpus=[_src(1)], llm_score=0.1)
    assert out.agreement is False
    assert out.combined == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_weight_zero_returns_pure_embedding_score():
    scorer = CompositeNoveltyScorer(
        embedding_scorer=_FixedEmbeddingScorer(0.42),
        llm_weight=0.0,
    )
    out = await scorer.score(idea="x", corpus=[_src(1)], llm_score=0.99)
    assert out.combined == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_weight_one_returns_pure_llm_score():
    scorer = CompositeNoveltyScorer(
        embedding_scorer=_FixedEmbeddingScorer(0.42),
        llm_weight=1.0,
    )
    out = await scorer.score(idea="x", corpus=[_src(1)], llm_score=0.99)
    assert out.combined == pytest.approx(0.99)


@pytest.mark.asyncio
async def test_agreement_threshold_is_strict_inequality():
    # |0.8 - 0.5| == 0.3 should NOT count as agreement.
    scorer = CompositeNoveltyScorer(
        embedding_scorer=_FixedEmbeddingScorer(0.5),
        llm_weight=0.5,
    )
    out = await scorer.score(idea="x", corpus=[_src(1)], llm_score=0.8)
    assert out.agreement is False


def test_invalid_llm_weight_rejected():
    with pytest.raises(ValueError):
        CompositeNoveltyScorer(
            embedding_scorer=_FixedEmbeddingScorer(0.5),
            llm_weight=1.5,
        )


@pytest.mark.asyncio
async def test_invalid_llm_score_rejected():
    scorer = CompositeNoveltyScorer(
        embedding_scorer=_FixedEmbeddingScorer(0.5),
        llm_weight=0.5,
    )
    with pytest.raises(ValueError):
        await scorer.score(idea="x", corpus=[_src(1)], llm_score=1.2)
