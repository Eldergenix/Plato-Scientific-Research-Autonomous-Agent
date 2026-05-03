"""Unit tests for the R11 scoped_node decorator (iter 13)."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from plato.io import FileScope, ScopedWriter, ScopeError, scoped_node


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
