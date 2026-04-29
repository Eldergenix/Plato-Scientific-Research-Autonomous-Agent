"""Tests for the embedding-based novelty scorer."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from plato.novelty import (
    EmbeddingScorer,
    NoveltyResult,
    OpenAIEmbeddingBackend,
    StubEmbeddingBackend,
)
from plato.state.models import Source


def _src(idx: int, title: str, abstract: str | None = None) -> Source:
    return Source(
        id=f"s{idx}",
        title=title,
        abstract=abstract,
        retrieved_via="arxiv",
        fetched_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_stub_backend_is_deterministic():
    backend = StubEmbeddingBackend()
    [a1] = await backend.embed(["hello world"])
    b1, b2 = await backend.embed(["hello world", "different text"])
    # Same text -> same vector across calls.
    assert a1 == b1
    # Different text -> different vector (overwhelmingly likely; stub is
    # 384-dim so a collision on every coordinate is astronomically rare).
    assert b1 != b2


@pytest.mark.asyncio
async def test_stub_vector_dimension():
    backend = StubEmbeddingBackend()
    [vec] = await backend.embed(["the quick brown fox"])
    assert len(vec) == 384
    # Components are bounded to [0, 1) by construction.
    assert all(0.0 <= x < 1.0 for x in vec)


@pytest.mark.asyncio
async def test_empty_corpus_returns_perfect_novelty():
    scorer = EmbeddingScorer(backend=StubEmbeddingBackend())
    result = await scorer.score("a brand-new idea", [])
    assert result == NoveltyResult(
        score=1.0, max_similarity=0.0, nearest_source_id=None
    )


@pytest.mark.asyncio
async def test_corpus_without_usable_text_returns_perfect_novelty():
    # Sources with empty title and no abstract are skipped; if all are
    # skipped the corpus is effectively empty.
    scorer = EmbeddingScorer(backend=StubEmbeddingBackend())
    bare = Source(
        id="bare",
        title="",
        abstract=None,
        retrieved_via="arxiv",
        fetched_at=datetime.now(timezone.utc),
    )
    result = await scorer.score("a brand-new idea", [bare])
    assert result.score == 1.0
    assert result.nearest_source_id is None


@pytest.mark.asyncio
async def test_identical_text_yields_high_similarity():
    scorer = EmbeddingScorer(backend=StubEmbeddingBackend())
    idea = "Quantum entanglement in macroscopic systems"
    corpus = [
        _src(1, title="Totally unrelated paper on lichen ecology"),
        _src(2, title=idea),
        _src(3, title="Another irrelevant astronomy review"),
    ]
    result = await scorer.score(idea, corpus)
    # Idea text matches s2's title verbatim. The stub embeds title +
    # space when abstract is empty, so similarity is very high but not
    # exactly 1 — that's fine, we just need the nearest source to be s2
    # and the score to be low.
    assert result.nearest_source_id == "s2"
    assert result.max_similarity > 0.9
    assert result.score < 0.1


@pytest.mark.asyncio
async def test_score_picks_max_across_corpus():
    # Custom backend with hand-crafted vectors so we can reason about
    # cosine similarity without relying on the stub's hash output.
    class FixedBackend:
        name = "fixed"

        async def embed(self, texts):
            mapping = {
                "idea": [1.0, 0.0, 0.0],
                "title-a": [0.1, 1.0, 0.0],  # near-orthogonal -> low sim
                "title-b": [0.95, 0.05, 0.0],  # almost parallel -> high sim
                "title-c": [0.0, 0.0, 1.0],  # orthogonal -> sim 0
            }
            return [mapping[t] for t in texts]

    scorer = EmbeddingScorer(backend=FixedBackend())
    corpus = [
        _src(1, title="title-a"),
        _src(2, title="title-b"),
        _src(3, title="title-c"),
    ]
    result = await scorer.score("idea", corpus)
    assert result.nearest_source_id == "s2"
    assert result.max_similarity > 0.9
    assert result.score < 0.1


@pytest.mark.asyncio
async def test_openai_backend_raises_clear_error_when_package_missing():
    # Force ``import openai`` to fail without disturbing the rest of the
    # test suite. ``patch.dict(sys.modules, {"openai": None})`` makes
    # Python raise ImportError for the lazy import.
    backend = OpenAIEmbeddingBackend()
    with patch.dict(sys.modules, {"openai": None}):
        with pytest.raises(ImportError, match="openai"):
            await backend.embed(["hello"])


@pytest.mark.asyncio
async def test_openai_backend_uses_client_when_available():
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client

    fake_resp = MagicMock()
    fake_resp.data = [
        MagicMock(embedding=[0.1, 0.2, 0.3]),
        MagicMock(embedding=[0.4, 0.5, 0.6]),
    ]
    fake_client.embeddings.create.return_value = fake_resp

    with patch.dict(sys.modules, {"openai": fake_openai}):
        backend = OpenAIEmbeddingBackend(api_key="sk-test", model="text-embedding-3-small")
        out = await backend.embed(["a", "b"])

    assert out == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    fake_openai.OpenAI.assert_called_once_with(api_key="sk-test")
    fake_client.embeddings.create.assert_called_once_with(
        input=["a", "b"], model="text-embedding-3-small"
    )


@pytest.mark.asyncio
async def test_openai_backend_returns_empty_for_empty_input():
    # No client should be constructed when there's nothing to embed.
    backend = OpenAIEmbeddingBackend()
    assert await backend.embed([]) == []


def test_default_backend_is_stub_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    scorer = EmbeddingScorer()
    assert isinstance(scorer.backend, StubEmbeddingBackend)


def test_default_backend_is_openai_with_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    scorer = EmbeddingScorer()
    assert isinstance(scorer.backend, OpenAIEmbeddingBackend)
