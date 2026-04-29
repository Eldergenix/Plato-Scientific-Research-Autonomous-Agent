"""
Phase 3 — R7: Eval metrics.

The ``Metrics`` Pydantic model is the canonical per-task result schema.
It is written to ``evals/results/<task_id>/metrics.json`` and aggregated
into ``evals/results/summary.json``.

Pure functions in this module derive metrics from the Phase 2 data model
(``ValidationResult``, ``Claim``, ``EvidenceLink``) so the same code can
score both real Plato runs and unit-test fixtures without any LLM calls.
"""
from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field

from plato.state.models import Claim, EvidenceLink, ValidationResult


class Metrics(BaseModel):
    """Per-task evaluation metrics. One row per golden task per run."""

    citation_validation_rate: float = Field(
        description="Fraction of references with verified DOI/arxiv id.",
    )
    unsupported_claim_rate: float = Field(
        description="Fraction of claims without a 'supports' EvidenceLink.",
    )
    novelty_consistency: float | None = None
    referee_severity_max: int | None = None
    paper_coherence: float | None = Field(
        default=None, description="Judge score 0..5; None if no judge ran."
    )
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_seconds: float = 0.0
    tool_call_error_rate: float | None = None


def citation_validation_rate(validations: Iterable[ValidationResult]) -> float:
    """Fraction of ``ValidationResult`` rows that resolved to a DOI or arxiv id.

    Returns ``0.0`` for an empty input so the metric is well-defined even
    when a workflow produced no citations. Retracted papers are *not*
    counted as validated even if their identifiers resolve, since a
    retraction means the claim should not be relied on.
    """
    items = list(validations)
    if not items:
        return 0.0
    valid = sum(
        1
        for v in items
        if (v.doi_resolved or v.arxiv_resolved) and not v.retracted
    )
    return valid / len(items)


def unsupported_claim_rate(
    claims: Iterable[Claim],
    evidence_links: Iterable[EvidenceLink],
) -> float:
    """Fraction of claims with no ``support='supports'`` evidence link.

    Empty claim list → ``0.0`` (vacuously, no unsupported claims).
    """
    claim_list = list(claims)
    if not claim_list:
        return 0.0
    supported_ids = {
        link.claim_id for link in evidence_links if link.support == "supports"
    }
    unsupported = sum(1 for c in claim_list if c.id not in supported_ids)
    return unsupported / len(claim_list)


__all__ = [
    "Metrics",
    "citation_validation_rate",
    "unsupported_claim_rate",
]
