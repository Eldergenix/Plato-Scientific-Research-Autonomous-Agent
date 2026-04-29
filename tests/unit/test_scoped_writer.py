"""Phase 3 — R11 unit tests for :mod:`plato.io.scoped_writer`."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from plato.io import FileScope, ScopedWriter, ScopeError


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    pd = tmp_path / "proj"
    pd.mkdir()
    return pd


# ---------------------------------------------------------------------------
# Write scope
# ---------------------------------------------------------------------------


def test_allowed_write_succeeds(project_dir: Path) -> None:
    scope = FileScope(write=["papers/**/*.tex", "out.json"])
    writer = ScopedWriter(project_dir, scope)

    out = writer.write("papers/sec/intro.tex", "Hello world")

    assert out == (project_dir / "papers/sec/intro.tex").resolve()
    assert out.read_text() == "Hello world"


def test_out_of_scope_path_raises(project_dir: Path) -> None:
    scope = FileScope(write=["papers/**/*.tex"])
    writer = ScopedWriter(project_dir, scope)

    with pytest.raises(ScopeError):
        writer.write("notes.txt", "nope")


def test_absolute_path_rejected(project_dir: Path) -> None:
    scope = FileScope(write=["**/*"])
    writer = ScopedWriter(project_dir, scope)

    with pytest.raises(ScopeError):
        writer.write("/etc/passwd", "x")
    with pytest.raises(ScopeError):
        writer.write(str(project_dir / "papers/intro.tex"), "x")


def test_parent_traversal_rejected(project_dir: Path) -> None:
    scope = FileScope(write=["**/*"])
    writer = ScopedWriter(project_dir, scope)

    with pytest.raises(ScopeError):
        writer.write("../escape.txt", "x")
    with pytest.raises(ScopeError):
        writer.write("papers/../../escape.txt", "x")


def test_symlink_to_outside_project_dir_rejected(
    project_dir: Path, tmp_path: Path
) -> None:
    """A symlink under project_dir pointing outside must be refused."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.txt").write_text("secret")

    # Pre-create the parent and a symlinked file inside project_dir.
    (project_dir / "papers").mkdir()
    link = project_dir / "papers" / "leak.txt"
    os.symlink(outside / "leak.txt", link)

    scope = FileScope(write=["papers/**/*"], read=["papers/**/*"])
    writer = ScopedWriter(project_dir, scope)

    with pytest.raises(ScopeError):
        writer.read("papers/leak.txt")
    with pytest.raises(ScopeError):
        writer.write("papers/leak.txt", "overwrite")


def test_symlinked_subdir_rejected(project_dir: Path, tmp_path: Path) -> None:
    """If a parent directory is a symlink to outside, refuse."""
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    os.symlink(outside, project_dir / "linked")

    scope = FileScope(write=["linked/**/*"])
    writer = ScopedWriter(project_dir, scope)

    with pytest.raises(ScopeError):
        writer.write("linked/foo.txt", "x")


def test_multiple_patterns_each_match(project_dir: Path) -> None:
    scope = FileScope(write=["out.json", "papers/**/*.tex", "logs/*.log"])
    writer = ScopedWriter(project_dir, scope)

    p1 = writer.write("out.json", "{}")
    p2 = writer.write("papers/draft/main.tex", "\\documentclass{}")
    p3 = writer.write("logs/run.log", "ok")

    assert p1.read_text() == "{}"
    assert p2.read_text() == "\\documentclass{}"
    assert p3.read_text() == "ok"


def test_write_bytes(project_dir: Path) -> None:
    scope = FileScope(write=["data/*.bin"])
    writer = ScopedWriter(project_dir, scope)

    p = writer.write("data/blob.bin", b"\x00\x01\x02")
    assert p.read_bytes() == b"\x00\x01\x02"


# ---------------------------------------------------------------------------
# Read scope
# ---------------------------------------------------------------------------


def test_read_scope_default_allows_all(project_dir: Path) -> None:
    (project_dir / "any.txt").write_text("hi")
    scope = FileScope(write=["nope/*"])  # read defaults to ["**/*"]
    writer = ScopedWriter(project_dir, scope)

    assert writer.read("any.txt") == b"hi"


def test_read_scope_restrictive(project_dir: Path) -> None:
    (project_dir / "ok.json").write_text("{}")
    (project_dir / "secret.txt").write_text("nope")
    scope = FileScope(write=[], read=["*.json"])
    writer = ScopedWriter(project_dir, scope)

    assert writer.read("ok.json") == b"{}"
    with pytest.raises(ScopeError):
        writer.read("secret.txt")


def test_read_rejects_traversal(project_dir: Path) -> None:
    scope = FileScope(write=[], read=["**/*"])
    writer = ScopedWriter(project_dir, scope)

    with pytest.raises(ScopeError):
        writer.read("../etc-passwd")


# ---------------------------------------------------------------------------
# Static helper
# ---------------------------------------------------------------------------


def test_matches_helper() -> None:
    assert ScopedWriter.matches("papers/sec/intro.tex", ["papers/**/*.tex"])
    assert ScopedWriter.matches("out.json", ["out.json"])
    assert not ScopedWriter.matches("notes.txt", ["papers/**/*.tex"])
    assert ScopedWriter.matches("logs/run.log", ["logs/*.log", "out.json"])
