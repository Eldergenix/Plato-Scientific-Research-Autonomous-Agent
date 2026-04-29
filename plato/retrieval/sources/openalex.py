"""
OpenAlex retrieval adapter.

Hits ``https://api.openalex.org/works`` and maps the JSON response into
:class:`plato.state.models.Source` records. Auto-registers itself in the
adapter registry on import.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx

from .. import register_adapter
from ...state.models import Source
from ..doi import normalize_doi

__all__ = ["OpenAlexAdapter"]


_OPENALEX_BASE_URL = "https://api.openalex.org/works"
_OPENALEX_WORK_PREFIX = "https://openalex.org/"


def _reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    """Reconstruct an abstract from OpenAlex's inverted index format.

    OpenAlex returns abstracts as ``{"word": [pos1, pos2, ...]}``. We expand
    that back to a flat space-joined string. Returns ``None`` if the input
    is empty / missing or contains no positional information.
    """
    if not inverted:
        return None

    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        if not idxs:
            continue
        for idx in idxs:
            positions.append((idx, word))

    if not positions:
        return None

    positions.sort(key=lambda pair: pair[0])
    return " ".join(word for _, word in positions)


def _strip_openalex_prefix(work_id: str | None) -> str | None:
    if not work_id:
        return None
    if work_id.startswith(_OPENALEX_WORK_PREFIX):
        return work_id[len(_OPENALEX_WORK_PREFIX) :]
    return work_id


def _coerce_year(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_authors(authorships: list[dict[str, Any]] | None) -> list[str]:
    if not authorships:
        return []
    names: list[str] = []
    for authorship in authorships:
        author = authorship.get("author") or {}
        name = author.get("display_name")
        if name:
            names.append(name)
    return names


def _extract_venue(primary_location: dict[str, Any] | None) -> str | None:
    if not primary_location:
        return None
    src = primary_location.get("source") or {}
    return src.get("display_name") or None


def _extract_pdf_url(open_access: dict[str, Any] | None) -> str | None:
    if not open_access:
        return None
    return open_access.get("oa_url") or None


def _map_work_to_source(work: dict[str, Any]) -> Source | None:
    """Map a single OpenAlex 'work' object to a :class:`Source`.

    Returns ``None`` if the work lacks the minimum required fields (id + title).
    """
    raw_id = work.get("id")
    w_id = _strip_openalex_prefix(raw_id)
    title = work.get("title") or work.get("display_name")
    if not w_id or not title:
        return None

    doi = normalize_doi(work.get("doi"))
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
    authors = _extract_authors(work.get("authorships"))
    year = _coerce_year(work.get("publication_year"))
    venue = _extract_venue(work.get("primary_location"))
    pdf_url = _extract_pdf_url(work.get("open_access"))

    return Source(
        id=f"openalex:{w_id}",
        doi=doi,
        openalex_id=w_id,
        title=title,
        authors=authors,
        year=year,
        venue=venue,
        abstract=abstract,
        pdf_url=pdf_url,
        url=raw_id if isinstance(raw_id, str) else None,
        retrieved_via="openalex",
        fetched_at=datetime.now(timezone.utc),
    )


class OpenAlexAdapter:
    """SourceAdapter hitting OpenAlex's `/works` search endpoint."""

    name = "openalex"

    def __init__(self, *, base_url: str = _OPENALEX_BASE_URL, timeout: float = 30.0) -> None:
        self._base_url = base_url
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> list[Source]:
        """Search OpenAlex for ``query`` and return up to ``limit`` Sources."""
        per_page = max(1, min(int(limit), 200))
        url = f"{self._base_url}?search={quote_plus(query)}&per-page={per_page}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()

        works = payload.get("results") or []
        sources: list[Source] = []
        for work in works[:per_page]:
            mapped = _map_work_to_source(work)
            if mapped is not None:
                sources.append(mapped)
        return sources


# Auto-register on import so importing the module is enough to wire it in.
register_adapter(OpenAlexAdapter(), overwrite=True)
