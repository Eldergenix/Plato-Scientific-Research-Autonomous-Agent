"""
Phase 2 — shared scientific-research data model.

These Pydantic models are the *contract* the rest of Phase 2 builds on:
- Retrieval (R4) returns ``Source[]``.
- Citation validation (R3) emits ``ValidationResult`` per source.
- Claim extraction + evidence matrix (R5) emit ``Claim[]`` and
  ``EvidenceLink[]`` linking paper claims to source quotes.
- The SQLite store (``plato/state/store.py``) persists all four kinds.

Models are intentionally narrow and side-effect-free. Persistence is a
separate concern; serialization to JSON (for ``manifest.json`` sidecars)
is via Pydantic's standard ``model_dump(mode='json')``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RetrievedVia = Literal[
    "semantic_scholar",
    "arxiv",
    "openalex",
    "ads",
    "crossref",
    "pubmed",
]
"""Adapter that produced a ``Source``. Extend the literal as new adapters land."""


SupportLabel = Literal["supports", "refutes", "neutral", "unclear"]
StrengthLabel = Literal["weak", "moderate", "strong"]


class Source(BaseModel):
    """A literature source — a paper, preprint, or data set Plato has retrieved."""

    id: str = Field(description="Internal stable identifier (uuid or hash).")
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    semantic_scholar_id: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    pdf_url: str | None = None
    url: str | None = None
    retracted: bool = False
    retrieved_via: RetrievedVia
    fetched_at: datetime


class Claim(BaseModel):
    """An atomic claim with optional source provenance."""

    id: str
    text: str
    source_id: str | None = Field(
        default=None,
        description="Source paper that asserts the claim. None for claims drafted by Plato itself.",
    )
    quote_span: tuple[int, int] | None = Field(
        default=None,
        description="(start, end) char offsets into the source's abstract or full text.",
    )
    section: str | None = Field(
        default=None,
        description="Section the claim appears in: 'abstract' | 'results' | 'introduction' | etc.",
    )


class EvidenceLink(BaseModel):
    """Link from a Plato-drafted claim to a source claim, with support classification."""

    claim_id: str
    source_id: str
    support: SupportLabel
    strength: StrengthLabel
    quote_span: tuple[int, int] | None = None


class ValidationResult(BaseModel):
    """Result of running a ``Source`` through citation validation (R3)."""

    source_id: str
    doi_resolved: bool = False
    arxiv_resolved: bool = False
    url_alive: bool | None = None
    retracted: bool = False
    error: str | None = None
    checked_at: datetime


__all__ = [
    "Source",
    "Claim",
    "EvidenceLink",
    "ValidationResult",
    "RetrievedVia",
    "SupportLabel",
    "StrengthLabel",
]
