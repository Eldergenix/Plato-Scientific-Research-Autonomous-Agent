"""Iter-21 integration test: E2BExecutor against the real E2B service.

Same skip-by-default posture as ``test_modal_executor_live.py``: the
module skips unless

1. The ``e2b_code_interpreter`` SDK is installed.
2. ``E2B_API_KEY`` is set (the SDK's expected env var for auth).
3. ``PLATO_TEST_E2B=1`` is set (explicit opt-in — E2B calls hit a
   billed API).

To run locally::

    pip install e2b-code-interpreter
    export E2B_API_KEY=<your-key>
    export PLATO_TEST_E2B=1
    pytest tests/integration/test_e2b_executor_live.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip(
    "e2b_code_interpreter",
    reason=(
        "e2b-code-interpreter SDK is not installed; install with "
        "`pip install e2b-code-interpreter` to run this suite."
    ),
)

if os.getenv("PLATO_TEST_E2B") != "1":
    pytest.skip(
        "PLATO_TEST_E2B=1 not set; export it (and E2B_API_KEY) to enable the "
        "live E2BExecutor integration suite.",
        allow_module_level=True,
    )

if not os.getenv("E2B_API_KEY"):
    pytest.skip(
        "E2B_API_KEY env var is not set; the e2b SDK needs it for auth.",
        allow_module_level=True,
    )


from plato.executor.e2b_backend import E2BExecutor  # noqa: E402


@pytest.mark.asyncio
async def test_e2b_runs_print_cell(tmp_path: Path) -> None:
    """Smoke: E2B sandbox runs a one-line print and we get the output back."""
    executor = E2BExecutor()
    result = await executor.run(
        research_idea="x",
        methodology="```python\nprint('hello from e2b')\n```",
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
        timeout_seconds=60,
    )
    assert result.artifacts["executor"] == "e2b"
    assert result.artifacts["had_error"] is False
    assert result.artifacts["cells_executed"] == 1
    assert "hello from e2b" in result.results


@pytest.mark.asyncio
async def test_e2b_captures_matplotlib_figure(tmp_path: Path) -> None:
    """E2B's notebook surface natively returns image/png — must surface as plot_paths."""
    matplotlib_cell = """
```python
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([1, 2, 3], [4, 5, 6])
ax.set_title("e2b-figure-test")
plt.show()
```
"""
    executor = E2BExecutor()
    result = await executor.run(
        research_idea="x",
        methodology=matplotlib_cell,
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
        timeout_seconds=120,
    )
    assert result.artifacts["had_error"] is False
    assert len(result.plot_paths) >= 1
    assert all(Path(p).is_file() for p in result.plot_paths)


@pytest.mark.asyncio
async def test_e2b_surfaces_user_code_error(tmp_path: Path) -> None:
    """A runtime error in the user code must land as a typed cell record."""
    executor = E2BExecutor()
    result = await executor.run(
        research_idea="x",
        methodology="```python\nraise ValueError('boom from e2b cell')\n```",
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
        timeout_seconds=60,
    )
    assert result.artifacts["had_error"] is True
    cell = result.artifacts["cells"][0]
    assert cell["error"] is not None
    assert cell["error"]["ename"] == "ValueError"
    assert "boom from e2b" in cell["error"]["evalue"]
