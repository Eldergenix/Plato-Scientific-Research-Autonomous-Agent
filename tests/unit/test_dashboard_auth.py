"""Phase 5 — dashboard auth helpers.

Covers ``extract_user_id`` (header → string | None) and
``require_user_id`` (raises 401 only in required-mode). The dashboard
package lives under ``dashboard/backend/src``; we add it to ``sys.path``
on import so this test runs from the repo-root pytest invocation.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Make the dashboard backend src importable without installing it.
_DASHBOARD_SRC = (
    Path(__file__).resolve().parents[2] / "dashboard" / "backend" / "src"
)
if str(_DASHBOARD_SRC) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_SRC))

from fastapi import HTTPException

from plato_dashboard.auth import (  # noqa: E402
    AUTH_REQUIRED_ENV,
    USER_HEADER,
    auth_required,
    extract_user_id,
    require_user_id,
)


def _request_with_headers(headers: dict[str, str]) -> Any:
    """Build a minimal stub Request with a ``.headers.get`` interface."""
    req = MagicMock()
    req.headers = headers
    return req


def test_extract_user_id_returns_header_value() -> None:
    req = _request_with_headers({USER_HEADER: "alice"})
    assert extract_user_id(req) == "alice"


def test_extract_user_id_strips_whitespace() -> None:
    req = _request_with_headers({USER_HEADER: "  bob \t"})
    assert extract_user_id(req) == "bob"


def test_extract_user_id_missing_returns_none() -> None:
    req = _request_with_headers({})
    assert extract_user_id(req) is None


def test_extract_user_id_empty_string_returns_none() -> None:
    """An empty header (or one that's all whitespace) is treated as missing."""
    req = _request_with_headers({USER_HEADER: "   "})
    assert extract_user_id(req) is None


def test_auth_required_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(AUTH_REQUIRED_ENV, raising=False)
    assert auth_required() is False
    monkeypatch.setenv(AUTH_REQUIRED_ENV, "1")
    assert auth_required() is True
    monkeypatch.setenv(AUTH_REQUIRED_ENV, "0")
    assert auth_required() is False


def test_require_user_id_returns_value_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AUTH_REQUIRED_ENV, "1")
    req = _request_with_headers({USER_HEADER: "alice"})
    assert require_user_id(req) == "alice"


def test_require_user_id_raises_401_when_required_and_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AUTH_REQUIRED_ENV, "1")
    req = _request_with_headers({})
    with pytest.raises(HTTPException) as exc_info:
        require_user_id(req)
    assert exc_info.value.status_code == 401
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == "auth_required"


def test_require_user_id_legacy_returns_empty_when_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single-user / legacy mode: missing header is OK and returns ''."""
    monkeypatch.delenv(AUTH_REQUIRED_ENV, raising=False)
    req = _request_with_headers({})
    assert require_user_id(req) == ""


def test_require_user_id_legacy_passes_through_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy mode still respects the header when supplied."""
    monkeypatch.delenv(AUTH_REQUIRED_ENV, raising=False)
    req = _request_with_headers({USER_HEADER: "carol"})
    assert require_user_id(req) == "carol"
