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
from .doi import normalize_doi, parse_arxiv_id

__all__ = ["dedup_sources"]


# Whitespace + punctuation collapser for the title-fallback dedup path.
# Without this, "Foo: Bar" and "Foo:  Bar" land in separate buckets even
# though they're the same paper from two adapters.
_TITLE_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def _normalize_title(title: str | None) -> str:
    if not title:
        return ""
    return _TITLE_PUNCT_RE.sub(" ", title).strip().lower()


def _dedup_key(source: Source) -> str:
    """Return the strongest stable identifier for ``source`` as a dedup key.

    Iter-5: normalise each candidate before falling through. Without this,
    DOI variants (``10.1234/X`` vs ``10.1234/x`` vs
    ``https://doi.org/10.1234/X``) and arXiv variants (``arXiv:2401.12345v2``
    vs ``2401.12345``) collide into separate buckets, defeating the
    multi-adapter dedup.
    """
    doi = normalize_doi(source.doi)
    if doi:
        return f"doi:{doi}"
    arxiv = parse_arxiv_id(source.arxiv_id)
    if arxiv:
        return f"arxiv:{arxiv}"
    if source.openalex_id:
        # OpenAlex ids are already canonical (W12345...).
        return f"oa:{source.openalex_id.strip()}"
    return f"title:{_normalize_title(source.title)}"


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
