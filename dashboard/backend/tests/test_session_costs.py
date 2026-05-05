"""Per-user session cost ledger + capabilities meter wiring."""

from __future__ import annotations

import pytest
from fastapi import Request

from plato_dashboard.api.capabilities import _session_used_cents
from plato_dashboard.worker.session_costs import (
    _LOCAL_KEY,
    add_session_cost,
    clear_all,
    get_session_cost,
    reset_session_cost,
)


@pytest.fixture(autouse=True)
def _reset_ledger():
    clear_all()
    yield
    clear_all()


def _mock_request(user_id: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if user_id is not None:
        headers.append((b"x-plato-user", user_id.encode()))
    scope = {"type": "http", "headers": headers, "method": "GET", "path": "/"}
    return Request(scope)


def test_add_then_get_returns_sum() -> None:
    add_session_cost("alice", 10)
    add_session_cost("alice", 25)
    assert get_session_cost("alice") == 35


def test_users_are_isolated() -> None:
    add_session_cost("alice", 10)
    add_session_cost("bob", 7)
    assert get_session_cost("alice") == 10
    assert get_session_cost("bob") == 7


def test_none_and_empty_collapse_to_local_bucket() -> None:
    add_session_cost(None, 4)
    add_session_cost("", 6)
    assert get_session_cost(None) == 10
    assert get_session_cost("") == 10
    # Sanity: explicit local key matches.
    assert get_session_cost(_LOCAL_KEY) == 10


def test_negative_delta_does_not_decrement() -> None:
    add_session_cost("alice", 10)
    add_session_cost("alice", -50)
    assert get_session_cost("alice") == 10


def test_reset_drops_user_only() -> None:
    add_session_cost("alice", 10)
    add_session_cost("bob", 7)
    reset_session_cost("alice")
    assert get_session_cost("alice") == 0
    assert get_session_cost("bob") == 7


def test_capabilities_reflects_ledger_for_authed_request() -> None:
    add_session_cost("alice", 42)
    req = _mock_request("alice")
    assert _session_used_cents(req) == 42


def test_capabilities_falls_back_to_local_bucket_when_unauthed() -> None:
    add_session_cost(None, 13)
    req = _mock_request(None)
    assert _session_used_cents(req) == 13
