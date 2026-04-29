"""
Embedding-based novelty scoring against a retrieved literature corpus.

The score is ``1.0 - max_cosine_similarity(idea, corpus)``: an idea that
matches an existing source closely scores low, an idea unlike anything in
the corpus scores high.

Two backends ship out of the box:
- ``OpenAIEmbeddingBackend`` calls OpenAI's embeddings API. The ``openai``
  package is imported lazily so the module remains importable without it.
- ``StubEmbeddingBackend`` produces deterministic pseudo-vectors via
  hashing. Used for tests and as the default when no API key is present.
"""
from __future__ import annotations

import hashlib
import os
from typing import Protocol, runtime_checkable

import numpy as np
from pydantic import BaseModel, Field

from plato.state.models import Source


_STUB_DIM = 384


@runtime_checkable
class EmbeddingBackend(Protocol):
    """Anything that turns a list of strings into a list of vectors."""

    name: str

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class OpenAIEmbeddingBackend:
    """OpenAI embeddings backend. Lazy-imports ``openai`` on first use."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.name = f"openai:{model}"
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import openai  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "OpenAIEmbeddingBackend requires the 'openai' package. "
                "Install plato with `pip install plato[novelty]` or "
                "`pip install openai`."
            ) from exc
        if openai is None:
            raise ImportError(
                "OpenAIEmbeddingBackend requires the 'openai' package; "
                "the import resolved to None."
            )
        self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        # OpenAI's Python SDK is sync; the surrounding interface is async
        # so callers can await it uniformly. We don't push to a thread
        # pool — embedding latency is small relative to the rest of the
        # pipeline and the call site is already inside an event loop.
        resp = client.embeddings.create(input=texts, model=self.model)
        return [d.embedding for d in resp.data]


class StubEmbeddingBackend:
    """Deterministic hash-based pseudo-embeddings. For tests + no-key fallback."""

    name = "stub"

    def __init__(self, dim: int = _STUB_DIM) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        # Hash each (text, i) pair to a stable byte; map to [0, 1).
        # SHA-1 gives uniform distribution and is platform-stable, unlike
        # Python's built-in ``hash``, which is salted per-process.
        out: list[float] = []
        for i in range(self.dim):
            h = hashlib.sha1(f"{text}|{i}".encode("utf-8")).digest()
            out.append(int.from_bytes(h[:4], "big") % 1000 / 1000.0)
        return out

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class NoveltyResult(BaseModel):
    """Embedding-only novelty verdict for an idea against a corpus."""

    score: float = Field(
        ge=0.0,
        le=1.0,
        description="1.0 = novel, 0.0 = highly similar to corpus.",
    )
    max_similarity: float = Field(
        ge=0.0,
        le=1.0,
        description="Highest cosine similarity to any source in the corpus.",
    )
    nearest_source_id: str | None = Field(
        default=None,
        description="ID of the source closest to the idea, or None if corpus empty.",
    )


def _source_text(source: Source) -> str | None:
    """Concatenate title + abstract for embedding. None if both empty."""
    title = (source.title or "").strip()
    abstract = (source.abstract or "").strip()
    if not title and not abstract:
        return None
    return f"{title} {abstract}".strip()


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _autoselect_backend() -> EmbeddingBackend:
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIEmbeddingBackend()
    return StubEmbeddingBackend()


class EmbeddingScorer:
    """Score idea novelty as ``1 - max_cosine_similarity(idea, corpus)``."""

    def __init__(self, backend: EmbeddingBackend | None = None) -> None:
        self.backend = backend or _autoselect_backend()

    async def score(self, idea: str, corpus: list[Source]) -> NoveltyResult:
        usable: list[tuple[Source, str]] = []
        for s in corpus:
            text = _source_text(s)
            if text is not None:
                usable.append((s, text))

        if not usable:
            return NoveltyResult(
                score=1.0, max_similarity=0.0, nearest_source_id=None
            )

        texts = [idea] + [t for _, t in usable]
        vectors = await self.backend.embed(texts)
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Backend {self.backend.name} returned {len(vectors)} vectors "
                f"for {len(texts)} inputs."
            )

        idea_vec = np.asarray(vectors[0], dtype=np.float64)
        sims: list[float] = []
        for vec in vectors[1:]:
            sims.append(_cosine(idea_vec, np.asarray(vec, dtype=np.float64)))

        # Cosine on non-negative vectors lives in [0, 1]; OpenAI vectors
        # can dip negative, so clamp before turning it into a score.
        max_sim = max(sims)
        max_sim_clamped = max(0.0, min(1.0, max_sim))
        nearest_idx = sims.index(max_sim)
        nearest_source = usable[nearest_idx][0]

        return NoveltyResult(
            score=1.0 - max_sim_clamped,
            max_similarity=max_sim_clamped,
            nearest_source_id=nearest_source.id,
        )


__all__ = [
    "EmbeddingBackend",
    "OpenAIEmbeddingBackend",
    "StubEmbeddingBackend",
    "NoveltyResult",
    "EmbeddingScorer",
]
