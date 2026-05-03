"""R8 — observability hook tests.

These exercise three branches of the LangFuse integration without
needing the LangFuse SDK installed:

1. No env vars → ``None`` (no traces, no warnings).
2. Env vars present, ``langfuse`` package missing → ``None`` plus a
   ``RuntimeWarning`` so misconfigured setups don't fail silently.
3. Env vars present, fake ``langfuse.callback`` module installed →
   returns a handler instance with the supplied ``session_id`` and
   ``metadata``.

The fake module is a stand-in for the real LangFuse SDK and lives in
``sys.modules`` only for the duration of one test, so this file does
not depend on the optional ``plato[obs]`` extra being installed in CI.
"""
from __future__ import annotations

import sys
import types
import warnings
from typing import Any

import pytest

from plato.observability import callbacks_for, get_langfuse_callback


@pytest.fixture(autouse=True)
def _isolate_langfuse_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip any developer-supplied LangFuse env vars per-test."""
    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(var, raising=False)


def test_returns_none_when_env_vars_missing() -> None:
    """No keys → no handler, no warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning fails the test
        assert get_langfuse_callback(session_id="run-1") is None
        assert callbacks_for("run-1", "get_paper") == []


def test_warns_when_keys_present_but_package_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keys set + langfuse not installed → returns None and warns once."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    # Simulate "package not installed" by ensuring the import path
    # resolves to a module that doesn't have ``CallbackHandler``.
    monkeypatch.setitem(sys.modules, "langfuse", types.ModuleType("langfuse"))
    monkeypatch.delitem(sys.modules, "langfuse.callback", raising=False)

    with pytest.warns(RuntimeWarning, match="LANGFUSE"):
        assert get_langfuse_callback(session_id="run-2") is None


def test_returns_handler_when_env_and_package_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keys + a fake ``langfuse.callback`` module → handler instance."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    captured: dict[str, Any] = {}

    class _FakeHandler:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)
            self.kwargs = kwargs

    fake_module = types.ModuleType("langfuse.callback")
    fake_module.CallbackHandler = _FakeHandler  # type: ignore[attr-defined]
    fake_pkg = types.ModuleType("langfuse")
    fake_pkg.callback = fake_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_pkg)
    monkeypatch.setitem(sys.modules, "langfuse.callback", fake_module)

    handler = get_langfuse_callback(
        session_id="run-3",
        user_id="alice",
        metadata={"workflow": "get_paper"},
    )

    assert isinstance(handler, _FakeHandler)
    assert captured["session_id"] == "run-3"
    assert captured["user_id"] == "alice"
    assert captured["metadata"] == {"workflow": "get_paper"}


def test_callbacks_for_returns_list_with_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The convenience helper wraps the handler in a list for LangGraph configs."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    class _FakeHandler:
        def __init__(self, **kwargs: Any) -> None:
            self.session_id = kwargs.get("session_id")

    fake_module = types.ModuleType("langfuse.callback")
    fake_module.CallbackHandler = _FakeHandler  # type: ignore[attr-defined]
    fake_pkg = types.ModuleType("langfuse")
    fake_pkg.callback = fake_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_pkg)
    monkeypatch.setitem(sys.modules, "langfuse.callback", fake_module)

    callbacks = callbacks_for("run-4", "get_idea_fast")
    assert len(callbacks) == 1
    assert getattr(callbacks[0], "session_id", None) == "run-4"
