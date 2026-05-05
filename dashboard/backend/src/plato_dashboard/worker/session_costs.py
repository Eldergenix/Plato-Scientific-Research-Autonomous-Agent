"""Per-user session cost ledger.

Backs the demo budget meter. ``run_manager`` calls
:func:`add_session_cost` after each run is reconciled; the capabilities
middleware reads it back via :func:`get_session_cost` so
``require_under_budget`` actually bites instead of comparing against a
hardcoded zero.

In single-user mode the user id is the empty string, so we map that to a
stable ``__local__`` key. The ledger is process-local — Phase 2 will
move it behind Redis once multi-worker deploys land. Thread-safe via a
single module-level lock.
"""

from __future__ import annotations

import threading

_LOCAL_KEY = "__local__"

_session_used: dict[str, int] = {}
_lock = threading.Lock()


def _normalize(user_id: str | None) -> str:
    if not user_id:
        return _LOCAL_KEY
    return user_id


def add_session_cost(user_id: str | None, cents: int) -> int:
    """Increment the running cost for ``user_id`` and return the new total.

    Negative or non-int ``cents`` collapse to zero so a bad caller can
    never *reduce* the meter.
    """
    delta = max(int(cents or 0), 0)
    key = _normalize(user_id)
    with _lock:
        total = _session_used.get(key, 0) + delta
        _session_used[key] = total
        return total


def get_session_cost(user_id: str | None) -> int:
    """Return the running cost in cents for ``user_id`` (0 if unseen)."""
    key = _normalize(user_id)
    with _lock:
        return _session_used.get(key, 0)


def reset_session_cost(user_id: str | None) -> None:
    """Drop the ledger entry for ``user_id`` (test / logout helper)."""
    key = _normalize(user_id)
    with _lock:
        _session_used.pop(key, None)


def clear_all() -> None:
    """Drop every entry. Test fixture only."""
    with _lock:
        _session_used.clear()


__all__ = [
    "add_session_cost",
    "get_session_cost",
    "reset_session_cost",
    "clear_all",
]
