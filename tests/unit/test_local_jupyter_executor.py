"""Unit tests for :class:`plato.executor.local_jupyter.LocalJupyterExecutor`.

These tests exercise the low-level ``execute_code`` entry point so they
work whether the backend resolved to a real Jupyter kernel or to the
subprocess fallback.
"""
from __future__ import annotations

import asyncio

import pytest

from plato.executor import ExecutorResult, get_executor
from plato.executor.local_jupyter import CellResult, LocalJupyterExecutor


@pytest.fixture
def executor():
    ex = LocalJupyterExecutor(default_timeout=30)
    try:
        yield ex
    finally:
        ex.shutdown()


def test_run_print_returns_expected_stdout(executor: LocalJupyterExecutor) -> None:
    cell = executor.execute_code("print(1 + 1)")
    assert isinstance(cell, CellResult)
    assert cell.success is True
    assert cell.timed_out is False
    assert "2" in cell.stdout
    assert cell.error == ""


def test_user_code_exception_is_captured_not_propagated(
    executor: LocalJupyterExecutor,
) -> None:
    cell = executor.execute_code("raise ValueError('boom')")
    assert cell.success is False
    assert cell.timed_out is False
    # Both backends must surface enough error context to debug.
    blob = (cell.error + cell.stderr).lower()
    assert "valueerror" in blob
    assert "boom" in blob


def test_timeout_is_enforced(executor: LocalJupyterExecutor) -> None:
    cell = executor.execute_code(
        "import time\nfor _ in range(20):\n    time.sleep(0.5)\n",
        timeout=1.0,
    )
    assert cell.timed_out is True
    assert cell.success is False
    assert cell.duration_sec >= 0.9


def test_executor_is_registered_under_local_jupyter() -> None:
    ex = get_executor("local_jupyter")
    assert isinstance(ex, LocalJupyterExecutor)
    assert ex.name == "local_jupyter"


def test_protocol_run_returns_executor_result(executor: LocalJupyterExecutor) -> None:
    async def _drive():
        return await executor.run(
            research_idea="r",
            methodology="x = 7\nprint('protocol-ok', x)",
            data_description="some data",
            project_dir="/tmp",
            keys=None,
            timeout=30,
        )

    result = asyncio.run(_drive())
    assert isinstance(result, ExecutorResult)
    assert "protocol-ok 7" in result.artifacts.get("stdout", "")
    assert result.artifacts.get("success") is True
    assert "LocalJupyterExecutor run" in result.results


def test_kernel_state_persists_across_cells_when_using_jupyter(
    executor: LocalJupyterExecutor,
) -> None:
    """Reusing the kernel keeps module-level state alive between cells.

    Skipped under the subprocess fallback, where each call is isolated.
    """
    if not executor._using_jupyter:  # type: ignore[attr-defined]
        pytest.skip("subprocess fallback in use; cells are isolated by design")
    seed = executor.execute_code("x = 41")
    assert seed.success is True
    follow = executor.execute_code("print(x + 1)")
    assert follow.success is True
    assert "42" in follow.stdout


def test_subprocess_fallback_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """If jupyter_client isn't importable, subprocess mode still executes code."""
    monkeypatch.setattr(LocalJupyterExecutor, "_jupyter_available", staticmethod(lambda: False))
    ex = LocalJupyterExecutor(default_timeout=30)
    try:
        cell = ex.execute_code("print('subproc-ok')")
        assert cell.backend == "subprocess"
        assert cell.success is True
        assert "subproc-ok" in cell.stdout
    finally:
        ex.shutdown()
