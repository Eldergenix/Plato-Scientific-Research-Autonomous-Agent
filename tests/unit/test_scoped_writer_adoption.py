"""Phase 4 — R11 adoption: tests for the per-node :class:`FileScope` declarations."""
from __future__ import annotations

from pathlib import Path

import pytest

from plato.io import ScopedWriter, ScopeError, writer_for_node
from plato.paper_agents.scopes import (
    ABSTRACT_SCOPE,
    CONCLUSIONS_SCOPE,
    METHODS_SCOPE,
)


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    pd = tmp_path / "proj"
    pd.mkdir()
    return pd


def test_abstract_scope_writes_to_paper_abstract(project_dir: Path) -> None:
    out = ScopedWriter(project_dir, ABSTRACT_SCOPE).write(
        "paper/abstract.tex", "x"
    )
    assert out.read_text() == "x"
    assert out == (project_dir / "paper" / "abstract.tex").resolve()


def test_methods_scope_writes_to_paper_methods(project_dir: Path) -> None:
    out = ScopedWriter(project_dir, METHODS_SCOPE).write(
        "paper/methods.tex", "y"
    )
    assert out.read_text() == "y"


def test_conclusions_scope_writes_to_paper_conclusions(project_dir: Path) -> None:
    out = ScopedWriter(project_dir, CONCLUSIONS_SCOPE).write(
        "paper/conclusions.tex", "z"
    )
    assert out.read_text() == "z"


def test_out_of_scope_write_raises(project_dir: Path) -> None:
    writer = ScopedWriter(project_dir, ABSTRACT_SCOPE)
    with pytest.raises(ScopeError):
        writer.write("plot/figure.png", b"\x89PNG")


def test_methods_scope_rejects_abstract_paths(project_dir: Path) -> None:
    """A scope should refuse paths intended for a different node."""
    writer = ScopedWriter(project_dir, METHODS_SCOPE)
    with pytest.raises(ScopeError):
        writer.write("paper/abstract.tex", "wrong scope")


def test_all_three_scopes_have_non_empty_write_lists() -> None:
    assert ABSTRACT_SCOPE.write
    assert METHODS_SCOPE.write
    assert CONCLUSIONS_SCOPE.write


def test_scopes_cover_legacy_temp_paths() -> None:
    """The legacy compile pipeline still writes to ``temp/<Section>.tex``;
    each scope must keep allowing its own legacy path."""
    assert ScopedWriter.matches("temp/Abstract.tex", ABSTRACT_SCOPE.write)
    assert ScopedWriter.matches("temp/Title.tex", ABSTRACT_SCOPE.write)
    assert ScopedWriter.matches("temp/Methods.tex", METHODS_SCOPE.write)
    assert ScopedWriter.matches("temp/Conclusions.tex", CONCLUSIONS_SCOPE.write)


def test_writer_for_node_returns_scoped_writer(project_dir: Path) -> None:
    writer = writer_for_node(project_dir, "abstract_node", ABSTRACT_SCOPE)
    assert isinstance(writer, ScopedWriter)
    out = writer.write("paper/abstract.tex", "ok")
    assert out.read_text() == "ok"


def test_writer_for_node_requires_explicit_scope(project_dir: Path) -> None:
    with pytest.raises(ValueError):
        writer_for_node(project_dir, "abstract_node", None)
