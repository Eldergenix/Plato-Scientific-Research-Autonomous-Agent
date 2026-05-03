"""Phase 5 — Executor Protocol, registry, and built-in backends.

These tests are intentionally backend-agnostic: they exercise the
:class:`~plato.executor.Executor` Protocol and the registration helpers
without spinning up cmbagent / jupyter / modal / e2b. The Modal and E2B
skeletons are checked end-to-end (they're cheap to await — they return
a structured failure ``ExecutorResult`` when their SDK or credentials
are missing, which is the case in CI).
"""
from __future__ import annotations

import asyncio

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


def test_modal_executor_skeleton_returns_structured_failure_when_unavailable() -> None:
    """Modal skeleton returns a clean ExecutorResult when SDK or creds are absent.

    The previous behaviour raised :class:`NotImplementedError`. ADR 0007
    §1 was updated to reflect that the skeleton now ships the Protocol
    shape and surfaces missing-SDK / missing-credentials states as
    structured failure results so the workflow can persist them.
    """
    ex = get_executor("modal")

    async def _drive():
        return await ex.run(
            research_idea="i",
            methodology="m",
            data_description="d",
            project_dir="/tmp",
            keys=None,
        )

    result = asyncio.run(_drive())
    assert isinstance(result, ExecutorResult)
    assert result.artifacts.get("backend") == "modal"
    assert result.artifacts.get("success") is False
    # Either the SDK is missing, credentials are missing, or the remote
    # path is still TODO — all are acceptable signals from the skeleton.
    assert result.artifacts.get("stage") in {"sdk_import", "credentials", "not_implemented"}


def test_e2b_executor_skeleton_returns_structured_failure_when_unavailable() -> None:
    """E2B skeleton mirrors the modal contract."""
    ex = get_executor("e2b")

    async def _drive():
        return await ex.run(
            research_idea="i",
            methodology="m",
            data_description="d",
            project_dir="/tmp",
            keys=None,
        )

    result = asyncio.run(_drive())
    assert isinstance(result, ExecutorResult)
    assert result.artifacts.get("backend") == "e2b"
    assert result.artifacts.get("success") is False
    assert result.artifacts.get("stage") in {"sdk_import", "credentials"}


def test_local_jupyter_executes_methodology_as_code() -> None:
    """The local_jupyter backend now runs methodology as Python code.

    Falls back to a subprocess if ``jupyter_client`` isn't installed, so
    this test must succeed in any environment with a Python interpreter.
    """
    ex = get_executor("local_jupyter")

    async def _drive():
        return await ex.run(
            research_idea="probe",
            methodology="print('plato-local-jupyter-ok')",
            data_description="d",
            project_dir="/tmp",
            keys=None,
            timeout=30,
        )

    result = asyncio.run(_drive())
    assert isinstance(result, ExecutorResult)
    assert "plato-local-jupyter-ok" in result.artifacts.get("stdout", "")
    assert result.artifacts.get("success") is True


def test_executor_result_defaults() -> None:
    """Defaults match the contract: results required, everything else optional."""
    r = ExecutorResult(results="ok")
    assert r.plot_paths == []
    assert r.artifacts == {}
    assert r.cost_usd == 0.0
    assert r.tokens_in == 0
    assert r.tokens_out == 0
