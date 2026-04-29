"""Phase 2 contract tests for the SourceAdapter protocol and registry."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from plato.retrieval import (
    ADAPTER_REGISTRY,
    SourceAdapter,
    get_adapter,
    list_adapters,
    register_adapter,
)
from plato.state.models import Source


class _FakeAdapter:
    name = "fake-test-adapter"

    async def search(self, query: str, limit: int) -> list[Source]:
        return [
            Source(
                id=f"{self.name}-{i}",
                title=f"q={query} #{i}",
                retrieved_via="arxiv",  # acceptable literal for the contract test
                fetched_at=datetime.now(timezone.utc),
            )
            for i in range(min(limit, 2))
        ]


def test_protocol_is_satisfied_by_fake_adapter():
    fake = _FakeAdapter()
    assert isinstance(fake, SourceAdapter)


def test_register_and_get_adapter():
    fake = _FakeAdapter()
    register_adapter(fake, overwrite=True)
    assert "fake-test-adapter" in list_adapters()
    assert get_adapter("fake-test-adapter") is fake


def test_register_rejects_duplicate_without_overwrite():
    fake = _FakeAdapter()
    register_adapter(fake, overwrite=True)
    with pytest.raises(ValueError, match="already registered"):
        register_adapter(fake)


def test_get_adapter_unknown_raises():
    with pytest.raises(KeyError, match="Unknown adapter"):
        get_adapter("does-not-exist-xyz")
