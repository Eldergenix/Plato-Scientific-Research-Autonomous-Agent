"""Phase 1 — R2: make_checkpointer() factory."""
from __future__ import annotations

from pathlib import Path

import pytest

from plato.state import make_checkpointer


def test_memory_backend_returns_memory_saver():
    """The memory backend always returns a MemorySaver instance."""
    from langgraph.checkpoint.memory import MemorySaver

    cp = make_checkpointer("memory")
    assert isinstance(cp, MemorySaver)


def test_sqlite_backend_returns_sqlite_or_falls_back(tmp_path: Path):
    """
    The sqlite backend either returns a SqliteSaver, or falls back to
    MemorySaver with a warning if `langgraph-checkpoint-sqlite` isn't
    installed. Both are acceptable Phase 1 outcomes.
    """
    from langgraph.checkpoint.memory import MemorySaver

    db_path = tmp_path / "state.db"
    with pytest.warns() if not _sqlite_available() else _no_warn():
        cp = make_checkpointer("sqlite", path=str(db_path))

    if _sqlite_available():
        # Real durable backend.
        from langgraph.checkpoint.sqlite import SqliteSaver

        assert isinstance(cp, SqliteSaver)
        assert db_path.exists()
    else:
        # Graceful fallback.
        assert isinstance(cp, MemorySaver)


def test_postgres_backend_requires_dsn():
    with pytest.raises(ValueError, match="dsn"):
        make_checkpointer("postgres")


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="Unknown checkpointer backend"):
        make_checkpointer("oracle")  # type: ignore[arg-type]


# --- helpers --------------------------------------------------------------


def _sqlite_available() -> bool:
    try:
        import langgraph.checkpoint.sqlite  # noqa: F401
        return True
    except ImportError:
        return False


class _no_warn:
    """Context manager: assert no RuntimeWarning is emitted."""

    def __enter__(self):
        import warnings

        self._cm = warnings.catch_warnings(record=True)
        self._caught = self._cm.__enter__()
        warnings.simplefilter("always")
        return self

    def __exit__(self, *a):
        result = self._cm.__exit__(*a)
        runtime = [w for w in self._caught if issubclass(w.category, RuntimeWarning)]
        assert not runtime, f"unexpected RuntimeWarning(s): {[str(w.message) for w in runtime]}"
        return result
