"""
Phase 2 — R3: citation validation pipeline.

The :class:`CitationValidator` cross-checks a :class:`~plato.state.models.Source`
against authoritative external services to detect hallucinated, dead, or
retracted citations:

- ``doi_resolved``    — Crossref ``/works/{doi}`` returns 200.
- ``arxiv_resolved``  — arXiv ``/abs/{id}`` returns 200.
- ``url_alive``       — HEAD on ``url``/``pdf_url`` returns 2xx/3xx.
- ``retracted``       — DOI in ``retraction_db`` (e.g. Retraction Watch CSV)
  OR Crossref payload contains an ``update-to`` entry with
  ``update-type == "retraction"``.

Each call is wrapped in try/except for httpx errors; failures populate the
:class:`~plato.state.models.ValidationResult.error` field rather than raising.

The validator owns its :class:`httpx.AsyncClient` only when one is not
injected; ``aclose()`` and the async context manager close only that
self-owned client. This makes it safe to share a single client across
multiple validators in production while still cleaning up in tests.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Literal, cast
from urllib.parse import quote

from defusedxml import ElementTree
import httpx

from plato.state.models import Source, ValidationResult
from plato.tools.citation_matching import (
    TITLE_MATCH_THRESHOLD,
    assessment_verdict,
    build_corrections,
    collapse_ws,
    compare_metadata,
    confidence_for,
    crossref_indicates_retraction,
    crossref_metadata,
    crossref_work_metadata,
    library_triage,
    needs_hallucination_check,
    normalize_assessment,
    normalize_doi,
    reverify_llm_metadata,
    status_for,
    title_similarity,
)
from plato.tools.citation_reports import build_validation_report, result_passes


_USER_AGENT = "Plato/1.0 citation-validator"
_DEFAULT_TIMEOUT_S = 10.0
_CROSSREF_WORKS = "https://api.crossref.org/works/{doi}"
_CROSSREF_SEARCH = "https://api.crossref.org/works?query.title={title}&rows=1"
_ARXIV_ABS = "https://export.arxiv.org/abs/{arxiv_id}"
_ARXIV_API = "https://export.arxiv.org/api/query?id_list={arxiv_id}"
_LOGGER = logging.getLogger(__name__)
HallucinationAssessor = Callable[[Source, list[dict[str, Any]]], Any]


class CitationValidator:
    """Validate :class:`Source` citations against Crossref, arXiv, and live URLs."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        retraction_db: set[str] | None = None,
        hallucination_assessor: HallucinationAssessor | None = None,
    ) -> None:
        if http_client is None:
            self._http = httpx.AsyncClient(
                headers={"User-Agent": _USER_AGENT},
                timeout=_DEFAULT_TIMEOUT_S,
                follow_redirects=True,
            )
            self._owns_client = True
        else:
            self._http = http_client
            self._owns_client = False
        self.retraction_db: set[str] = (
            set()
            if retraction_db is None
            else {normalize_doi(d) for d in retraction_db}
        )
        self.hallucination_assessor = hallucination_assessor

    # -- public API ---------------------------------------------------------

    async def validate(self, source: Source) -> ValidationResult:
        """Validate a single :class:`Source` and return a :class:`ValidationResult`.

        Network errors are absorbed and surfaced via the ``error`` field;
        per-check booleans default to ``False`` (or ``None`` for ``url_alive``
        on timeout) when their respective service cannot be reached.
        """
        transport_errors: list[str] = []
        doi_resolved = False
        arxiv_resolved = False
        url_alive: bool | None = None
        retracted = False
        crossref_payload: dict[str, Any] | None = None
        matched_metadata: dict[str, Any] | None = None
        matched_source: str | None = None
        url_to_check = source.url or source.pdf_url

        # --- DOI / Crossref -------------------------------------------------
        if source.doi:
            normalized_doi = normalize_doi(source.doi)
            try:
                resp = await self._http.get(_CROSSREF_WORKS.format(doi=normalized_doi))
            except httpx.HTTPError as exc:
                transport_errors.append(f"crossref: {type(exc).__name__}: {exc}")
            else:
                if resp.status_code == 200:
                    doi_resolved = True
                    try:
                        crossref_payload = resp.json()
                        matched_metadata = crossref_metadata(crossref_payload)
                        matched_source = "crossref"
                    except ValueError as exc:
                        transport_errors.append(f"crossref-json: {exc}")
                elif resp.status_code == 404:
                    doi_resolved = False
                else:
                    transport_errors.append(f"crossref: HTTP {resp.status_code}")

            # Retraction Watch DB lookup uses the normalized DOI.
            if normalized_doi in self.retraction_db:
                retracted = True
        elif source.title and not source.arxiv_id and not url_to_check:
            found = await self._search_crossref_by_title(source.title)
            if found is not None:
                matched_metadata = found
                matched_source = "crossref_title"

        # --- arXiv ----------------------------------------------------------
        if source.arxiv_id:
            try:
                resp = await self._http.head(
                    _ARXIV_ABS.format(arxiv_id=source.arxiv_id)
                )
            except httpx.HTTPError as exc:
                transport_errors.append(f"arxiv: {type(exc).__name__}: {exc}")
            else:
                arxiv_resolved = resp.status_code == 200
            arxiv_metadata = await self._resolve_arxiv_metadata(source.arxiv_id)
            if arxiv_metadata is not None:
                matched_metadata = arxiv_metadata
                matched_source = "arxiv"

        # --- URL liveness ---------------------------------------------------
        if url_to_check:
            try:
                resp = await self._http.head(url_to_check)
            except httpx.TimeoutException as exc:
                url_alive = None
                transport_errors.append(f"url-timeout: {type(exc).__name__}: {exc}")
            except httpx.HTTPError as exc:
                url_alive = False
                transport_errors.append(f"url: {type(exc).__name__}: {exc}")
            else:
                code = resp.status_code
                if 200 <= code < 400:
                    url_alive = True
                else:
                    url_alive = False

        # --- Crossref retraction signal ------------------------------------
        if not retracted and crossref_payload is not None:
            retracted = crossref_indicates_retraction(crossref_payload)

        issues, warnings = compare_metadata(
            source,
            matched_metadata,
            doi_resolved=doi_resolved,
            arxiv_resolved=arxiv_resolved,
            url_alive=url_alive,
            retracted=retracted,
        )
        hallucination_assessment = await self._assess_hallucination(source, issues)
        issues, warnings, matched_metadata, matched_source = reverify_llm_metadata(
            source,
            issues,
            warnings,
            matched_metadata,
            matched_source,
            hallucination_assessment,
        )
        verdict = assessment_verdict(issues, hallucination_assessment)
        confidence = confidence_for(verdict, issues, warnings, hallucination_assessment)
        status = status_for(issues, warnings, verdict)
        corrections = build_corrections(source, matched_metadata or {})
        tags, folder, notes = library_triage(source, issues, warnings, verdict)

        return ValidationResult(
            source_id=source.id,
            doi_resolved=doi_resolved,
            arxiv_resolved=arxiv_resolved,
            url_alive=url_alive,
            retracted=retracted,
            status=cast(
                Literal["verified", "warning", "unverified", "error", "hallucination"],
                status,
            ),
            verdict=cast(Literal["UNLIKELY", "UNCERTAIN", "LIKELY"], verdict),
            confidence=confidence,
            matched_source=matched_source,
            matched_metadata=matched_metadata,
            issues=issues,
            warnings=warnings,
            hallucination_assessment=hallucination_assessment,
            corrections=corrections,
            tags=tags,
            folder=folder,
            notes=notes,
            error="; ".join(transport_errors) if transport_errors else None,
            checked_at=datetime.now(timezone.utc),
        )

    async def validate_batch(
        self,
        sources: list[Source],
        concurrency: int = 5,
    ) -> list[ValidationResult]:
        """Validate ``sources`` with bounded concurrency via ``asyncio.Semaphore``.

        Results are returned in the same order as ``sources``.
        """
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        sem = asyncio.Semaphore(concurrency)

        async def _bounded(src: Source) -> ValidationResult:
            async with sem:
                return await self.validate(src)

        return await asyncio.gather(*(_bounded(s) for s in sources))

    async def aclose(self) -> None:
        """Close the internal httpx client iff this validator created it."""
        if self._owns_client:
            await self._http.aclose()

    # -- async context manager ---------------------------------------------

    async def __aenter__(self) -> "CitationValidator":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def _search_crossref_by_title(self, title: str) -> dict[str, Any] | None:
        try:
            resp = await self._http.get(_CROSSREF_SEARCH.format(title=quote(title)))
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            items = resp.json().get("message", {}).get("items") or []
        except ValueError:
            return None
        if not items:
            return None
        candidate = crossref_work_metadata(items[0])
        similarity = title_similarity(title, str(candidate.get("title") or ""))
        return candidate if similarity >= TITLE_MATCH_THRESHOLD else None

    async def _resolve_arxiv_metadata(self, arxiv_id: str) -> dict[str, Any] | None:
        try:
            resp = await self._http.get(_ARXIV_API.format(arxiv_id=quote(arxiv_id)))
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            root = ElementTree.fromstring(resp.text)
        except ElementTree.ParseError:
            return None
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        title = collapse_ws(entry.findtext("atom:title", default="", namespaces=ns))
        authors = [
            collapse_ws(node.findtext("atom:name", default="", namespaces=ns))
            for node in entry.findall("atom:author", ns)
        ]
        year = None
        published = entry.findtext("atom:published", default="", namespaces=ns)
        if published:
            match = re.search(r"\d{4}", published)
            if match:
                year = int(match.group(0))
        return {
            "title": title,
            "authors": [a for a in authors if a],
            "year": year,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "arxiv_id": arxiv_id,
        }

    async def _assess_hallucination(
        self,
        source: Source,
        issues: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not issues or not needs_hallucination_check(issues):
            return None
        if self.hallucination_assessor is None:
            return {
                "verdict": "UNCERTAIN",
                "explanation": (
                    "Reference met deterministic hallucination pre-filter criteria, "
                    "but no hallucination LLM assessor was configured."
                ),
                "link": None,
            }
        try:
            result = self.hallucination_assessor(source, issues)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            _LOGGER.exception("Hallucination assessor failed for source %s", source.id)
            return normalize_assessment(None)
        return normalize_assessment(result)


__all__ = [
    "CitationValidator",
    "build_validation_report",
    "result_passes",
]
