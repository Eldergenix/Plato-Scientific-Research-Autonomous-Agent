"""Unit tests for the iter-18 LocalJupyterExecutor real implementation.

We deliberately don't spin up a real jupyter kernel here — that would
demand the ipykernel binary on every CI runner and turn a 30-ms unit
test into a 5-s integration test. Instead we exercise the pure
helpers (``_extract_code_cells``) and the early-return paths
(``run`` with no executable cells, ``run`` with jupyter_client missing).

A real kernel-execution test lives in tests/integration/ and is
gated behind an env var.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest

from plato.executor.local_jupyter import (
    LocalJupyterExecutor,
    _extract_code_cells,
)


# --- _extract_code_cells ----------------------------------------------------

def test_extract_code_cells_picks_python_fences() -> None:
    md = """
Some prose explaining the experiment.

```python
import numpy as np
print(np.pi)
```

More prose.

```python
print("second cell")
```

A non-python fence (skipped):

```bash
ls -la
```
"""
    cells = _extract_code_cells(md)
    assert len(cells) == 2
    assert cells[0] == "import numpy as np\nprint(np.pi)"
    assert cells[1] == 'print("second cell")'


def test_extract_code_cells_accepts_py_alias() -> None:
    """``py`` and ``ipython`` are accepted aliases for ``python``."""
    md = """
```py
print("py-tagged")
```
```ipython
print("ipython-tagged")
```
"""
    cells = _extract_code_cells(md)
    assert len(cells) == 2
    assert "py-tagged" in cells[0]
    assert "ipython-tagged" in cells[1]


def test_extract_code_cells_falls_back_to_whole_text() -> None:
    """Plain text without fences becomes a single cell."""
    src = "import math\nprint(math.tau)"
    cells = _extract_code_cells(src)
    assert cells == [src]


def test_extract_code_cells_handles_empty_inputs() -> None:
    assert _extract_code_cells("") == []
    assert _extract_code_cells("    \n\n\t") == []


def test_extract_code_cells_strips_blank_blocks() -> None:
    """A fenced block containing only whitespace is dropped, not preserved."""
    md = """
```python

```

```python
print("real one")
```
"""
    cells = _extract_code_cells(md)
    assert cells == ['print("real one")']


# --- run() early-return paths ----------------------------------------------

@pytest.mark.asyncio
async def test_run_returns_clean_result_when_no_code(tmp_path: Any) -> None:
    """Empty methodology + no kwargs[code] must return an honest empty result."""
    executor = LocalJupyterExecutor()
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


@pytest.mark.asyncio
async def test_run_raises_clear_importerror_without_jupyter_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """When jupyter_client isn't importable, raise ImportError with install hint."""
    # Force the import to fail without uninstalling the real package.
    monkeypatch.setitem(sys.modules, "jupyter_client", None)
    monkeypatch.setitem(sys.modules, "jupyter_client.manager", None)

    executor = LocalJupyterExecutor()
    with pytest.raises(ImportError) as exc_info:
        await executor.run(
            research_idea="x",
            methodology="print('hi')",
            data_description="y",
            project_dir=str(tmp_path),
            keys=None,
        )
    assert "jupyter-client" in str(exc_info.value)
    assert "pip install" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_explicit_code_kwarg_overrides_methodology(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """``kwargs['code']`` must take precedence over ``methodology`` extraction."""
    captured_cells: list[list[str]] = []

    class _StubKM:
        def __init__(self, kernel_name: str = "python3") -> None:
            self.kernel_name = kernel_name

        def start_kernel(self) -> None:
            pass

        def client(self) -> "_StubClient":
            return _StubClient(captured_cells)

        def shutdown_kernel(self, *, now: bool = True, restart: bool = False) -> None:
            pass

    class _StubClient:
        def __init__(self, sink: list[list[str]]) -> None:
            self._sink = sink
            self._this_cell: list[str] = []
            self._idle_pending = False

        def start_channels(self) -> None:
            pass

        def stop_channels(self) -> None:
            pass

        def wait_for_ready(self, timeout: float = 30.0) -> None:
            pass

        def execute(self, source: str, *, allow_stdin: bool = False) -> str:
            self._this_cell.append(source)
            self._sink.append([source])
            self._idle_pending = True
            return "msg-1"

        def get_iopub_msg(self, timeout: float) -> dict[str, Any]:
            self._idle_pending = False
            return {
                "parent_header": {"msg_id": "msg-1"},
                "msg_type": "status",
                "content": {"execution_state": "idle"},
            }

    # Build a fake jupyter_client.manager module that exposes our StubKM.
    import types

    fake_module = types.ModuleType("jupyter_client.manager")
    fake_module.KernelManager = _StubKM  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jupyter_client", types.ModuleType("jupyter_client"))
    monkeypatch.setitem(sys.modules, "jupyter_client.manager", fake_module)

    executor = LocalJupyterExecutor()
    result = await executor.run(
        research_idea="x",
        methodology="```python\nprint('from-methodology')\n```",
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
        code="print('from-kwargs')",
    )

    # The captured cells should be the explicit code, NOT the markdown
    # fence content.
    assert captured_cells == [["print('from-kwargs')"]]
    assert result.artifacts["cells_executed"] == 1
    assert result.artifacts["had_error"] is False
