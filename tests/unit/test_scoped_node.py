"""Unit tests for the R11 scoped_node decorator (iter 13)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from plato.io import FileScope, ScopedWriter, ScopeError, scoped_node
from plato.io.scoped_writer import writer_for_node


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    pd = tmp_path / "proj"
    pd.mkdir()
    return pd


def _state(project_dir: Path) -> dict:
    return {"files": {"Folder": str(project_dir)}}


def test_sync_node_gets_scoped_writer(project_dir: Path) -> None:
    captured: dict = {}

    def node(state: dict) -> dict:
        captured["writer"] = state.get("_writer")
        return {}

    wrapped = scoped_node(node, FileScope(write=["out.txt"]))
    wrapped(_state(project_dir))

    assert isinstance(captured["writer"], ScopedWriter)


def test_sync_node_in_scope_write_succeeds(project_dir: Path) -> None:
    def node(state: dict) -> dict:
        writer: ScopedWriter = state["_writer"]
        writer.write("output.log", "ok")
        return {}

    wrapped = scoped_node(node, FileScope(write=["output.log"]))
    wrapped(_state(project_dir))

    assert (project_dir / "output.log").read_text() == "ok"


def test_sync_node_out_of_scope_write_raises(project_dir: Path) -> None:
    def node(state: dict) -> dict:
        writer: ScopedWriter = state["_writer"]
        writer.write("escape.txt", "blocked")
        return {}

    wrapped = scoped_node(node, FileScope(write=["only_this.txt"]))

    with pytest.raises(ScopeError):
        wrapped(_state(project_dir))


def test_async_node_gets_scoped_writer(project_dir: Path) -> None:
    captured: dict = {}

    async def node(state: dict) -> dict:
        captured["writer"] = state.get("_writer")
        return {}

    wrapped = scoped_node(node, FileScope(write=["x"]))
    asyncio.run(wrapped(_state(project_dir)))

    assert isinstance(captured["writer"], ScopedWriter)


def test_async_node_out_of_scope_raises(project_dir: Path) -> None:
    async def node(state: dict) -> dict:
        state["_writer"].write("../etc/passwd", "leak")
        return {}

    wrapped = scoped_node(node, FileScope(write=["allowed.txt"]))

    with pytest.raises(ScopeError):
        asyncio.run(wrapped(_state(project_dir)))


def test_wrapper_does_not_mutate_caller_state(project_dir: Path) -> None:
    """The state dict the caller passes in should not gain a ``_writer`` key."""
    caller_state = _state(project_dir)

    def node(state: dict) -> dict:
        # The wrapped node sees _writer, but the caller's state must not.
        return {}

    wrapped = scoped_node(node, FileScope(write=["x"]))
    wrapped(caller_state)

    assert "_writer" not in caller_state


def test_wrapper_preserves_function_metadata(project_dir: Path) -> None:
    """Wrapped function should report the original ``__name__`` for LangGraph debug."""

    def my_node(state: dict) -> dict:
        return {}

    wrapped = scoped_node(my_node, FileScope(write=["x"]))
    assert wrapped.__name__ == "my_node"


def test_wrapper_async_preserves_function_metadata(project_dir: Path) -> None:
    async def my_async_node(state: dict) -> dict:
        return {}

    wrapped = scoped_node(my_async_node, FileScope(write=["x"]))
    assert wrapped.__name__ == "my_async_node"


def test_wrapper_returns_node_result(project_dir: Path) -> None:
    def node(state: dict) -> dict:
        return {"updated": True, "value": 42}

    wrapped = scoped_node(node, FileScope(write=["x"]))
    result = wrapped(_state(project_dir))
    assert result == {"updated": True, "value": 42}


def test_wrapper_async_returns_node_result(project_dir: Path) -> None:
    async def node(state: dict) -> dict:
        return {"async_updated": True}

    wrapped = scoped_node(node, FileScope(write=["x"]))
    result = asyncio.run(wrapped(_state(project_dir)))
    assert result == {"async_updated": True}


# --- Added edge-case tests below this line --------------------------------


def test_writer_rejects_absolute_path(project_dir: Path) -> None:
    """ScopedWriter._resolve must reject absolute paths up front."""
    writer = ScopedWriter(project_dir, FileScope(write=["**/*"]))
    with pytest.raises(ScopeError, match="absolute"):
        writer.write("/etc/passwd", "leak")


def test_writer_rejects_parent_traversal(project_dir: Path) -> None:
    """A relative path containing '..' must be rejected even with permissive scope."""
    writer = ScopedWriter(project_dir, FileScope(write=["**/*"]))
    with pytest.raises(ScopeError, match="parent-traversal"):
        writer.write("../escape.txt", "nope")


def test_writer_rejects_empty_path(project_dir: Path) -> None:
    """Empty string path is invalid for any operation."""
    writer = ScopedWriter(project_dir, FileScope(write=["**/*"]))
    with pytest.raises(ScopeError, match="empty"):
        writer.write("", "nope")


def test_writer_rejects_symlink_inside_project(project_dir: Path, tmp_path: Path) -> None:
    """Even a symlink whose target is inside project_dir must be refused."""
    if sys.platform.startswith("win"):
        pytest.skip("symlinks require admin on Windows")

    real = project_dir / "real.txt"
    real.write_text("hello")
    link = project_dir / "link.txt"
    os.symlink(real, link)

    writer = ScopedWriter(project_dir, FileScope(write=["link.txt", "real.txt"]))
    with pytest.raises(ScopeError, match="symlink"):
        writer.write("link.txt", "stomp")


def test_writer_rejects_symlink_escape(project_dir: Path, tmp_path: Path) -> None:
    """A symlink pointing outside project_dir must be refused via containment check."""
    if sys.platform.startswith("win"):
        pytest.skip("symlinks require admin on Windows")

    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = project_dir / "escape.txt"
    os.symlink(outside, link)

    writer = ScopedWriter(project_dir, FileScope(write=["escape.txt"]))
    with pytest.raises(ScopeError):
        writer.write("escape.txt", "leaked")


def test_writer_creates_parent_directories(project_dir: Path) -> None:
    """Nested writes must auto-mkdir parent directories."""
    writer = ScopedWriter(project_dir, FileScope(write=["a/b/c/file.txt"]))
    target = writer.write("a/b/c/file.txt", "deep")
    assert target.read_text() == "deep"
    assert (project_dir / "a" / "b" / "c").is_dir()


def test_writer_round_trip_bytes(project_dir: Path) -> None:
    """Bytes content should round-trip through write/read identically."""
    writer = ScopedWriter(project_dir, FileScope(write=["bin.dat"], read=["bin.dat"]))
    payload = b"\x00\x01\x02\xff"
    writer.write("bin.dat", payload)
    assert writer.read("bin.dat") == payload


def test_writer_read_blocked_by_scope(project_dir: Path) -> None:
    """A file outside the read scope cannot be read even if it exists."""
    secret = project_dir / "secret.txt"
    secret.write_text("classified")
    writer = ScopedWriter(project_dir, FileScope(write=[], read=["allowed.txt"]))
    with pytest.raises(ScopeError, match="does not match"):
        writer.read("secret.txt")


def test_writer_default_read_scope_allows_anything(project_dir: Path) -> None:
    """Default read scope is ``['**/*']`` — should match top-level files too."""
    (project_dir / "anywhere.txt").write_text("ok")
    writer = ScopedWriter(project_dir, FileScope(write=["whatever"]))  # default read
    assert writer.read("anywhere.txt") == b"ok"


def test_writer_glob_pattern_matches_nested(project_dir: Path) -> None:
    """``papers/**/*.tex`` allows nested writes; non-matching extension fails."""
    writer = ScopedWriter(project_dir, FileScope(write=["papers/**/*.tex"]))
    target = writer.write("papers/sec/intro.tex", "\\section{x}")
    assert target.read_text() == "\\section{x}"

    with pytest.raises(ScopeError, match="does not match"):
        writer.write("papers/sec/intro.md", "wrong ext")


def test_writer_for_node_requires_scope(project_dir: Path) -> None:
    """writer_for_node refuses to fabricate a default scope."""
    with pytest.raises(ValueError, match="FileScope is required"):
        writer_for_node(project_dir, "some_node", scope=None)


def test_writer_for_node_returns_scoped_writer(project_dir: Path) -> None:
    """Happy path: writer_for_node yields a ScopedWriter rooted at project_dir."""
    scope = FileScope(write=["x.txt"])
    w = writer_for_node(project_dir, "node_a", scope=scope)
    assert isinstance(w, ScopedWriter)
    assert w.project_dir == project_dir.resolve()
    assert w.scope is scope


def test_scope_matches_short_filename() -> None:
    """``out.json`` pattern must match exact filename at root."""
    assert ScopedWriter.matches("out.json", ["out.json"]) is True
    assert ScopedWriter.matches("other.json", ["out.json"]) is False


def test_scope_matches_double_star_prefix() -> None:
    """``**/*`` must match both root files and nested paths."""
    assert ScopedWriter.matches("file.txt", ["**/*"]) is True
    assert ScopedWriter.matches("a/b/file.txt", ["**/*"]) is True


def test_scope_matches_no_pattern_means_no_match() -> None:
    """An empty pattern list rejects everything."""
    assert ScopedWriter.matches("anything", []) is False
