"""
NASA ADS (Astrophysics Data System) source adapter.

Implements :class:`plato.retrieval.SourceAdapter` against the public ADS
search API. ADS is the astro-default literature source for Plato; the
adapter is auto-registered on import so the retrieval orchestrator can
look it up by ``name == "ads"``.

The adapter requires an API token, read from ``ADS_API_KEY`` (preferred)
or ``ADS_DEV_KEY`` (legacy). When neither is set, the adapter still
imports cleanly so callers can introspect the registry without
credentials, but :meth:`ADSAdapter.search` is a no-op that returns ``[]``
after emitting a one-time :class:`RuntimeWarning`.
"""
from __future__ import annotations

import os
import re
import warnings
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx  # noqa: F401  # kept so ``patch("httpx.AsyncClient.get", ...)`` still resolves.

from .. import register_adapter
from ..middleware import RetrievalClient
from ...state.models import Source


_ADS_SEARCH_URL = "https://api.adsabs.harvard.edu/v1/search/query"
_ADS_FIELDS = "bibcode,title,author,year,doi,abstract,pub,arxiv_class,identifier"
_ARXIV_IDENTIFIER_RE = re.compile(r"^arxiv:(\d{4}\.\d{4,5})$", re.IGNORECASE)


def _read_token() -> str | None:
    """Return the ADS API token, preferring ``ADS_API_KEY`` over ``ADS_DEV_KEY``."""
    return os.environ.get("ADS_API_KEY") or os.environ.get("ADS_DEV_KEY")


def _extract_arxiv_id(identifiers: list[str] | None) -> str | None:
    """Return the first ``arxiv:NNNN.NNNNN`` style identifier, if any."""
    if not identifiers:
        return None
    for ident in identifiers:
        if not isinstance(ident, str):
            continue
        match = _ARXIV_IDENTIFIER_RE.match(ident.strip())
        if match:
            return match.group(1)
    return None


def _coerce_year(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return int(str(raw).strip()[:4])
    except (TypeError, ValueError):
        return None


def _doc_to_source(doc: dict[str, Any]) -> Source | None:
    """Map a single ADS ``response.docs`` entry to a :class:`Source`. Returns ``None`` if unusable."""
    bibcode = doc.get("bibcode")
    if not bibcode:
        return None

    titles = doc.get("title") or []
    title = titles[0] if isinstance(titles, list) and titles else (titles if isinstance(titles, str) else "")
    if not title:
        # ADS records always have a title; if missing, skip the row to keep contract clean.
        return None

    authors_raw = doc.get("author") or []
    if isinstance(authors_raw, str):
        authors: list[str] = [authors_raw]
    elif isinstance(authors_raw, list):
        authors = [a for a in authors_raw if isinstance(a, str)]
    else:
        authors = []

    doi_list = doc.get("doi") or []
    doi: str | None = None
    if isinstance(doi_list, list) and doi_list:
        first = doi_list[0]
        if isinstance(first, str) and first.strip():
            doi = first.strip().lower()
    elif isinstance(doi_list, str) and doi_list.strip():
        doi = doi_list.strip().lower()

    abstract = doc.get("abstract")
    if abstract is not None and not isinstance(abstract, str):
        abstract = None

    venue = doc.get("pub")
    if venue is not None and not isinstance(venue, str):
        venue = None

    arxiv_id = _extract_arxiv_id(doc.get("identifier"))

    return Source(
        id=f"ads:{bibcode}",
        doi=doi,
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        year=_coerce_year(doc.get("year")),
        venue=venue,
        abstract=abstract,
        retrieved_via="ads",
        fetched_at=datetime.now(timezone.utc),
    )


class ADSAdapter:
    """SourceAdapter for NASA ADS. Auto-registered on import."""

    name = "ads"

    def __init__(self) -> None:
        self._warned_no_token = False

    async def search(self, query: str, limit: int) -> list[Source]:
        token = _read_token()
        if not token:
            if not self._warned_no_token:
                warnings.warn(
                    "ADS_API_KEY not set; ADS adapter is no-op",
                    RuntimeWarning,
                    stacklevel=2,
                )
                self._warned_no_token = True
            return []

        params = {
            "q": query,
            "rows": str(limit),
            "fl": _ADS_FIELDS,
        }
        url = f"{_ADS_SEARCH_URL}?{urlencode(params)}"
        headers = {"Authorization": f"Bearer {token}"}

        async with RetrievalClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()

        docs = (payload or {}).get("response", {}).get("docs") or []
        sources: list[Source] = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            mapped = _doc_to_source(doc)
            if mapped is not None:
                sources.append(mapped)
        return sources


# Auto-register on import. ``overwrite=True`` keeps re-imports (e.g. test
# reloads) idempotent; the registry is a module-level dict so the second
# import shouldn't crash the suite.
register_adapter(ADSAdapter(), overwrite=True)


__all__ = ["ADSAdapter"]
