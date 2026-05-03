"""Iter-21 integration test: ModalExecutor against the real Modal API.

This module skips entirely unless three conditions are all met:

1. The ``modal`` SDK is installed.
2. ``PLATO_TEST_MODAL=1`` is set (the explicit opt-in — Modal calls cost
   real money even on the free tier).
3. The local Modal token works (i.e. ``modal token new`` has been run).

To run locally::

    pip install modal
    modal token new
    export PLATO_TEST_MODAL=1
    pytest tests/integration/test_modal_executor_live.py

Mirrors the tests/integration/test_postgres_checkpointer.py pattern —
the unit-test suite has full coverage of the ``run()`` early-return and
ImportError paths via stub-modal monkeypatching; this module proves the
real round-trip end-to-end so we'd notice if Modal's API changes.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Skip the entire module unless modal is installed AND the explicit
# opt-in env var is set. Keeps the default ``pytest`` run on a developer
# laptop and the lightweight ``test-fast`` CI job free of Modal calls.
pytest.importorskip(
    "modal",
    reason="modal SDK is not installed; install with `pip install modal` to run this suite.",
)

if os.getenv("PLATO_TEST_MODAL") != "1":
    pytest.skip(
        "PLATO_TEST_MODAL=1 not set; export it (and make sure `modal token new` has run) "
        "to enable the live ModalExecutor integration suite.",
        allow_module_level=True,
    )


from plato.executor.modal_backend import ModalExecutor  # noqa: E402


@pytest.mark.asyncio
async def test_modal_runs_print_cell_and_returns_envelope(tmp_path: Path) -> None:
    """Smoke: Modal sandbox runs a one-line print and we get the output back."""
    executor = ModalExecutor()
    result = await executor.run(
        research_idea="x",
        methodology="```python\nprint('hello from modal')\n```",
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
        # Tighten the timeout so a hung sandbox fails the test fast
        # rather than taking the default 600s.
        timeout_seconds=120,
    )
    assert result.artifacts["executor"] == "modal"
    assert result.artifacts["had_error"] is False
    assert result.artifacts["cells_executed"] == 1
    assert "hello from modal" in result.results


@pytest.mark.asyncio
async def test_modal_captures_matplotlib_figure(tmp_path: Path) -> None:
    """The runner script's plt.show hook must base64-encode any figures."""
    matplotlib_cell = """
```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot([1, 2, 3], [4, 5, 6])
ax.set_title("modal-figure-test")
plt.show()
```
"""
    executor = ModalExecutor()
    result = await executor.run(
        research_idea="x",
        methodology=matplotlib_cell,
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
        timeout_seconds=180,
    )
    assert result.artifacts["had_error"] is False
    # plot_paths should hold the PNG written into project_dir/plots/modal/.
    assert len(result.plot_paths) >= 1
    assert all(Path(p).is_file() for p in result.plot_paths)


@pytest.mark.asyncio
async def test_modal_surfaces_user_code_error(tmp_path: Path) -> None:
    """A runtime error in the user code must land as a typed cell record."""
    executor = ModalExecutor()
    result = await executor.run(
        research_idea="x",
        methodology="```python\nraise ValueError('boom from cell')\n```",
        data_description="y",
        project_dir=str(tmp_path),
        keys=None,
        timeout_seconds=120,
    )
    assert result.artifacts["had_error"] is True
    cell = result.artifacts["cells"][0]
    assert cell["error"] is not None
    assert cell["error"]["ename"] == "ValueError"
    assert "boom from cell" in cell["error"]["evalue"]
