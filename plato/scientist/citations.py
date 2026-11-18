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
