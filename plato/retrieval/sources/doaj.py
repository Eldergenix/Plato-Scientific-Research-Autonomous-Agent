"""
DOAJ retrieval adapter.

Hits the Directory of Open Access Journals article search API. The public
article search endpoint requires no API key and returns article metadata
for fully open-access journals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx  # noqa: F401  # kept so ``patch("httpx.AsyncClient.get", ...)`` resolves.

from .. import register_adapter
from ..doi import normalize_doi
from ..middleware import RetrievalClient
from ...state.models import Source

__all__ = ["DOAJAdapter"]


_DOAJ_ARTICLE_SEARCH_URL = "https://doaj.org/api/search/articles"
_USER_AGENT = "Plato/1.0 (mailto:plato.astropilot.ai@gmail.com)"


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_year(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1500 <= year <= 2100 else None


def _extract_doi(bibjson: dict[str, Any]) -> str | None:
    identifiers = bibjson.get("identifier")
    if not isinstance(identifiers, list):
        return None
    for entry in identifiers:
        if not isinstance(entry, dict):
            continue
        if (_text(entry.get("type")) or "").lower() == "doi":
            return normalize_doi(entry.get("id"))
    return None


def _extract_authors(bibjson: dict[str, Any]) -> list[str]:
    raw = bibjson.get("author")
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for author in raw:
        if not isinstance(author, dict):
            continue
        name = _text(author.get("name"))
        if name:
            names.append(name)
    return names


def _extract_venue(bibjson: dict[str, Any]) -> str | None:
    journal = bibjson.get("journal")
    if isinstance(journal, dict):
        return _text(journal.get("title")) or _text(journal.get("publisher"))
    return None


def _links(bibjson: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bibjson.get("link")
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict)]


def _extract_url(bibjson: dict[str, Any], doi: str | None) -> str | None:
    for link in _links(bibjson):
        url = _text(link.get("url"))
        if url and (_text(link.get("type")) or "").lower() == "fulltext":
            return url
    for link in _links(bibjson):
        url = _text(link.get("url"))
        if url:
            return url
    return f"https://doi.org/{doi}" if doi else None


def _extract_pdf_url(bibjson: dict[str, Any]) -> str | None:
    for link in _links(bibjson):
        url = _text(link.get("url"))
        if not url:
            continue
        content_type = (_text(link.get("content_type")) or "").lower()
        if content_type == "application/pdf" or url.lower().endswith(".pdf"):
            return url
    return None


def _map_result_to_source(result: dict[str, Any]) -> Source | None:
    bibjson = result.get("bibjson")
    if not isinstance(bibjson, dict):
        return None

    title = _text(bibjson.get("title"))
    record_id = _text(result.get("id"))
    doi = _extract_doi(bibjson)
    if not title or not (record_id or doi):
        return None

    stable_id = f"doaj:{record_id}" if record_id else f"doaj:{doi}"

    return Source(
        id=stable_id,
        doi=doi,
        title=title,
        authors=_extract_authors(bibjson),
        year=_coerce_year(bibjson.get("year")),
        venue=_extract_venue(bibjson),
        abstract=_text(bibjson.get("abstract")),
        pdf_url=_extract_pdf_url(bibjson),
        url=_extract_url(bibjson, doi),
        retrieved_via="doaj",
        fetched_at=datetime.now(timezone.utc),
    )


class DOAJAdapter:
    """SourceAdapter hitting DOAJ's public article search endpoint."""

    name = "doaj"

    def __init__(
        self,
        *,
        base_url: str = _DOAJ_ARTICLE_SEARCH_URL,
        user_agent: str = _USER_AGENT,
        timeout: float = 20.0,
    ) -> None:
        self._base_url = base_url
        self._user_agent = user_agent
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> list[Source]:
        page_size = max(1, min(int(limit), 100))
        url = f"{self._base_url}/{quote(query)}?pageSize={page_size}"
        headers = {"User-Agent": self._user_agent}

        async with RetrievalClient(timeout=self._timeout, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()

        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []

        sources: list[Source] = []
        for result in results[:page_size]:
            if not isinstance(result, dict):
                continue
            mapped = _map_result_to_source(result)
            if mapped is not None:
                sources.append(mapped)
        return sources


register_adapter(DOAJAdapter(), overwrite=True)
