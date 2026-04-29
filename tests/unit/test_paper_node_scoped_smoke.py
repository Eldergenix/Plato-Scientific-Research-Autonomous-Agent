"""Phase 4 — R11 adoption: smoke tests for scoped paper-graph nodes.

Just verifies that ``abstract_node``, ``methods_node`` and
``conclusions_node`` still import and run end-to-end with the
:class:`ScopedWriter` integration in place. We mock the LLM and the LaTeX
toolchain so the test stays hermetic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def test_three_nodes_importable() -> None:
    from plato.paper_agents.paper_node import (  # noqa: F401
        abstract_node,
        conclusions_node,
        methods_node,
    )
    from plato.paper_agents.scopes import (  # noqa: F401
        ABSTRACT_SCOPE,
        CONCLUSIONS_SCOPE,
        METHODS_SCOPE,
    )


def _make_state(project_dir: Path) -> dict[str, Any]:
    """Minimal `GraphState`-shaped dict pointing at a real temp project dir."""
    from plato.paper_agents.journal import Journal

    paper_folder = project_dir
    temp_dir = paper_folder / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    llm_calls = paper_folder / "LLM_calls.txt"

    return {
        "messages": [],
        "files": {
            "Folder": str(paper_folder),
            "Paper_folder": str(paper_folder),
            "Temp": str(temp_dir),
            "Paper_v1": str(paper_folder / "paper_v1.tex"),
            "LLM_calls": str(llm_calls),
            "Error": str(paper_folder / "Error.txt"),
        },
        "idea": {"Idea": "x", "Methods": "y", "Results": "z"},
        "paper": {
            "Title": "",
            "Abstract": "",
            "Keywords": "",
            "Introduction": "",
            "Methods": "",
            "Results": "",
            "Conclusions": "",
            "References": "",
            "summary": "",
            "journal": Journal.NONE,
            "add_citations": False,
            "cmbagent_keywords": False,
        },
        "tokens": {"ti": 0, "to": 0, "i": 0, "o": 0},
        "llm": {"model": "stub", "max_output_tokens": 1024, "llm": None, "temperature": 0.0},
        "latex": {"section_to_fix": ""},
        "keys": None,
        "time": {"start": 0.0},
        "writer": "scientist",
        "params": {"num_keywords": 3},
        "critiques": {},
        "critique_digest": None,
        "revision_state": {"iteration": 0, "max_iterations": 2},
    }


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    pd = tmp_path / "paper_proj"
    pd.mkdir()
    return pd


def _scripted_llm(scripts: list[str]):
    """Sequenced mock — returns ``scripts[i]`` for the i-th call, repeating
    the last script if more calls come in."""
    idx = {"i": 0}

    def _impl(prompt, state):
        state["tokens"]["ti"] += 1
        state["tokens"]["to"] += 1
        i = idx["i"]
        idx["i"] = i + 1
        payload = scripts[i] if i < len(scripts) else scripts[-1]
        return state, payload

    return _impl


def test_abstract_node_runs_with_scoped_writer(project_dir: Path) -> None:
    from plato.paper_agents import paper_node

    state = _make_state(project_dir)

    scripts = [
        # 1: abstract_prompt → JSON with Title + Abstract
        '```json\n{"Title": "T", "Abstract": "An abstract."}\n```',
        # 2: abstract_reflection → LaTeX block named Abstract
        "\\begin{Abstract}\nAn abstract.\n\\end{Abstract}",
    ]
    with patch.object(paper_node, "LLM_call", side_effect=_scripted_llm(scripts)), \
         patch.object(paper_node, "compile_tex_document", return_value=True), \
         patch.object(paper_node, "save_paper", return_value=None), \
         patch.object(paper_node, "fix_latex", side_effect=lambda s, f: (s, True)):
        out = paper_node.abstract_node(state, config=None)

    assert "paper" in out
    assert out["paper"]["Title"] == "T"
    # The ScopedWriter must have written into the project dir at temp/Abstract.tex.
    abstract_path = project_dir / "temp" / "Abstract.tex"
    title_path = project_dir / "temp" / "Title.tex"
    assert abstract_path.exists(), "ScopedWriter should have written temp/Abstract.tex"
    assert title_path.exists(), "ScopedWriter should have written temp/Title.tex"
    assert "An abstract." in abstract_path.read_text()


def _section_script(section_name: str) -> list[str]:
    return [f"\\begin{{{section_name}}}\nSome {section_name} text.\n\\end{{{section_name}}}"]


def test_methods_node_runs_with_scoped_writer(project_dir: Path) -> None:
    from plato.paper_agents import paper_node

    state = _make_state(project_dir)

    with patch.object(paper_node, "LLM_call", side_effect=_scripted_llm(_section_script("Methods"))), \
         patch.object(paper_node, "LaTeX_checker", side_effect=lambda s, t: t), \
         patch.object(paper_node, "compile_tex_document", return_value=True), \
         patch.object(paper_node, "save_paper", return_value=None), \
         patch.object(paper_node, "fix_latex", side_effect=lambda s, f: (s, True)):
        out = paper_node.methods_node(state, config=None)

    assert "paper" in out
    assert "Some Methods text." in out["paper"]["Methods"]
    methods_path = project_dir / "temp" / "Methods.tex"
    assert methods_path.exists(), "ScopedWriter should have written temp/Methods.tex"
    assert "Some Methods text." in methods_path.read_text()


def test_conclusions_node_runs_with_scoped_writer(project_dir: Path) -> None:
    from plato.paper_agents import paper_node

    state = _make_state(project_dir)

    with patch.object(paper_node, "LLM_call", side_effect=_scripted_llm(_section_script("Conclusions"))), \
         patch.object(paper_node, "LaTeX_checker", side_effect=lambda s, t: t), \
         patch.object(paper_node, "compile_tex_document", return_value=True), \
         patch.object(paper_node, "save_paper", return_value=None), \
         patch.object(paper_node, "fix_latex", side_effect=lambda s, f: (s, True)):
        out = paper_node.conclusions_node(state, config=None)

    assert "paper" in out
    assert "Some Conclusions text." in out["paper"]["Conclusions"]
    conclusions_path = project_dir / "temp" / "Conclusions.tex"
    assert conclusions_path.exists(), "ScopedWriter should have written temp/Conclusions.tex"
    assert "Some Conclusions text." in conclusions_path.read_text()
