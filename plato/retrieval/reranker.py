"""
R4 reranker — relevance reranking for retrieval results.

Backend priority:

1. Cohere — when ``COHERE_API_KEY`` is set AND the ``cohere`` package is
   importable. Uses the ``rerank-english-v3.0`` model.
2. CrossEncoder — when ``sentence-transformers`` is importable. Uses
   ``cross-encoder/ms-marco-MiniLM-L-6-v2`` (no API key required).
3. BM25 — dependency-free lexical ranking over title (weighted twice) and abstract,
   used when the caller passes ``fallback="bm25"`` (the live scientist does, so a
   fan-out over many adapters keeps the most relevant papers, not the first adapter's).
4. Passthrough — first-seen-wins slice with a one-time warning.

Both heavyweight backends are lazy-imported so ``plato.retrieval`` stays
importable on a vanilla install with neither extra present. Install via
``pip install "plato[rerank]"``.
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..state.models import Source

logger = logging.getLogger(__name__)

__all__ = ["bm25_rank", "rerank"]

# Module-level guard so the "no backend" warning fires at most once per
# process. Tests reset this by reloading the module.
_WARNED = False


def _doc(source: "Source") -> str:
    """Build the text passed to the reranker for a single source."""
    parts = [source.title]
    if source.abstract:
        parts.append(source.abstract)
    return " ".join(parts)


_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the to was "
    "were with we our this these those using via vs versus".split()
)


def _tokens(text: str) -> list[str]:
    return [
        t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1
    ]


def bm25_rank(
    query: str, sources: list["Source"], *, top_k: int, k1: float = 1.5, b: float = 0.75
) -> list["Source"]:
    """Okapi BM25 over title (counted twice) + abstract. Stable: ties keep input order."""
    q = set(_tokens(query))
    if not q or not sources:
        return sources[:top_k]
    docs = [Counter(_tokens(s.title) * 2 + _tokens(s.abstract or "")) for s in sources]
    lengths = [sum(d.values()) for d in docs]
    avg = (sum(lengths) / len(lengths)) or 1.0
    n = len(docs)
    idf = {
        t: math.log(1 + (n - df + 0.5) / (df + 0.5))
        for t in q
        for df in [sum(1 for d in docs if t in d)]
    }
    scores = []
    for i, (d, length) in enumerate(zip(docs, lengths, strict=True)):
        score = sum(
            idf[t] * d[t] * (k1 + 1) / (d[t] + k1 * (1 - b + b * length / avg))
            for t in q
            if t in d
        )
        scores.append((-score, i))
    return [sources[i] for _, i in sorted(scores)[:top_k]]


def rerank(
    query: str,
    sources: list["Source"],
    *,
    top_k: int,
    fallback: Literal["passthrough", "bm25"] = "passthrough",
) -> list["Source"]:
    """Rerank ``sources`` by relevance to ``query``, returning at most ``top_k``."""
    if not sources:
        return []

    # --- Cohere ---
    cohere_key = os.environ.get("COHERE_API_KEY", "")
    if cohere_key:
        try:
            import cohere

            client = cohere.Client(cohere_key)
            docs = [_doc(s) for s in sources]
            response = client.rerank(
                query=query,
                documents=docs,
                model="rerank-english-v3.0",
                top_n=top_k,
            )
            return [sources[hit.index] for hit in response.results]
        except ImportError:
            pass  # fall through to cross-encoder

    # --- CrossEncoder ---
    try:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        pairs = [(query, _doc(s)) for s in sources]
        scores = list(model.predict(pairs))
        ranked = sorted(zip(scores, sources), key=lambda t: t[0], reverse=True)
        return [src for _, src in ranked[:top_k]]
    except ImportError:
        pass

    if fallback == "bm25":
        return bm25_rank(query, sources, top_k=top_k)

    # --- Passthrough ---
    global _WARNED
    if not _WARNED:
        logger.warning(
            "plato.retrieval.reranker: no rerank backend available "
            "(install plato[rerank] for sentence-transformers, or set "
            "COHERE_API_KEY). Falling back to first-seen-wins ordering."
        )
        _WARNED = True
    return sources[:top_k]
