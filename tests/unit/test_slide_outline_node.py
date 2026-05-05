"""Smoke tests for ``plato.paper_agents.slide_outline_node``.

The node runs once after the revision loop and converts the finished
paper into a presentation-grade Markdown outline. We mock ``LLM_call``
so the test stays hermetic, then assert the node:

* writes the outline to ``state['paper']['slide_outline']``
* persists ``slide_outline.md`` under ``Paper_folder`` via ScopedWriter
* skips disk writes when the LLM returns empty output
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def _make_state(
    project_dir: Path,
    *,
    paper_text: str = "An abstract.",
) -> dict[str, Any]:
    """Minimal ``GraphState``-shaped dict pointing at a real temp dir.

    Mirrors the shape used by ``test_paper_node_scoped_smoke._make_state``
    but trimmed to just the keys ``slide_outline_node`` + its prompt
    builder consume: ``paper`` (read by ``_paper_snapshot_for_review``),
    ``files.Paper_folder`` (where ScopedWriter roots), and ``tokens``
    (the trailing print statement reads ``ti`` / ``to``).
    """
    paper_folder = project_dir
    return {
        "files": {"Paper_folder": str(paper_folder)},
        "paper": {
            "Title": "Hello",
            "Abstract": paper_text,
            "Introduction": "",
            "Methods": "",
            "Results": "",
            "Conclusions": "",
        },
        "tokens": {"ti": 0, "to": 0, "i": 0, "o": 0},
        "writer": "scientist",
    }


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    pd = tmp_path / "paper_proj"
    pd.mkdir()
    return pd


def _scripted_llm(payload: str):
    """Sequenced LLM stub: returns ``payload`` and bumps token counters
    so the node's print statement (which reads ``state['tokens']``) is
    well-defined.
    """

    def _impl(prompt, state, **kwargs):  # noqa: ARG001
        state["tokens"]["ti"] += 1
        state["tokens"]["to"] += 1
        return state, payload

    return _impl


def test_slide_outline_writes_to_paper_folder(project_dir: Path) -> None:
    """A non-empty LLM result must (a) land in state['paper']['slide_outline']
    and (b) be persisted to ``<Paper_folder>/slide_outline.md`` via
    ScopedWriter."""
    from plato.paper_agents import slide_outline_node as node_mod

    state = _make_state(project_dir)
    fake_outline = "## Slide 1: Title\n- bullet a\n- bullet b\n"

    with patch.object(
        node_mod, "LLM_call", side_effect=_scripted_llm(fake_outline)
    ):
        out = node_mod.slide_outline_node(state, config=None)

    assert "paper" in out
    assert out["paper"]["slide_outline"] == fake_outline.strip()

    outline_path = project_dir / "slide_outline.md"
    assert outline_path.is_file(), (
        "ScopedWriter should have written slide_outline.md under Paper_folder"
    )
    assert outline_path.read_text(encoding="utf-8") == fake_outline.strip()


def test_slide_outline_handles_empty_paper(project_dir: Path) -> None:
    """Empty paper text shouldn't crash the node — the prompt builder
    falls back to ``(no paper text yet)`` and the LLM still returns
    something the test can stub. We only assert non-crashing + a
    well-formed return shape; whether the LLM-side decides to emit
    content is out-of-scope here."""
    from plato.paper_agents import slide_outline_node as node_mod

    state = _make_state(project_dir, paper_text="")
    # Wipe every section so the snapshot is the "(no paper text yet)"
    # fallback rather than a stub abstract.
    for key in ("Title", "Abstract", "Introduction", "Methods", "Results", "Conclusions"):
        state["paper"][key] = ""

    with patch.object(
        node_mod, "LLM_call", side_effect=_scripted_llm("")
    ):
        out = node_mod.slide_outline_node(state, config=None)

    assert "paper" in out
    assert out["paper"]["slide_outline"] == ""
    # No file written when the outline is empty (see the next test for
    # the explicit assertion on the disk side).


def test_slide_outline_does_not_write_when_llm_returns_empty(
    project_dir: Path,
) -> None:
    """When the LLM returns an empty string the node must NOT touch
    disk — the production code guards the ScopedWriter call with
    ``if paper_folder and outline``. The state still gets the empty
    string back so downstream consumers see the no-op explicitly."""
    from plato.paper_agents import slide_outline_node as node_mod

    state = _make_state(project_dir)

    with patch.object(
        node_mod, "LLM_call", side_effect=_scripted_llm("")
    ):
        out = node_mod.slide_outline_node(state, config=None)

    outline_path = project_dir / "slide_outline.md"
    assert not outline_path.exists(), (
        "slide_outline.md should not be written when the LLM returns empty"
    )
    assert out["paper"]["slide_outline"] == ""
