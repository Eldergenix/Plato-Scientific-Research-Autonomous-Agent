"""Phase 2 (R4) tests for ``plato.retrieval.orchestrator.retrieve``."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from plato.domain import DomainProfile
from plato.retrieval import (
    ADAPTER_REGISTRY,
    register_adapter,
)
from plato.retrieval.orchestrator import retrieve
from plato.state.models import Source


def _make_source(
    *,
    arxiv_id: str | None = None,
    doi: str | None = None,
    title: str = "Some Paper",
    via: str = "arxiv",
) -> Source:
    return Source(
        id=f"{via}:{arxiv_id or doi or title}",
        arxiv_id=arxiv_id,
        doi=doi,
        title=title,
        retrieved_via=via,  # type: ignore[arg-type]
        fetched_at=datetime.now(timezone.utc),
    )


class _FakeAdapter:
    """A minimal SourceAdapter that returns a canned list."""

    def __init__(self, name: str, sources: list[Source]) -> None:
        self.name = name
        self._sources = sources
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, limit: int) -> list[Source]:
        self.calls.append((query, limit))
        return list(self._sources[:limit])


class _BoomAdapter:
    """Adapter whose ``search`` always raises."""

    def __init__(self, name: str = "boom") -> None:
        self.name = name

    async def search(self, query: str, limit: int) -> list[Source]:  # noqa: ARG002
        raise RuntimeError("simulated upstream failure")


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Snapshot and restore the global adapter registry around each test."""
    saved = dict(ADAPTER_REGISTRY)
    ADAPTER_REGISTRY.clear()
    try:
        yield
    finally:
        ADAPTER_REGISTRY.clear()
        ADAPTER_REGISTRY.update(saved)


@pytest.mark.asyncio
async def test_retrieve_dedupes_overlapping_arxiv_id():
    shared = _make_source(arxiv_id="2401.0001", title="Shared Paper", via="arxiv")
    only_a = _make_source(arxiv_id="2401.0002", title="Only A", via="arxiv")
    only_b = _make_source(arxiv_id="2401.0003", title="Only B", via="openalex")
    # Same arxiv_id as ``shared`` but different surface fields — the dedup
    # key should still collapse them into one (first-seen wins).
    shared_dup = _make_source(
        arxiv_id="2401.0001", title="Shared Paper (alt)", via="openalex"
    )

    a = _FakeAdapter("alpha", [shared, only_a])
    b = _FakeAdapter("beta", [shared_dup, only_b])
    register_adapter(a)
    register_adapter(b)

    out = await retrieve("dm halos", limit=10, adapter_names=["alpha", "beta"])

    arxiv_ids = [s.arxiv_id for s in out]
    assert arxiv_ids.count("2401.0001") == 1
    assert {s.arxiv_id for s in out} == {"2401.0001", "2401.0002", "2401.0003"}
    # First-seen-wins: the alpha-supplied "Shared Paper" must survive.
    shared_kept = next(s for s in out if s.arxiv_id == "2401.0001")
    assert shared_kept.title == "Shared Paper"


@pytest.mark.asyncio
async def test_retrieve_falls_back_to_all_registered_when_no_names_or_profile():
    s1 = _make_source(arxiv_id="2401.AAAA", via="arxiv")
    s2 = _make_source(arxiv_id="2401.BBBB", via="openalex")
    register_adapter(_FakeAdapter("alpha", [s1]))
    register_adapter(_FakeAdapter("beta", [s2]))

    # No adapter_names, no profile → use every registered adapter.
    out = await retrieve("query", limit=5)

    arxiv_ids = {s.arxiv_id for s in out}
    assert arxiv_ids == {"2401.AAAA", "2401.BBBB"}


@pytest.mark.asyncio
async def test_retrieve_uses_profile_retrieval_sources():
    s_arxiv = _make_source(arxiv_id="2401.X", via="arxiv")
    s_openalex = _make_source(arxiv_id="2401.Y", via="openalex")
    register_adapter(_FakeAdapter("alpha", [s_arxiv]))
    register_adapter(_FakeAdapter("beta", [s_openalex]))
    # ``gamma`` is referenced by the profile but never registered — the
    # orchestrator must log + skip rather than crashing.
    profile = DomainProfile(name="t", retrieval_sources=["alpha", "gamma"])

    out = await retrieve("query", limit=5, profile=profile)

    assert {s.arxiv_id for s in out} == {"2401.X"}


@pytest.mark.asyncio
async def test_retrieve_survives_an_adapter_raising():
    survivor_source = _make_source(arxiv_id="2401.SURV", via="arxiv")
    register_adapter(_FakeAdapter("good", [survivor_source]))
    register_adapter(_BoomAdapter("bad"))

    out = await retrieve(
        "anything", limit=5, adapter_names=["good", "bad"]
    )

    assert len(out) == 1
    assert out[0].arxiv_id == "2401.SURV"


@pytest.mark.asyncio
async def test_retrieve_empty_adapter_list_returns_empty():
    # No registered adapters at all (autouse fixture cleared them).
    out = await retrieve("anything", limit=5)
    assert out == []


@pytest.mark.asyncio
async def test_retrieve_truncates_to_limit():
    sources = [
        _make_source(arxiv_id=f"2401.{i:04d}", title=f"P{i}", via="arxiv")
        for i in range(10)
    ]
    register_adapter(_FakeAdapter("alpha", sources))

    out = await retrieve("q", limit=3)

    assert len(out) == 3
    # Order is preserved across dedup, so we should see the first three.
    assert [s.arxiv_id for s in out] == ["2401.0000", "2401.0001", "2401.0002"]


@pytest.mark.asyncio
async def test_retrieve_overfetches_per_adapter():
    """The orchestrator should request more than ``limit`` from each adapter
    so dedup has spare candidates to fold together."""
    sources = [
        _make_source(arxiv_id=f"2401.{i:04d}", title=f"P{i}", via="arxiv")
        for i in range(10)
    ]
    spy = _FakeAdapter("alpha", sources)
    register_adapter(spy)

    await retrieve("q", limit=3)

    assert spy.calls, "adapter should have been invoked"
    _, requested = spy.calls[0]
    assert requested >= 3 * 2
