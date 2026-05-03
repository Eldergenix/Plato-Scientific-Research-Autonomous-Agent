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

# ``MemorySaver`` is the fallback path; lazy-import so plato.state
# (which is imported by every graph builder) doesn't pay the
# langgraph.checkpoint.memory import cost on every fresh process —
# even when the caller picks ``sqlite`` or ``postgres`` and never
# touches MemorySaver.

Backend = Literal["memory", "sqlite", "postgres"]


def _memory_saver():
    """Lazy import of MemorySaver — see module-level note."""
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()

_DEFAULT_SQLITE_PATH = "~/.plato/state.db"

# SQLite busy-timeout in milliseconds. Sets how long a write transaction
# will wait for a competing writer to release the lock before raising
# ``sqlite3.OperationalError("database is locked")``. The dashboard
# worker pool (R2 risk register R6) can produce overlapping checkpoint
# writes from concurrent runs; without this, the second writer fails
# instantly. 10 seconds is long enough to absorb realistic contention
# but short enough that a real deadlock surfaces quickly.
_SQLITE_BUSY_TIMEOUT_MS = 10_000


def _resolve_sqlite_path(path: str | os.PathLike[str]) -> Path:
    expanded = Path(path).expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    return expanded


def _apply_concurrency_pragmas(conn: sqlite3.Connection) -> None:
    """Set the WAL + concurrency PRAGMAs the LangGraph checkpointer needs.

    - ``journal_mode=WAL``: enables concurrent readers + a single writer
      (the default ``DELETE`` mode serialises everything).
    - ``synchronous=NORMAL``: with WAL this is safe — the WAL file is
      still fsync'd on commit, only the main DB file's checkpoint sync
      is relaxed. Durability under app crash is preserved; only sudden
      power loss can lose the very last commit, which is acceptable for
      a checkpointer that auto-rebuilds from state.
    - ``busy_timeout``: see :data:`_SQLITE_BUSY_TIMEOUT_MS`.
    - ``wal_autocheckpoint=1000``: keep the WAL file from growing
      unbounded under heavy load (default is also 1000 but stating it
      explicitly documents the contract).

    All four PRAGMAs are idempotent — re-applying them on a reused
    connection is a no-op, so callers who want to re-harden a borrowed
    handle can call this helper directly.
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA wal_autocheckpoint=1000")


def make_checkpointer(
    backend: Backend = "sqlite",
    *,
    path: str | os.PathLike[str] | None = None,
    dsn: str | None = None,
    **kwargs: Any,
):
    """
    Return a LangGraph checkpointer for the requested backend.

    Falls back to ``MemorySaver`` with a warning if the requested backend's
    extra package is not installed.

    Unknown keyword arguments emit a ``RuntimeWarning`` rather than being
    silently swallowed — typos in caller code should not produce a
    correct-looking checkpointer with a misconfigured backend.
    """
    if kwargs:
        warnings.warn(
            f"make_checkpointer received unexpected keyword arguments: "
            f"{sorted(kwargs)}. They will be ignored. Known kwargs: "
            f"path (sqlite), dsn (postgres).",
            RuntimeWarning,
            stacklevel=2,
        )
    if backend == "memory":
        if path is not None or dsn is not None:
            warnings.warn(
                "make_checkpointer('memory') ignores 'path' and 'dsn'.",
                RuntimeWarning,
                stacklevel=2,
            )
        return _memory_saver()

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
            return _memory_saver()

        resolved = _resolve_sqlite_path(path or _DEFAULT_SQLITE_PATH)
        conn = sqlite3.connect(str(resolved), check_same_thread=False)
        _apply_concurrency_pragmas(conn)
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
            return _memory_saver()

        return PostgresSaver.from_conn_string(dsn)

    raise ValueError(f"Unknown checkpointer backend: {backend!r}")
