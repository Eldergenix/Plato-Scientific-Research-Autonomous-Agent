"""Unit tests for the iter-20 ModalExecutor real implementation.

We deliberately don't talk to the real Modal API — that would demand
``modal token`` credentials and a network round-trip, turning a 30-ms
unit test into a paid integration test. Instead we exercise:

1. The pure ``_extract_code_cells`` helper (fence parsing parity with
   LocalJupyterExecutor).
2. The pure ``_parse_runner_envelope`` helper (markers + JSON shape).
3. The ``run()`` early-return when methodology is empty.
4. The ``ImportError`` path when modal isn't installed.
5. A happy-path run where ``modal`` is replaced with a stub module that
   produces a deterministic envelope; this proves the host loop wires
   stdout → envelope → ExecutorResult correctly.

A real-Modal test lives in tests/integration/ behind an env var.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from plato.executor.modal_backend import (
    ModalExecutor,
    _extract_code_cells,
    _parse_runner_envelope,
)


# --- _extract_code_cells ---------------------------------------------------

def test_extract_code_cells_picks_python_fences() -> None:
    md = """
Some prose.

```python
import numpy as np
print(np.pi)
```

```python
print("second")
```

```bash
ls -la
```
"""
    cells = _extract_code_cells(md)
    assert len(cells) == 2
    assert cells[0] == "import numpy as np\nprint(np.pi)"
    assert cells[1] == 'print("second")'


def test_extract_code_cells_falls_back_to_whole_text() -> None:
    src = "import math\nprint(math.tau)"
    assert _extract_code_cells(src) == [src]


def test_extract_code_cells_handles_empty_inputs() -> None:
    assert _extract_code_cells("") == []
    assert _extract_code_cells("   \n") == []


# --- _parse_runner_envelope ------------------------------------------------

def test_parse_runner_envelope_round_trips_payload() -> None:
    raw = (
        "irrelevant header noise\n"
        "===PLATO_RESULT_START===\n"
        + json.dumps({"stdout": "hi", "stderr": "", "figures": [], "error": None})
        + "\n===PLATO_RESULT_END===\n"
        "trailing junk\n"
    )
    out = _parse_runner_envelope(raw)
    assert out is not None
    assert out["stdout"] == "hi"
    assert out["error"] is None


def test_parse_runner_envelope_returns_none_when_markers_missing() -> None:
    assert _parse_runner_envelope("nothing here") is None
    assert _parse_runner_envelope("===PLATO_RESULT_START===\n{}") is None


def test_parse_runner_envelope_returns_none_on_invalid_json() -> None:
    raw = "===PLATO_RESULT_START===\nnot json===PLATO_RESULT_END==="
    assert _parse_runner_envelope(raw) is None


# --- run() early returns ---------------------------------------------------

@pytest.mark.asyncio
async def test_run_returns_clean_result_when_no_code(tmp_path: Path) -> None:
    executor = ModalExecutor()
    result = await executor.run(
        research_idea="x",
        methodology="",
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
    )
    assert result.results == "No executable code found in methodology."
    assert result.plot_paths == []
    assert result.artifacts.get("cells_executed") == 0
    assert result.artifacts.get("executor") == "modal"


@pytest.mark.asyncio
async def test_run_raises_clear_importerror_without_modal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "modal", None)

    executor = ModalExecutor()
    with pytest.raises(ImportError) as exc_info:
        await executor.run(
            research_idea="x",
            methodology="print('hi')",
            data_description="y",
            project_dir=str(tmp_path),
            keys=None,
        )
    assert "modal" in str(exc_info.value)
    assert "pip install" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_with_stub_modal_returns_envelope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end happy path with a stub modal module.

    The stub's Sandbox.create returns a sandbox whose .stdout.read()
    yields a valid PLATO_RESULT envelope. We assert the ExecutorResult
    captures stdout + cell record + the artifacts dict.
    """
    captured_runners: list[str] = []

    class _StubStream:
        def __init__(self, text: str) -> None:
            self._text = text

        def read(self) -> str:
            return self._text

    class _StubSandbox:
        def __init__(self, stdout_text: str) -> None:
            self.stdout = _StubStream(stdout_text)
            self.stderr = _StubStream("")

        def wait(self) -> None:
            pass

        def terminate(self) -> None:
            pass

    class _StubSandboxFactory:
        @staticmethod
        def create(*args: Any, **kwargs: Any) -> _StubSandbox:
            # The runner script is the third positional after "python",
            # "-c". Capture it so the test can verify the user code
            # made it into the sandbox.
            captured_runners.append(args[-1] if args else "")
            envelope = {
                "stdout": "ran cell 1",
                "stderr": "",
                "figures": [],
                "error": None,
            }
            return _StubSandbox(
                "===PLATO_RESULT_START===\n"
                + json.dumps(envelope)
                + "\n===PLATO_RESULT_END===\n"
            )

    class _StubAppNamespace:
        @staticmethod
        def lookup(name: str, *, create_if_missing: bool = False) -> str:
            return f"app::{name}"

    class _StubImage:
        def pip_install(self, *deps: str) -> "_StubImage":
            return self

    class _StubImageNamespace:
        @staticmethod
        def debian_slim() -> _StubImage:
            return _StubImage()

    import types as _types

    fake = _types.ModuleType("modal")
    fake.Sandbox = _StubSandboxFactory
    fake.App = _StubAppNamespace
    fake.Image = _StubImageNamespace
    monkeypatch.setitem(sys.modules, "modal", fake)

    executor = ModalExecutor()
    result = await executor.run(
        research_idea="x",
        methodology="```python\nprint('hello')\n```",
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
    )

    assert result.artifacts["executor"] == "modal"
    assert result.artifacts["cells_executed"] == 1
    assert result.artifacts["had_error"] is False
    assert "ran cell 1" in result.results
    # Captured runner script must contain the user's print() call.
    assert any("print('hello')" in src for src in captured_runners)
