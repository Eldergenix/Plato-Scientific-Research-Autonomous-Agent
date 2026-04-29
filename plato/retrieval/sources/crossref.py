"""
Crossref retrieval adapter.

Hits ``https://api.crossref.org/works`` and maps ``message.items[*]`` into
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

__all__ = ["CrossrefAdapter"]


_CROSSREF_BASE_URL = "https://api.crossref.org/works"
_USER_AGENT = "Plato/1.0 (mailto:plato.astropilot.ai@gmail.com)"


def _first(items: Any) -> Any:
    if isinstance(items, list) and items:
        return items[0]
    return None


def _extract_title(item: dict[str, Any]) -> str | None:
    title = _first(item.get("title"))
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def _extract_year(item: dict[str, Any]) -> int | None:
    issued = item.get("issued") or {}
    date_parts = issued.get("date-parts")
    first_part = _first(date_parts)
    if isinstance(first_part, list) and first_part:
        try:
            return int(first_part[0])
        except (TypeError, ValueError):
            return None
    return None


def _extract_authors(item: dict[str, Any]) -> list[str]:
    raw = item.get("author") or []
    names: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        family = (entry.get("family") or "").strip()
        given = (entry.get("given") or "").strip()
        if family and given:
            names.append(f"{given} {family}")
        elif family:
            names.append(family)
        elif given:
            names.append(given)
        else:
            name = (entry.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _extract_venue(item: dict[str, Any]) -> str | None:
    venue = _first(item.get("container-title"))
    if isinstance(venue, str) and venue.strip():
        return venue.strip()
    return None


def _extract_url(item: dict[str, Any], doi: str | None) -> str | None:
    url = item.get("URL")
    if isinstance(url, str) and url.strip():
        return url.strip()
    if doi:
        return f"https://doi.org/{doi}"
    return None


def _map_item_to_source(item: dict[str, Any]) -> Source | None:
    """Map one Crossref ``message.items`` entry to a :class:`Source`.

    Returns ``None`` for items missing a DOI or a title — both are required
    for the Source to be useful downstream.
    """
    doi = normalize_doi(item.get("DOI"))
    title = _extract_title(item)
    if not doi or not title:
        return None

    return Source(
        id=f"crossref:{doi}",
        doi=doi,
        title=title,
        authors=_extract_authors(item),
        year=_extract_year(item),
        venue=_extract_venue(item),
        url=_extract_url(item, doi),
        retrieved_via="crossref",
        fetched_at=datetime.now(timezone.utc),
    )


class CrossrefAdapter:
    """SourceAdapter hitting Crossref's `/works` search endpoint."""

    name = "crossref"

    def __init__(
        self,
        *,
        base_url: str = _CROSSREF_BASE_URL,
        user_agent: str = _USER_AGENT,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url
        self._user_agent = user_agent
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> list[Source]:
        """Search Crossref for ``query`` and return up to ``limit`` Sources."""
        rows = max(1, min(int(limit), 1000))
        url = f"{self._base_url}?query={quote_plus(query)}&rows={rows}"
        headers = {"User-Agent": self._user_agent}

        async with httpx.AsyncClient(timeout=self._timeout, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()

        message = payload.get("message") or {}
        items = message.get("items") or []
        sources: list[Source] = []
        for item in items[:rows]:
            mapped = _map_item_to_source(item)
            if mapped is not None:
                sources.append(mapped)
        return sources


# Auto-register on import so importing the module is enough to wire it in.
register_adapter(CrossrefAdapter(), overwrite=True)
