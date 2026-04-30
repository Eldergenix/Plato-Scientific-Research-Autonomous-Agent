"""Phase 5 — Executor Protocol, registry, and built-in backends.

These tests are intentionally backend-agnostic: they exercise the
:class:`~plato.executor.Executor` Protocol and the registration helpers
without spinning up cmbagent / jupyter / modal / e2b. The Modal and E2B
stubs are checked end-to-end (they're cheap to await — they just raise
:class:`NotImplementedError`).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from plato.executor import (
    EXECUTOR_REGISTRY,
    Executor,
    ExecutorResult,
    get_executor,
    list_executors,
    register_executor,
)


class _StubExecutor:
    """Minimal Protocol-conformant stub used in collision/lookup tests."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def run(self, **kwargs):  # type: ignore[override]
        return ExecutorResult(results="stub")


def test_protocol_is_satisfied_by_stub_executor() -> None:
    assert isinstance(_StubExecutor("anything"), Executor)


def test_built_in_executors_are_registered() -> None:
    """All four backends auto-register on ``import plato.executor``."""
    expected = {"cmbagent", "local_jupyter", "modal", "e2b"}
    assert expected.issubset(set(list_executors()))
    for name in expected:
        ex = get_executor(name)
        assert ex.name == name
        assert isinstance(ex, Executor)


def test_register_rejects_duplicate_without_overwrite() -> None:
    name = "duplicate-test-executor-xyz"
    register_executor(_StubExecutor(name), overwrite=True)
    with pytest.raises(ValueError, match="already registered"):
        register_executor(_StubExecutor(name))
    # Cleanup so we don't leak state across tests.
    EXECUTOR_REGISTRY.pop(name, None)


def test_register_overwrite_replaces_entry() -> None:
    name = "overwrite-test-executor-xyz"
    first = _StubExecutor(name)
    second = _StubExecutor(name)
    register_executor(first, overwrite=True)
    register_executor(second, overwrite=True)
    assert get_executor(name) is second
    EXECUTOR_REGISTRY.pop(name, None)


def test_get_executor_unknown_raises() -> None:
    with pytest.raises(KeyError, match="Unknown executor"):
        get_executor("does-not-exist-xyz")


def test_executor_result_round_trips_json() -> None:
    """``ExecutorResult`` can survive a JSON serialization round-trip."""
    result = ExecutorResult(
        results="# heading\nbody",
        plot_paths=["/tmp/a.png", "/tmp/b.png"],
        artifacts={"notebook": "/tmp/run.ipynb", "step_count": 7},
        cost_usd=1.23,
        tokens_in=1000,
        tokens_out=2000,
    )
    payload = result.model_dump(mode="json")
    restored = ExecutorResult.model_validate(payload)
    assert restored == result
    assert restored.model_dump(mode="json") == payload


def test_modal_executor_is_a_stub() -> None:
    """Modal stub must surface a clear NotImplementedError when awaited."""
    ex = get_executor("modal")

    async def _drive():
        await ex.run(
            research_idea="i",
            methodology="m",
            data_description="d",
            project_dir="/tmp",
            keys=None,
        )

    with pytest.raises(NotImplementedError, match="ModalExecutor"):
        asyncio.run(_drive())


def test_e2b_executor_is_a_stub() -> None:
    ex = get_executor("e2b")

    async def _drive():
        await ex.run(
            research_idea="i",
            methodology="m",
            data_description="d",
            project_dir="/tmp",
            keys=None,
        )

    with pytest.raises(NotImplementedError, match="E2BExecutor"):
        asyncio.run(_drive())


def test_local_jupyter_raises_helpful_error_when_dep_missing() -> None:
    """If ``jupyter_client`` isn't installed the stub should hint at the fix.

    If it *is* installed (the real implementation would run), the stub
    still raises ``NotImplementedError`` for now — both outcomes are
    acceptable signals that the wiring is correct.
    """
    ex = get_executor("local_jupyter")

    async def _drive():
        await ex.run(
            research_idea="i",
            methodology="m",
            data_description="d",
            project_dir="/tmp",
            keys=None,
        )

    try:
        import jupyter_client  # type: ignore[import-not-found]  # noqa: F401

        expected = NotImplementedError
    except ImportError:
        expected = ImportError

    with pytest.raises(expected):
        asyncio.run(_drive())


def test_executor_result_defaults() -> None:
    """Defaults match the contract: results required, everything else optional."""
    r = ExecutorResult(results="ok")
    assert r.plot_paths == []
    assert r.artifacts == {}
    assert r.cost_usd == 0.0
    assert r.tokens_in == 0
    assert r.tokens_out == 0
