"""Phase 2 contract tests for the shared scientific-research models."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from plato.state.models import (
    Claim,
    EvidenceLink,
    Source,
    ValidationResult,
)


def test_source_round_trip():
    s = Source(
        id="src-001",
        doi="10.1234/example",
        arxiv_id="2401.12345",
        title="Test paper",
        authors=["Alice", "Bob"],
        year=2025,
        retrieved_via="arxiv",
        fetched_at=datetime.now(timezone.utc),
    )
    payload = s.model_dump(mode="json")
    restored = Source.model_validate(payload)
    assert restored.doi == "10.1234/example"
    assert restored.authors == ["Alice", "Bob"]


def test_source_rejects_unknown_retrieved_via():
    with pytest.raises(ValidationError):
        Source(
            id="x",
            title="t",
            retrieved_via="nasa-grants",  # type: ignore[arg-type]
            fetched_at=datetime.now(timezone.utc),
        )


def test_claim_defaults():
    c = Claim(id="c1", text="atoms exist")
    assert c.source_id is None
    assert c.quote_span is None
    assert c.section is None


def test_evidence_link_supports_label_validation():
    EvidenceLink(
        claim_id="c1",
        source_id="s1",
        support="supports",
        strength="strong",
    )
    with pytest.raises(ValidationError):
        EvidenceLink(
            claim_id="c1",
            source_id="s1",
            support="maybe",  # type: ignore[arg-type]
            strength="strong",
        )


def test_validation_result_minimal():
    v = ValidationResult(source_id="s1", checked_at=datetime.now(timezone.utc))
    assert v.doi_resolved is False
    assert v.retracted is False
