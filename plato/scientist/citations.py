"""Citation and retraction checks for papers the scientist retrieves.

Every paper is checked once, when the literature scout finds it, with the library's
:class:`plato.tools.citation_validator.CitationValidator`: the DOI must resolve (Crossref,
else the doi.org handle API for DataCite and other agencies), arXiv ids must resolve,
and Crossref's retraction records (``updated-by``/``update-to``, which include Retraction
Watch data) must not mark it retracted. Retracted papers and papers whose DOI resolves
to a different work are excluded from the campaign, so they can neither seed hypotheses
nor be cited.

Checks are best effort: a source the checker cannot reach is recorded as ``unchecked``
and kept, because an outage of Crossref must not empty the literature stage.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from plato.state.models import Source
from plato.tools.citation_validator import CitationValidator

logger = logging.getLogger(__name__)

_USER_AGENT = "Plato-Scientist/1.0 (citation checks; +https://jarvisos.xyz)"
# Issues that mean the record points at a different work than the one retrieved.
_WRONG_WORK = frozenset({"title_mismatch", "doi_conflict", "arxiv_conflict"})


def summarize(result: Any) -> dict[str, Any]:
    """Compact, JSON-safe summary of a ValidationResult."""
    issues = [i.get("type") for i in (result.issues or []) if isinstance(i, dict)]
    return {
        "status": result.status,
        "retracted": bool(result.retracted),
        "doi_resolved": bool(result.doi_resolved),
        "arxiv_resolved": bool(result.arxiv_resolved),
        "url_alive": result.url_alive,
        "matched_source": result.matched_source,
        "issues": sorted({i for i in issues if i}),
        "checked_at": result.checked_at.isoformat(),
    }


def unchecked(reason: str) -> dict[str, Any]:
    return {
        "status": "unchecked",
        "retracted": False,
        "issues": [],
        "error": reason[:300],
        "checked_at": datetime.now(UTC).isoformat(),
    }


def exclusion_reason(check: dict[str, Any] | None) -> str | None:
    """Why a checked paper must not be used, or None when it may be."""
    if not check:
        return None
    if check.get("retracted"):
        return "retracted"
    if check.get("status") == "hallucination":
        return "not found in any registry"
    wrong = sorted(set(check.get("issues") or []) & _WRONG_WORK)
    if wrong:
        return "identifier resolves to a different work (" + ", ".join(wrong) + ")"
    return None


async def check_sources(
    sources: list[Source],
    *,
    concurrency: int = 6,
    per_source_timeout: float = 30.0,
    http_client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Check each source; results are in input order and never raise."""
    if not sources:
        return []
    client = http_client or httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT}, timeout=10.0, follow_redirects=True
    )
    validator = CitationValidator(http_client=client)
    sem = asyncio.Semaphore(concurrency)

    async def one(src: Source) -> dict[str, Any]:
        async with sem:
            try:
                result = await asyncio.wait_for(
                    validator.validate(src), per_source_timeout
                )
            except TimeoutError:
                return unchecked("timed out")
            except Exception as exc:  # noqa: BLE001 - a checker bug must not stop research
                logger.warning("citation check failed for %r: %s", src.title, exc)
                return unchecked(f"{type(exc).__name__}: {exc}")
            return summarize(result)

    try:
        return list(await asyncio.gather(*(one(s) for s in sources)))
    finally:
        if http_client is None:
            await client.aclose()


# ----------------------------------------------------------------------------- abstracts
# A paper is citable only with an abstract: the claim-evidence matrix judges every citation
# against the cited abstract, so a paper without one makes each claim citing it
# "unsupported" by construction. Abstracts shorter than this are titles or stubs.
MIN_ABSTRACT_CHARS = 80
_OPENALEX_WORKS = "https://api.openalex.org/works"
_ARXIV_API = "https://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"


def has_abstract(text: str | None) -> bool:
    return len((text or "").strip()) >= MIN_ABSTRACT_CHARS


