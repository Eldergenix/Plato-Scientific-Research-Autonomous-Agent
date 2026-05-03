"""
R4 reranker — relevance reranking for retrieval results.

Backend priority:

1. Cohere — when ``COHERE_API_KEY`` is set AND the ``cohere`` package is
   importable. Uses the ``rerank-english-v3.0`` model.
2. CrossEncoder — when ``sentence-transformers`` is importable. Uses
   ``cross-encoder/ms-marco-MiniLM-L-6-v2`` (no API key required).
3. Passthrough — first-seen-wins slice with a one-time warning.

Both heavyweight backends are lazy-imported so ``plato.retrieval`` stays
importable on a vanilla install with neither extra present. Install via
``pip install "plato[rerank]"``.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..state.models import Source

logger = logging.getLogger(__name__)

__all__ = ["rerank"]

# Module-level guard so the "no backend" warning fires at most once per
# process. Tests reset this by reloading the module.
_WARNED = False


def _doc(source: "Source") -> str:
    """Build the text passed to the reranker for a single source."""
    parts = [source.title]
    if source.abstract:
        parts.append(source.abstract)
    return " ".join(parts)


def rerank(query: str, sources: list["Source"], *, top_k: int) -> list["Source"]:
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
