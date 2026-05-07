"""Phase 5 — Executor Protocol, registry, and built-in backends.

These tests are intentionally backend-agnostic: they exercise the
:class:`~plato.executor.Executor` Protocol and the registration helpers
without spinning up cmbagent / jupyter / modal / e2b. Optional backends are
checked only through their import-time error contract.
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

    async def run(self, **kwargs):
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


def test_modal_executor_missing_sdk_has_clear_error() -> None:
    """Modal is a real optional backend; missing SDK must be explicit."""
    ex = get_executor("modal")

    async def _drive():
        await ex.run(
            research_idea="i",
            methodology="m",
            data_description="d",
            project_dir="/tmp",
            keys=None,
        )

    with pytest.raises(ImportError, match="modal SDK"):
        asyncio.run(_drive())


def test_e2b_executor_missing_sdk_has_clear_error() -> None:
    ex = get_executor("e2b")

    async def _drive():
        await ex.run(
            research_idea="i",
            methodology="m",
            data_description="d",
            project_dir="/tmp",
            keys=None,
        )

    with pytest.raises(ImportError, match="e2b-code-interpreter SDK"):
        asyncio.run(_drive())


def test_local_jupyter_runs_explicit_code(tmp_path: Path) -> None:
    """The local executor should be runnable when registered."""
    ex = get_executor("local_jupyter")

    async def _drive():
        return await ex.run(
            research_idea="i",
            methodology="m",
            data_description="d",
            project_dir=tmp_path,
            keys=None,
            code="print('local-jupyter-ok')",
        )

    result = asyncio.run(_drive())
    assert "local-jupyter-ok" in result.results
    assert result.artifacts["cells_executed"] == 1


def test_executor_result_defaults() -> None:
    """Defaults match the contract: results required, everything else optional."""
    r = ExecutorResult(results="ok")
    assert r.plot_paths == []
    assert r.artifacts == {}
    assert r.cost_usd == 0.0
    assert r.tokens_in == 0
    assert r.tokens_out == 0
