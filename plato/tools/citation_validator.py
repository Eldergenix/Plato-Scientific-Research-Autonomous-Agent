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
from datetime import datetime, timezone
from typing import Any

import httpx

from plato.state.models import Source, ValidationResult


_USER_AGENT = "Plato/1.0 citation-validator"
_DEFAULT_TIMEOUT_S = 10.0
_CROSSREF_WORKS = "https://api.crossref.org/works/{doi}"
_ARXIV_ABS = "https://export.arxiv.org/abs/{arxiv_id}"


class CitationValidator:
    """Validate :class:`Source` citations against Crossref, arXiv, and live URLs."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        retraction_db: set[str] | None = None,
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
            set() if retraction_db is None else {_normalize_doi(d) for d in retraction_db}
        )

    # -- public API ---------------------------------------------------------

    async def validate(self, source: Source) -> ValidationResult:
        """Validate a single :class:`Source` and return a :class:`ValidationResult`.

        Network errors are absorbed and surfaced via the ``error`` field;
        per-check booleans default to ``False`` (or ``None`` for ``url_alive``
        on timeout) when their respective service cannot be reached.
        """
        errors: list[str] = []
        doi_resolved = False
        arxiv_resolved = False
        url_alive: bool | None = None
        retracted = False
        crossref_payload: dict[str, Any] | None = None

        # --- DOI / Crossref -------------------------------------------------
        if source.doi:
            normalized_doi = _normalize_doi(source.doi)
            try:
                resp = await self._http.get(
                    _CROSSREF_WORKS.format(doi=normalized_doi)
                )
            except httpx.HTTPError as exc:
                errors.append(f"crossref: {type(exc).__name__}: {exc}")
            else:
                if resp.status_code == 200:
                    doi_resolved = True
                    try:
                        crossref_payload = resp.json()
                    except ValueError as exc:
                        errors.append(f"crossref-json: {exc}")
                elif resp.status_code == 404:
                    doi_resolved = False
                else:
                    errors.append(f"crossref: HTTP {resp.status_code}")

            # Retraction Watch DB lookup uses the normalized DOI.
            if normalized_doi in self.retraction_db:
                retracted = True

        # --- arXiv ----------------------------------------------------------
        if source.arxiv_id:
            try:
                resp = await self._http.head(
                    _ARXIV_ABS.format(arxiv_id=source.arxiv_id)
                )
            except httpx.HTTPError as exc:
                errors.append(f"arxiv: {type(exc).__name__}: {exc}")
            else:
                arxiv_resolved = resp.status_code == 200

        # --- URL liveness ---------------------------------------------------
        url_to_check = source.url or source.pdf_url
        if url_to_check:
            try:
                resp = await self._http.head(url_to_check)
            except httpx.TimeoutException as exc:
                url_alive = None
                errors.append(f"url-timeout: {type(exc).__name__}: {exc}")
            except httpx.HTTPError as exc:
                url_alive = False
                errors.append(f"url: {type(exc).__name__}: {exc}")
            else:
                code = resp.status_code
                if 200 <= code < 400:
                    url_alive = True
                else:
                    url_alive = False

        # --- Crossref retraction signal ------------------------------------
        if not retracted and crossref_payload is not None:
            retracted = _crossref_indicates_retraction(crossref_payload)

        return ValidationResult(
            source_id=source.id,
            doi_resolved=doi_resolved,
            arxiv_resolved=arxiv_resolved,
            url_alive=url_alive,
            retracted=retracted,
            error="; ".join(errors) if errors else None,
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


# --- helpers --------------------------------------------------------------


def _normalize_doi(doi: str) -> str:
    """Strip resolver prefixes and lowercase a DOI for stable comparison.

    Examples
    --------
    >>> _normalize_doi("https://doi.org/10.1000/Foo")
    '10.1000/foo'
    >>> _normalize_doi("doi:10.1000/Foo")
    '10.1000/foo'
    """
    s = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
            break
    return s.lower()


def _crossref_indicates_retraction(payload: dict[str, Any]) -> bool:
    """Return True if a Crossref ``/works/{doi}`` payload signals a retraction.

    Crossref encodes retraction notices as an ``update-to`` array on the
    *retracting* notice's record; each entry has an ``update-type`` of
    ``"retraction"`` (other types include ``"correction"``, ``"erratum"``).
    The Crossref API wraps the work in ``{"message": {...}}``, so we look in
    both the top level and ``message`` for robustness.
    """
    candidates: list[dict[str, Any]] = [payload]
    msg = payload.get("message")
    if isinstance(msg, dict):
        candidates.append(msg)

    for body in candidates:
        updates = body.get("update-to")
        if not isinstance(updates, list):
            continue
        for entry in updates:
            if not isinstance(entry, dict):
                continue
            update_type = entry.get("update-type") or entry.get("type")
            if isinstance(update_type, str) and update_type.lower() == "retraction":
                return True
    return False


__all__ = ["CitationValidator"]