def _openalex_abstract(inverted: dict[str, list[int]] | None) -> str:
    if not inverted:
        return ""
    words = sorted((i, w) for w, idxs in inverted.items() for i in idxs or [])
    return " ".join(w for _, w in words)


def _bare_doi(doi: str | None) -> str:
    d = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        d = d.removeprefix(prefix)
    return d


async def _openalex_by_doi(
    client: httpx.AsyncClient, dois: list[str]
) -> dict[str, str]:
    found: dict[str, str] = {}
    for i in range(0, len(dois), 50):  # OpenAlex OR-filters take up to 50 values
        batch = dois[i : i + 50]
        resp = await client.get(
            _OPENALEX_WORKS,
            params={
                "filter": "doi:" + "|".join(batch),
                "select": "doi,abstract_inverted_index",
                "per-page": "50",
            },
        )
        resp.raise_for_status()
        for work in resp.json().get("results", []):
            text = _openalex_abstract(work.get("abstract_inverted_index"))
            if has_abstract(text):
                found[_bare_doi(work.get("doi"))] = text
    return found


async def _arxiv_by_id(client: httpx.AsyncClient, ids: list[str]) -> dict[str, str]:
    from defusedxml import ElementTree

    found: dict[str, str] = {}
    for i in range(0, len(ids), 50):
        batch = ids[i : i + 50]
        resp = await client.get(
            _ARXIV_API, params={"id_list": ",".join(batch), "max_results": "50"}
        )
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)
        for entry in root.iter(f"{_ATOM}entry"):
            url = (entry.findtext(f"{_ATOM}id") or "").rsplit("/abs/", 1)[-1]
            text = " ".join((entry.findtext(f"{_ATOM}summary") or "").split())
            if has_abstract(text):
                found[_arxiv_base(url)] = text
    return found


def _arxiv_base(arxiv_id: str | None) -> str:
    a = (arxiv_id or "").strip()
    for prefix in ("arxiv:", "arXiv:"):
        a = a.removeprefix(prefix)
    head, _, tail = a.rpartition("v")
    return head if head and tail.isdigit() else a


async def fetch_missing_abstracts(
    sources: list[Any],
    *,
    timeout: float = 20.0,
    http_client: httpx.AsyncClient | None = None,
) -> list[str | None]:
    """Abstract for each source that lacks one (OpenAlex by DOI, then arXiv by id), in
    input order; None where none was found or the source already had one. Never raises:
    a registry outage leaves the paper without an abstract, and so not citable."""
    out: list[str | None] = [None] * len(sources)
    missing = [i for i, s in enumerate(sources) if not has_abstract(s.abstract)]
    if not missing:
        return out
    client = http_client or httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT}, timeout=10.0, follow_redirects=True
    )
    try:
        dois = sorted({_bare_doi(sources[i].doi) for i in missing if sources[i].doi})
        by_doi: dict[str, str] = {}
        if dois:
            try:
                by_doi = await asyncio.wait_for(_openalex_by_doi(client, dois), timeout)
            except Exception as exc:  # noqa: BLE001 - best effort
                logger.warning("OpenAlex abstract lookup failed: %s", exc)
        for i in missing:
            out[i] = by_doi.get(_bare_doi(sources[i].doi)) if sources[i].doi else None
        arxiv = sorted(
            {
                _arxiv_base(getattr(sources[i], "arxiv_id", None))
                for i in missing
                if out[i] is None and getattr(sources[i], "arxiv_id", None)
            }
        )
        if arxiv:
            try:
                by_arxiv = await asyncio.wait_for(_arxiv_by_id(client, arxiv), timeout)
            except Exception as exc:  # noqa: BLE001 - best effort
                logger.warning("arXiv abstract lookup failed: %s", exc)
                by_arxiv = {}
            for i in missing:
                aid = getattr(sources[i], "arxiv_id", None)
                if out[i] is None and aid:
                    out[i] = by_arxiv.get(_arxiv_base(aid))
        return out
    finally:
        if http_client is None:
            await client.aclose()
