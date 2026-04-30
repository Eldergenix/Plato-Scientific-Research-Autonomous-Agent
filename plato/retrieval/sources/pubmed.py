"""
PubMed retrieval adapter.

Hits NCBI's E-utilities API (``esearch.fcgi`` → ``esummary.fcgi`` →
``efetch.fcgi``) and maps the response into :class:`plato.state.models.Source`
records. ``esummary`` provides metadata; ``efetch`` provides abstracts
(without it the downstream ``claim_extractor`` has nothing to work with
for biology-domain runs).

Auto-registers itself in the adapter registry on import.

An optional ``NCBI_API_KEY`` environment variable raises the per-IP rate
limit from 3 req/s to 10 req/s. The endpoint works without a key.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx

from .. import register_adapter
from ...state.models import Source
from ..doi import normalize_doi

__all__ = ["PubMedAdapter"]


_EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_ESEARCH_URL = f"{_EUTILS_BASE_URL}/esearch.fcgi"
_ESUMMARY_URL = f"{_EUTILS_BASE_URL}/esummary.fcgi"
_EFETCH_URL = f"{_EUTILS_BASE_URL}/efetch.fcgi"


def _read_api_key() -> str | None:
    """Optional API key for higher rate limits; bare endpoint works without one."""
    key = os.environ.get("NCBI_API_KEY")
    if key and key.strip():
        return key.strip()
    return None


def _coerce_year(pubdate: Any) -> int | None:
    """Pull a 4-digit year out of an esummary ``pubdate`` field."""
    if not isinstance(pubdate, str) or not pubdate.strip():
        return None
    head = pubdate.strip()[:4]
    try:
        return int(head)
    except ValueError:
        return None


def _extract_doi_from_articleids(article: dict[str, Any]) -> str | None:
    """Walk an esummary article's ``articleids`` list looking for a DOI entry.

    The esummary payload encodes external identifiers as
    ``[{"idtype": "doi", "value": "10.1234/xyz"}, ...]``. We pick the first
    DOI entry, normalize it, and return ``None`` if absent or unparseable.
    """
    raw = article.get("articleids")
    if not isinstance(raw, list):
        return None
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if entry.get("idtype") == "doi":
            value = entry.get("value")
            if isinstance(value, str) and value.strip():
                return normalize_doi(value)
    return None


def _extract_doi(article: dict[str, Any]) -> str | None:
    """Try ``elocationid`` first (the modern field), then fall back to ``articleids``."""
    elocation = article.get("elocationid")
    if isinstance(elocation, str) and "doi" in elocation.lower():
        normalized = normalize_doi(elocation)
        if normalized:
            return normalized
    return _extract_doi_from_articleids(article)


def _extract_authors(article: dict[str, Any]) -> list[str]:
    """Pull ``[{"name": "Doe J", ...}, ...]`` into a flat list of names."""
    raw = article.get("authors")
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _extract_venue(article: dict[str, Any]) -> str | None:
    """Prefer the full journal name; fall back to the abbreviated ``source`` field."""
    full = article.get("fulljournalname")
    if isinstance(full, str) and full.strip():
        return full.strip()
    short = article.get("source")
    if isinstance(short, str) and short.strip():
        return short.strip()
    return None


def _map_article_to_source(
    pmid: str,
    article: dict[str, Any],
    abstract: str | None = None,
) -> Source | None:
    """Map one esummary article entry to a :class:`Source`. Returns None if unusable.

    ``abstract`` is fetched separately via ``efetch`` and threaded in so we
    don't pay the second round-trip when we already know the article is
    unusable (e.g. missing title).
    """
    title = article.get("title")
    if not isinstance(title, str) or not title.strip():
        return None

    return Source(
        id=f"pubmed:{pmid}",
        doi=_extract_doi(article),
        title=title.strip(),
        authors=_extract_authors(article),
        year=_coerce_year(article.get("pubdate")),
        venue=_extract_venue(article),
        abstract=abstract,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        retrieved_via="pubmed",
        fetched_at=datetime.now(timezone.utc),
    )


def _extract_abstracts_from_efetch(xml_text: str) -> dict[str, str]:
    """Parse a PubMed efetch XML response into ``{pmid: abstract_text}``.

    The PubMed XML schema nests abstracts under
    ``PubmedArticle/MedlineCitation/Article/Abstract/AbstractText`` (the
    AbstractText node may repeat with different ``Label`` attributes for
    structured abstracts; we concatenate them).

    Tolerant of malformed XML — returns ``{}`` on parse error.
    """
    if not isinstance(xml_text, str) or not xml_text.strip():
        return {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}

    out: dict[str, str] = {}
    for article in root.iter("PubmedArticle"):
        pmid_el = article.find(".//MedlineCitation/PMID")
        if pmid_el is None or not (pmid_el.text or "").strip():
            continue
        pmid = pmid_el.text.strip()
        parts: list[str] = []
        for at in article.iter("AbstractText"):
            label = (at.attrib.get("Label") or "").strip()
            text = "".join(at.itertext()).strip()
            if not text:
                continue
            parts.append(f"{label}: {text}" if label else text)
        if parts:
            out[pmid] = "\n".join(parts)
    return out


class PubMedAdapter:
    """SourceAdapter hitting NCBI E-utilities for PubMed records."""

    name = "pubmed"

    def __init__(
        self,
        *,
        esearch_url: str = _ESEARCH_URL,
        esummary_url: str = _ESUMMARY_URL,
        efetch_url: str = _EFETCH_URL,
        timeout: float = 10.0,
        fetch_abstracts: bool = True,
    ) -> None:
        self._esearch_url = esearch_url
        self._esummary_url = esummary_url
        self._efetch_url = efetch_url
        self._timeout = timeout
        self._fetch_abstracts = fetch_abstracts

    async def search(self, query: str, limit: int) -> list[Source]:
        """Search PubMed for ``query`` and return up to ``limit`` Sources.

        Hits ``esearch`` for PMIDs, ``esummary`` for metadata, and
        ``efetch`` for abstracts when ``fetch_abstracts=True``. The efetch
        leg is best-effort — if it fails (rate limit, transient error)
        the adapter still returns the metadata-only Sources rather than
        propagating the failure.
        """
        retmax = max(1, int(limit))
        api_key = _read_api_key()
        key_suffix = f"&api_key={quote_plus(api_key)}" if api_key else ""

        esearch_url = (
            f"{self._esearch_url}"
            f"?db=pubmed"
            f"&term={quote_plus(query)}"
            f"&retmode=json"
            f"&retmax={retmax}"
            f"{key_suffix}"
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            esearch_response = await client.get(esearch_url)
            esearch_response.raise_for_status()
            esearch_payload = esearch_response.json()

            pmids = _extract_pmids(esearch_payload)
            if not pmids:
                return []

            esummary_url = (
                f"{self._esummary_url}"
                f"?db=pubmed"
                f"&id={','.join(pmids)}"
                f"&retmode=json"
                f"{key_suffix}"
            )
            esummary_response = await client.get(esummary_url)
            esummary_response.raise_for_status()
            esummary_payload = esummary_response.json()

            abstracts: dict[str, str] = {}
            if self._fetch_abstracts:
                efetch_url = (
                    f"{self._efetch_url}"
                    f"?db=pubmed"
                    f"&id={','.join(pmids)}"
                    f"&retmode=xml"
                    f"&rettype=abstract"
                    f"{key_suffix}"
                )
                try:
                    efetch_response = await client.get(efetch_url)
                    efetch_response.raise_for_status()
                    abstracts = _extract_abstracts_from_efetch(efetch_response.text)
                except httpx.HTTPError:
                    # Best-effort: missing abstracts shouldn't fail the run.
                    abstracts = {}

        return _map_esummary_payload(esummary_payload, pmids, abstracts)


def _extract_pmids(payload: dict[str, Any]) -> list[str]:
    """Pull the ``esearchresult.idlist`` PMID list out of an esearch payload."""
    result = payload.get("esearchresult") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return []
    raw = result.get("idlist")
    if not isinstance(raw, list):
        return []
    return [pmid for pmid in raw if isinstance(pmid, str) and pmid.strip()]


def _map_esummary_payload(
    payload: dict[str, Any],
    pmids: list[str],
    abstracts: dict[str, str] | None = None,
) -> list[Source]:
    """Iterate ``payload.result[<pmid>]`` in the original PMID order."""
    if not isinstance(payload, dict):
        return []
    result = payload.get("result")
    if not isinstance(result, dict):
        return []

    abstracts = abstracts or {}
    sources: list[Source] = []
    for pmid in pmids:
        article = result.get(pmid)
        if not isinstance(article, dict):
            continue
        mapped = _map_article_to_source(pmid, article, abstract=abstracts.get(pmid))
        if mapped is not None:
            sources.append(mapped)
    return sources


# Auto-register on import. ``overwrite=True`` is intentional: importing
# this module IS the registration mechanism, and a re-import (e.g.
# from a test fixture that clears + restores the registry) should
# repopulate the slot rather than raising. Third-party adapters that
# want to fail-loud on name collision should call ``register_adapter``
# directly with ``overwrite=False``.
register_adapter(PubMedAdapter(), overwrite=True)
