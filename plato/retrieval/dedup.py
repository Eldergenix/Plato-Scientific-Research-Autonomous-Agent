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

import re

from ..state.models import Source

__all__ = ["dedup_sources", "title_key"]


def _dedup_key(source: Source) -> str:
    """Return the strongest stable identifier for ``source`` as a dedup key."""
    return source.doi or source.arxiv_id or source.openalex_id or source.title.lower()


_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# Titles shorter than this ("Editorial", "Introduction") are too generic to identify a work.
_MIN_TITLE_KEY = 30


def title_key(source: Source) -> str | None:
    """Normalised title plus year, or None when the title is too generic to match on.

    Repositories mint several DOIs for one work (Figshare's ``.v1`` versions, preprint
    and journal DOIs), so identifier keys alone leave visible duplicates."""
    norm = _NON_ALNUM.sub(" ", source.title.lower()).strip()
    if len(norm) < _MIN_TITLE_KEY:
        return None
    return f"title:{norm}:{source.year or ''}"


def dedup_sources(sources: list[Source]) -> list[Source]:
    """Return ``sources`` with duplicates removed, preserving first-seen order.

    Two sources are duplicates when their dedup key (DOI, then arXiv ID, then
    OpenAlex ID, then lower-cased title) matches, or when their normalised titles
    (at least 30 characters) and years match. A kept record missing an abstract
    takes it from a later duplicate.
    """
    seen: dict[str, int] = {}
    deduped: list[Source] = []
    for src in sources:
        keys = [k for k in (_dedup_key(src), title_key(src)) if k]
        hit = next((seen[k] for k in keys if k in seen), None)
        if hit is not None:
            kept = deduped[hit]
            if not kept.abstract and src.abstract:
                deduped[hit] = kept.model_copy(update={"abstract": src.abstract})
            for k in keys:
                seen.setdefault(k, hit)
            continue
        for k in keys:
            seen[k] = len(deduped)
        deduped.append(src)
    return deduped
