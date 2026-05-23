"""
OpenCitations Meta retrieval adapter.

OpenCitations Meta is identifier-first rather than a free-text search
engine. This adapter therefore acts as a DOI resolver: if the query
contains a DOI, it returns verifiable bibliographic metadata from
OpenCitations' public Meta API; otherwise it returns an empty list without
touching the network.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx  # noqa: F401  # kept so ``patch("httpx.AsyncClient.get", ...)`` resolves.

from .. import register_adapter
from ..doi import parse_doi
from ..middleware import RetrievalClient
from ...state.models import Source

__all__ = ["OpenCitationsAdapter"]


_OPENCITATIONS_META_URL = "https://api.opencitations.net/meta/v1/metadata"
_USER_AGENT = "Plato/1.0 (mailto:plato.astropilot.ai@gmail.com)"
_BRACKETED_METADATA_RE = re.compile(r"\s*\[[^\]]+\]")


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _strip_bracketed_metadata(value: str | None) -> str | None:
    text = _text(value)
    if not text:
        return None
    cleaned = _BRACKETED_METADATA_RE.sub("", text).strip()
    return cleaned or text


def _coerce_year(pub_date: Any) -> int | None:
    if not isinstance(pub_date, str) or len(pub_date) < 4:
        return None
    try:
        year = int(pub_date[:4])
    except ValueError:
        return None
    return year if 1500 <= year <= 2100 else None


def _extract_authors(raw: Any) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []

    names: list[str] = []
    for part in raw.split(";"):
        cleaned = _strip_bracketed_metadata(part)
        if not cleaned:
            continue
        if "," in cleaned:
            family, given = [piece.strip() for piece in cleaned.split(",", 1)]
            if family and given:
                names.append(f"{given} {family}")
            else:
                names.append(cleaned)
        else:
            names.append(cleaned)
    return names


def _map_record_to_source(record: dict[str, Any], fallback_doi: str) -> Source | None:
    title = _text(record.get("title"))
    doi = parse_doi(record.get("id")) or fallback_doi
    if not title or not doi:
        return None

    venue = _strip_bracketed_metadata(record.get("venue"))
    publisher = _strip_bracketed_metadata(record.get("publisher"))

    return Source(
        id=f"opencitations:{doi}",
        doi=doi,
        title=title,
        authors=_extract_authors(record.get("author")),
        year=_coerce_year(record.get("pub_date")),
        venue=venue or publisher or _text(record.get("type")),
        url=f"https://doi.org/{doi}",
        retrieved_via="opencitations",
        fetched_at=datetime.now(timezone.utc),
    )


class OpenCitationsAdapter:
    """DOI-only SourceAdapter for OpenCitations Meta."""

    name = "opencitations"

    def __init__(
        self,
        *,
        base_url: str = _OPENCITATIONS_META_URL,
        user_agent: str = _USER_AGENT,
        timeout: float = 20.0,
    ) -> None:
        self._base_url = base_url
        self._user_agent = user_agent
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> list[Source]:
        if limit <= 0:
            return []
        doi = parse_doi(query)
        if not doi:
            return []

        identifier = quote(f"doi:{doi}", safe=":/._;()-")
        url = f"{self._base_url}/{identifier}"
        headers = {"User-Agent": self._user_agent}

        async with RetrievalClient(timeout=self._timeout, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, list):
            return []

        sources: list[Source] = []
        for record in payload[: max(1, int(limit))]:
            if not isinstance(record, dict):
                continue
            mapped = _map_record_to_source(record, doi)
            if mapped is not None:
                sources.append(mapped)
        return sources


register_adapter(OpenCitationsAdapter(), overwrite=True)
