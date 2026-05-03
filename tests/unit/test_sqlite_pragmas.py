"""Iter 18: pin the SQLite WAL + concurrency PRAGMAs on the checkpointer connection.

The Phase-1 ``make_checkpointer('sqlite')`` factory used to set only
``PRAGMA journal_mode=WAL`` and call it a day. That left two real gaps
under the dashboard worker pool:

1. No ``busy_timeout`` — concurrent writers raised ``database is
   locked`` instantly instead of waiting for the lock holder.
2. No ``synchronous=NORMAL`` — every checkpoint commit paid the cost
   of a full ``fsync`` on the main DB file, which is overkill once
   WAL is on (the WAL itself is fsync'd; durability is preserved).

These tests pin the four PRAGMAs the iter-18 hardening sets so a
future refactor that swaps the connection setup can't silently regress
the contract.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from plato.state.checkpointer import (
    _SQLITE_BUSY_TIMEOUT_MS,
    _apply_concurrency_pragmas,
    make_checkpointer,
)


def _sqlite_saver_available() -> bool:
    try:
        import langgraph.checkpoint.sqlite  # noqa: F401
        return True
    except ImportError:
        return False


def _read_pragma(conn: sqlite3.Connection, name: str) -> object:
    cur = conn.execute(f"PRAGMA {name}")
    row = cur.fetchone()
    return row[0] if row else None


def test_apply_concurrency_pragmas_sets_wal(tmp_path: Path) -> None:
    db = tmp_path / "pragmas.db"
    conn = sqlite3.connect(str(db))
    try:
        _apply_concurrency_pragmas(conn)
        assert _read_pragma(conn, "journal_mode") == "wal"
    finally:
        conn.close()


def test_apply_concurrency_pragmas_sets_synchronous_normal(tmp_path: Path) -> None:
    db = tmp_path / "sync.db"
    conn = sqlite3.connect(str(db))
    try:
        _apply_concurrency_pragmas(conn)
        # SQLite returns the integer code: 0=OFF, 1=NORMAL, 2=FULL, 3=EXTRA.
        assert _read_pragma(conn, "synchronous") == 1
    finally:
        conn.close()


def test_apply_concurrency_pragmas_sets_busy_timeout(tmp_path: Path) -> None:
    db = tmp_path / "busy.db"
    conn = sqlite3.connect(str(db))
    try:
        _apply_concurrency_pragmas(conn)
        assert _read_pragma(conn, "busy_timeout") == _SQLITE_BUSY_TIMEOUT_MS
    finally:
        conn.close()


def test_apply_concurrency_pragmas_sets_wal_autocheckpoint(tmp_path: Path) -> None:
    db = tmp_path / "autock.db"
    conn = sqlite3.connect(str(db))
    try:
        _apply_concurrency_pragmas(conn)
        assert _read_pragma(conn, "wal_autocheckpoint") == 1000
    finally:
        conn.close()


def test_apply_concurrency_pragmas_is_idempotent(tmp_path: Path) -> None:
    """Re-applying the helper on the same connection must not raise or change values."""
    db = tmp_path / "idem.db"
    conn = sqlite3.connect(str(db))
    try:
        _apply_concurrency_pragmas(conn)
        first = (
            _read_pragma(conn, "journal_mode"),
            _read_pragma(conn, "synchronous"),
            _read_pragma(conn, "busy_timeout"),
            _read_pragma(conn, "wal_autocheckpoint"),
        )
        # Re-apply.
        _apply_concurrency_pragmas(conn)
        second = (
            _read_pragma(conn, "journal_mode"),
            _read_pragma(conn, "synchronous"),
            _read_pragma(conn, "busy_timeout"),
            _read_pragma(conn, "wal_autocheckpoint"),
        )
        assert first == second
    finally:
        conn.close()


@pytest.mark.skipif(
    not _sqlite_saver_available(),
    reason="langgraph-checkpoint-sqlite not installed",
)
def test_make_checkpointer_sqlite_applies_pragmas(tmp_path: Path) -> None:
    """The ``sqlite`` backend must apply every concurrency PRAGMA on its connection."""
    db = tmp_path / "factory.db"
    cp = make_checkpointer("sqlite", path=str(db))

    # SqliteSaver exposes the underlying connection as ``.conn``. We fall
    # back to attribute introspection so the test isn't tied to a private
    # attribute name across LangGraph versions.
    conn = getattr(cp, "conn", None)
    if conn is None:
        # Newer LangGraph versions name it differently — skip gracefully.
        pytest.skip("SqliteSaver connection attribute not exposed in this version")

    assert _read_pragma(conn, "journal_mode") == "wal"
    assert _read_pragma(conn, "synchronous") == 1
    assert _read_pragma(conn, "busy_timeout") == _SQLITE_BUSY_TIMEOUT_MS


def test_busy_timeout_makes_concurrent_write_wait(tmp_path: Path) -> None:
    """A second writer must block on the lock instead of raising immediately.

    Without ``busy_timeout`` the second connection raises
    ``OperationalError("database is locked")`` the moment it touches
    a locked write. With the helper applied, it waits up to the
    configured timeout and then succeeds. We use a short artificial
    hold (50ms) to keep the test fast — the assertion is "did NOT
    raise", not a precise timing measurement.
    """
    db = tmp_path / "busy_test.db"

    # Bootstrap the schema.
    boot = sqlite3.connect(str(db))
    boot.execute("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)")
    boot.commit()
    boot.close()

    holder = sqlite3.connect(str(db), timeout=0)
    holder.execute("BEGIN IMMEDIATE")  # acquire the write lock
    holder.execute("INSERT INTO t (v) VALUES ('a')")

    # Release the lock after a short delay so the contender can succeed.
    def release() -> None:
        import time

        time.sleep(0.1)
        holder.commit()
        holder.close()

    threading.Thread(target=release, daemon=True).start()

    contender = sqlite3.connect(str(db))
    _apply_concurrency_pragmas(contender)
    try:
        # This MUST not raise. Without busy_timeout it raises
        # immediately; with our 10-second budget it waits for the
        # holder to release.
        contender.execute("INSERT INTO t (v) VALUES ('b')")
        contender.commit()
        rows = list(contender.execute("SELECT v FROM t ORDER BY k"))
        assert rows == [("a",), ("b",)]
    finally:
        contender.close()
