"""
LangGraph checkpointer factory.

Plato graphs were previously built with `MemorySaver()`, which means a
process crash mid-paper-write loses tens of thousands of tokens of work.
`make_checkpointer()` returns a durable checkpointer (SQLite by default,
Postgres opt-in) using the same LangGraph BaseCheckpointSaver interface
so the graph builders need no other change.

Backends
--------
- ``memory``  : in-process only; previous default. Useful for tests.
- ``sqlite``  : default; persists to ``~/.plato/state.db`` (override with
                ``path``). Survives crashes and restarts.
- ``postgres``: opt-in for multi-tenant/dashboard deployments. Requires
                ``langgraph-checkpoint-postgres`` and a ``dsn`` keyword.

The sqlite/postgres backends are imported lazily so installs without the
extra checkpointer packages still work — they fall back to memory with
a one-time warning.
"""
from __future__ import annotations

import os
import sqlite3
import warnings
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver

Backend = Literal["memory", "sqlite", "postgres"]

_DEFAULT_SQLITE_PATH = "~/.plato/state.db"


def _resolve_sqlite_path(path: str | os.PathLike[str]) -> Path:
    expanded = Path(path).expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    return expanded


def make_checkpointer(
    backend: Backend = "sqlite",
    *,
    path: str | os.PathLike[str] | None = None,
    dsn: str | None = None,
    **_kw: Any,
):
    """
    Return a LangGraph checkpointer for the requested backend.

    Falls back to ``MemorySaver`` with a warning if the requested backend's
    extra package is not installed.
    """
    if backend == "memory":
        return MemorySaver()

    if backend == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError:
            warnings.warn(
                "langgraph-checkpoint-sqlite is not installed; "
                "falling back to MemorySaver. Install with "
                "`pip install langgraph-checkpoint-sqlite` for crash-resumable runs.",
                RuntimeWarning,
                stacklevel=2,
            )
            return MemorySaver()

        resolved = _resolve_sqlite_path(path or _DEFAULT_SQLITE_PATH)
        conn = sqlite3.connect(str(resolved), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return SqliteSaver(conn)

    if backend == "postgres":
        if not dsn:
            raise ValueError("postgres backend requires a `dsn` keyword argument")
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError:
            warnings.warn(
                "langgraph-checkpoint-postgres is not installed; "
                "falling back to MemorySaver. Install with "
                "`pip install langgraph-checkpoint-postgres`.",
                RuntimeWarning,
                stacklevel=2,
            )
            return MemorySaver()

        return PostgresSaver.from_conn_string(dsn)

    raise ValueError(f"Unknown checkpointer backend: {backend!r}")
