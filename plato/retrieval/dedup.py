"""
Phase 2 (R4) — first-seen-wins dedup for retrieval results.

The orchestrator fans out a single query to several adapters in parallel
(arXiv, OpenAlex, Semantic Scholar, ...). The same paper often shows up in
more than one of them, so we collapse duplicates before truncating to the
caller's ``limit``.

The dedup key is the strongest stable identifier we have, in priority
order: ``doi`` → ``arxiv_id`` → ``openalex_id`` → lower-cased title. This
keeps the common case (a DOI is shared across adapters) cheap and falls
back to titles only when nothing more authoritative is available.
"""
from __future__ import annotations

from ..state.models import Source

__all__ = ["dedup_sources"]


def _dedup_key(source: Source) -> str:
    """Return the strongest stable identifier for ``source`` as a dedup key."""
    return (
        source.doi
        or source.arxiv_id
        or source.openalex_id
        or source.title.lower()
    )


def dedup_sources(sources: list[Source]) -> list[Source]:
    """Return ``sources`` with duplicates removed, preserving first-seen order.

    Two sources are considered duplicates when their dedup key (DOI, then
    arXiv ID, then OpenAlex ID, then lower-cased title) matches.
    """
    seen: set[str] = set()
    deduped: list[Source] = []
    for src in sources:
        key = _dedup_key(src)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(src)
    return deduped
