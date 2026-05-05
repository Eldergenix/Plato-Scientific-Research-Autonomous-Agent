"""Phase 2 contract tests for the SourceAdapter protocol and registry."""
from __future__ import annotations

import asyncio
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


# --- Added edge-case tests below this line ---------------------------------


def test_protocol_rejects_object_missing_search_method():
    """An object without ``search`` is not a SourceAdapter."""

    class _MissingSearch:
        name = "no-search"

    assert not isinstance(_MissingSearch(), SourceAdapter)


def test_protocol_rejects_object_missing_name_attribute():
    """An object without ``name`` is not a SourceAdapter."""

    class _Nameless:
        async def search(self, query: str, limit: int) -> list[Source]:
            return []

    # Protocol checks both attribute presence at runtime.
    assert not isinstance(_Nameless(), SourceAdapter)


def test_register_overwrite_replaces_prior_adapter():
    """overwrite=True must replace the existing entry, not duplicate it."""

    class _A:
        name = "overwrite-target"

        async def search(self, query: str, limit: int) -> list[Source]:
            return []

    class _B:
        name = "overwrite-target"

        async def search(self, query: str, limit: int) -> list[Source]:
            return []

    a, b = _A(), _B()
    register_adapter(a, overwrite=True)
    assert get_adapter("overwrite-target") is a
    register_adapter(b, overwrite=True)
    assert get_adapter("overwrite-target") is b


def test_list_adapters_returns_sorted_names():
    """list_adapters must return names sorted alphabetically."""

    class _Z:
        name = "z-adapter"

        async def search(self, query: str, limit: int) -> list[Source]:
            return []

    class _A:
        name = "a-adapter"

        async def search(self, query: str, limit: int) -> list[Source]:
            return []

    register_adapter(_Z(), overwrite=True)
    register_adapter(_A(), overwrite=True)
    names = list_adapters()
    a_idx = names.index("a-adapter")
    z_idx = names.index("z-adapter")
    assert a_idx < z_idx


def test_list_adapters_returns_a_copy_safe_from_mutation():
    """Mutating the returned list must not corrupt the registry's internals."""
    fake = _FakeAdapter()
    register_adapter(fake, overwrite=True)
    listing = list_adapters()
    listing.clear()
    # Adapter is still registered.
    assert "fake-test-adapter" in list_adapters()


def test_fake_adapter_search_respects_limit():
    """The contract: ``search(query, limit)`` must not exceed ``limit``."""
    fake = _FakeAdapter()
    results = asyncio.run(fake.search("query", limit=1))
    assert len(results) == 1
    assert all(isinstance(r, Source) for r in results)


def test_fake_adapter_search_returns_zero_when_limit_zero():
    """A limit of 0 must produce no results — empty list, no exception."""
    fake = _FakeAdapter()
    results = asyncio.run(fake.search("anything", limit=0))
    assert results == []


def test_get_adapter_error_message_lists_known_names():
    """The KeyError message must mention currently-registered adapters."""
    fake = _FakeAdapter()
    register_adapter(fake, overwrite=True)
    with pytest.raises(KeyError) as exc_info:
        get_adapter("totally-bogus-name")
    assert "fake-test-adapter" in str(exc_info.value)


def test_adapter_registry_is_the_module_level_dict():
    """ADAPTER_REGISTRY is the canonical store; register_adapter mutates it."""
    fake = _FakeAdapter()
    register_adapter(fake, overwrite=True)
    assert ADAPTER_REGISTRY["fake-test-adapter"] is fake
