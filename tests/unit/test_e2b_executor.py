"""Unit tests for the iter-20 E2BExecutor real implementation.

Same testing posture as ``test_modal_executor.py`` — we never call the
real E2B service. The pure helpers and the ``run()`` early-return
paths are exercised directly; the happy path uses a stub
``e2b_code_interpreter`` module that returns a synthesized execution
object.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from plato.executor.e2b_backend import (
    E2BExecutor,
    _coerce_text,
    _extract_code_cells,
    _extract_png,
)


# --- _extract_code_cells ---------------------------------------------------

def test_extract_code_cells_handles_fenced_python() -> None:
    md = """
prose
```python
print("a")
```
```py
print("b")
```
"""
    cells = _extract_code_cells(md)
    assert cells == ['print("a")', 'print("b")']


def test_extract_code_cells_falls_back_to_whole_text() -> None:
    assert _extract_code_cells("import math") == ["import math"]


def test_extract_code_cells_empty_input() -> None:
    assert _extract_code_cells("") == []


# --- _coerce_text ---------------------------------------------------------

def test_coerce_text_handles_str_list_none() -> None:
    assert _coerce_text(None) == ""
    assert _coerce_text("x") == "x"
    assert _coerce_text(["a", "b"]) == "ab"
    assert _coerce_text(("a", "b")) == "ab"
    # Anything else is stringified.
    assert _coerce_text(42) == "42"


# --- _extract_png ---------------------------------------------------------

def test_extract_png_reads_direct_attr() -> None:
    class _R:
        png = "abc"

    assert _extract_png(_R()) == "abc"


def test_extract_png_reads_raw_data() -> None:
    class _R:
        raw_data = {"image/png": "xyz", "text/plain": "hi"}

    assert _extract_png(_R()) == "xyz"


def test_extract_png_returns_none_when_missing() -> None:
    class _R:
        pass

    assert _extract_png(_R()) is None


# --- run() early returns --------------------------------------------------

@pytest.mark.asyncio
async def test_run_returns_clean_result_when_no_code(tmp_path: Path) -> None:
    executor = E2BExecutor()
    result = await executor.run(
        research_idea="x",
        methodology="",
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
    )
    assert result.results == "No executable code found in methodology."
    assert result.artifacts.get("cells_executed") == 0
    assert result.artifacts.get("executor") == "e2b"


@pytest.mark.asyncio
async def test_run_raises_clear_importerror_without_e2b(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", None)

    executor = E2BExecutor()
    with pytest.raises(ImportError) as exc_info:
        await executor.run(
            research_idea="x",
            methodology="print('hi')",
            data_description="y",
            project_dir=str(tmp_path),
            keys=None,
        )
    assert "e2b-code-interpreter" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_with_stub_sandbox_captures_logs_and_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end happy path with a stub e2b_code_interpreter module."""
    captured_code: list[str] = []

    class _StubLogs:
        def __init__(self, stdout: str = "", stderr: str = "") -> None:
            self.stdout = stdout
            self.stderr = stderr

    class _StubExecution:
        def __init__(self) -> None:
            self.logs = _StubLogs(stdout="hello from cell\n", stderr="")
            self.error = None
            # No image results — keeps the test independent of the
            # base64 + filesystem write path.
            self.results: list[Any] = []

    class _StubSandbox:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def run_code(self, code: str, *, timeout: int = 60) -> _StubExecution:
            captured_code.append(code)
            return _StubExecution()

        def kill(self) -> None:
            pass

    import types as _types

    fake = _types.ModuleType("e2b_code_interpreter")
    fake.Sandbox = _StubSandbox
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", fake)

    executor = E2BExecutor()
    result = await executor.run(
        research_idea="x",
        methodology="```python\nprint('hello')\n```",
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
    )

    assert result.artifacts["executor"] == "e2b"
    assert result.artifacts["cells_executed"] == 1
    assert result.artifacts["had_error"] is False
    assert "hello from cell" in result.results
    assert captured_code == ["print('hello')"]


@pytest.mark.asyncio
async def test_run_propagates_sandbox_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If sandbox.run_code raises, the cell record carries the error and the loop stops."""

    class _StubSandbox:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def run_code(self, code: str, *, timeout: int = 60) -> Any:
            raise RuntimeError("boom: sandbox refused")

        def kill(self) -> None:
            pass

    import types as _types

    fake = _types.ModuleType("e2b_code_interpreter")
    fake.Sandbox = _StubSandbox
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", fake)

    executor = E2BExecutor()
    result = await executor.run(
        research_idea="x",
        methodology="print('a')\nprint('b')",
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
    )
    assert result.artifacts["had_error"] is True
    cell = result.artifacts["cells"][0]
    assert cell["error"]["ename"] == "E2BSandboxError"
    assert "boom" in cell["error"]["evalue"]
