"""
DataCite retrieval adapter.

Hits the public DataCite REST API for DOI metadata. DataCite covers
datasets, software, reports, preprints, and other citable research outputs
that often do not show up cleanly in article-only indexes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx  # noqa: F401  # kept so ``patch("httpx.AsyncClient.get", ...)`` resolves.

from .. import register_adapter
from ..doi import normalize_doi
from ..middleware import RetrievalClient
from ...state.models import Source

__all__ = ["DataCiteAdapter"]


_DATACITE_DOIS_URL = "https://api.datacite.org/dois"
_USER_AGENT = "Plato/1.0 (mailto:plato.astropilot.ai@gmail.com)"


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_year(value: Any, dates: Any = None) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        year = None
    if year is not None and 1500 <= year <= 2100:
        return year

    if isinstance(dates, list):
        for entry in dates:
            if not isinstance(entry, dict):
                continue
            date = _text(entry.get("date"))
            if not date:
                continue
            try:
                parsed = int(date[:4])
            except ValueError:
                continue
            if 1500 <= parsed <= 2100:
                return parsed
    return None


def _extract_title(attrs: dict[str, Any]) -> str | None:
    titles = attrs.get("titles")
    if not isinstance(titles, list):
        return None
    for entry in titles:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get("title"))
        if title:
            return title
    return None


def _extract_authors(attrs: dict[str, Any]) -> list[str]:
    creators = attrs.get("creators")
    if not isinstance(creators, list):
        return []
    names: list[str] = []
    for creator in creators:
        if not isinstance(creator, dict):
            continue
        name = _text(creator.get("name"))
        if name:
            names.append(name)
            continue
        given = _text(creator.get("givenName")) or ""
        family = _text(creator.get("familyName")) or ""
        combined = f"{given} {family}".strip()
        if combined:
            names.append(combined)
    return names


def _extract_abstract(attrs: dict[str, Any]) -> str | None:
    descriptions = attrs.get("descriptions")
    if not isinstance(descriptions, list):
        return None

    fallback: str | None = None
    for entry in descriptions:
        if not isinstance(entry, dict):
            continue
        desc = _text(entry.get("description"))
        if not desc:
            continue
        if fallback is None:
            fallback = desc
        if (_text(entry.get("descriptionType")) or "").lower() == "abstract":
            return desc
    return fallback


def _extract_venue(attrs: dict[str, Any]) -> str | None:
    container = attrs.get("container")
    if isinstance(container, dict):
        title = _text(container.get("title"))
        if title:
            return title

    publisher = _text(attrs.get("publisher"))
    if publisher:
        return publisher

    types = attrs.get("types")
    if isinstance(types, dict):
        return _text(types.get("resourceTypeGeneral")) or _text(
            types.get("resourceType")
        )
    return None


def _extract_pdf_url(attrs: dict[str, Any]) -> str | None:
    content_url = attrs.get("contentUrl")
    urls = content_url if isinstance(content_url, list) else [content_url]
    for url_value in urls:
        url = _text(url_value)
        if url and url.lower().endswith(".pdf"):
            return url
    return None


def _map_record_to_source(record: dict[str, Any]) -> Source | None:
    attrs = record.get("attributes")
    if not isinstance(attrs, dict):
        return None

    doi = normalize_doi(attrs.get("doi") or record.get("id"))
    title = _extract_title(attrs)
    if not doi or not title:
        return None

    url = _text(attrs.get("url")) or f"https://doi.org/{doi}"

    return Source(
        id=f"datacite:{doi}",
        doi=doi,
        title=title,
        authors=_extract_authors(attrs),
        year=_coerce_year(attrs.get("publicationYear"), attrs.get("dates")),
        venue=_extract_venue(attrs),
        abstract=_extract_abstract(attrs),
        pdf_url=_extract_pdf_url(attrs),
        url=url,
        retrieved_via="datacite",
        fetched_at=datetime.now(timezone.utc),
    )


class DataCiteAdapter:
    """SourceAdapter hitting DataCite's public DOI search endpoint."""

    name = "datacite"

    def __init__(
        self,
        *,
        base_url: str = _DATACITE_DOIS_URL,
        user_agent: str = _USER_AGENT,
        timeout: float = 20.0,
    ) -> None:
        self._base_url = base_url
        self._user_agent = user_agent
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> list[Source]:
        page_size = max(1, min(int(limit), 1000))
        params = urlencode(
            {
                "query": query,
                "page[size]": page_size,
                "sort": "relevance",
            }
        )
        url = f"{self._base_url}?{params}"
        headers = {"User-Agent": self._user_agent}

        async with RetrievalClient(timeout=self._timeout, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()

        records = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            return []

        sources: list[Source] = []
        for record in records[:page_size]:
            if not isinstance(record, dict):
                continue
            mapped = _map_record_to_source(record)
            if mapped is not None:
                sources.append(mapped)
        return sources


register_adapter(DataCiteAdapter(), overwrite=True)
