"""Phase 3 — R6: aggregate the reviewer-panel critiques.

The ``critique_aggregator`` LangGraph node reduces the four per-reviewer
critiques (stored under ``state['critiques']``) into a single
:class:`CritiqueDigest`: the maximum severity, a flat list of all issues, and
the current revision iteration. The digest drives the conditional redraft
loop in :func:`plato.paper_agents.routers.revision_router`.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from .parameters import GraphState


class CritiqueDigest(BaseModel):
    """Reduced view across all reviewers used to gate the redraft loop."""

    max_severity: int = Field(
        default=0,
        ge=0,
        le=5,
        description="Highest severity reported by any reviewer (0..5).",
    )
    issues: list[dict] = Field(
        default_factory=list,
        description="Flat list of all issues from all reviewers.",
    )
    iteration: int = Field(
        default=0,
        ge=0,
        description="Revision iteration this digest belongs to.",
    )


def _coerce_severity(value: Any) -> int:
    try:
        sev = int(value)
    except (TypeError, ValueError):
        return 0
    if sev < 0:
        return 0
    if sev > 5:
        return 5
    return sev


def critique_aggregator(state: GraphState, config: RunnableConfig):
    """Reduce ``state['critiques']`` into a single ``CritiqueDigest``.

    Computes ``max_severity`` across all reviewer outputs and concatenates
    every reviewer's issues (each tagged with the reviewer name) so the
    redraft node can address them in one pass.
    """
    critiques = state.get("critiques") or {}

    severities: list[int] = []
    issues: list[dict] = []
    for reviewer_name, critique in critiques.items():
        if not isinstance(critique, dict):
            continue
        severities.append(_coerce_severity(critique.get("severity", 0)))
        for entry in critique.get("issues", []) or []:
            if not isinstance(entry, dict):
                continue
            issues.append(
                {
                    "reviewer": reviewer_name,
                    "section": str(entry.get("section", "")),
                    "issue": str(entry.get("issue", "")),
                    "fix": str(entry.get("fix", "")),
                }
            )

    max_severity = max(severities) if severities else 0
    revision_state = state.get("revision_state") or {}
    iteration = int(revision_state.get("iteration", 0) or 0)

    digest = CritiqueDigest(
        max_severity=max_severity,
        issues=issues,
        iteration=iteration,
    )

    return {"critique_digest": digest.model_dump()}


__all__ = ["critique_aggregator", "CritiqueDigest"]
