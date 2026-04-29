"""
Embedding-based novelty scoring (Workflow #9).

The LLM-only novelty decider in ``plato.langgraph_agents.literature`` is
brittle on its own — it can rate an idea novel even when the retrieved
corpus contains a near-paraphrase. This package adds a cheap cosine-based
sanity check, and a composite scorer that blends LLM and embedding
signals.

Public surface:
- ``EmbeddingScorer``: turns an idea + ``Source`` corpus into a
  ``NoveltyResult`` (1.0 = fully novel, 0.0 = identical to something in
  the corpus).
- ``CompositeNoveltyScorer``: combines a caller-supplied LLM novelty score
  with the embedding score and flags disagreement.
- ``NoveltyResult``: the data model returned by ``EmbeddingScorer``.

The scorers do not call an LLM themselves; the LLM score is provided by
the existing ``novelty_decider`` node.
"""
from __future__ import annotations

from plato.novelty.composite_scorer import (
    CompositeNoveltyScore,
    CompositeNoveltyScorer,
)
from plato.novelty.embedding_scorer import (
    EmbeddingBackend,
    EmbeddingScorer,
    NoveltyResult,
    OpenAIEmbeddingBackend,
    StubEmbeddingBackend,
)

__all__ = [
    "EmbeddingBackend",
    "EmbeddingScorer",
    "NoveltyResult",
    "OpenAIEmbeddingBackend",
    "StubEmbeddingBackend",
    "CompositeNoveltyScore",
    "CompositeNoveltyScorer",
]
