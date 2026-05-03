"""Unit tests for :class:`plato.executor.e2b_backend.E2BExecutor`.

We deliberately do **not** exercise actual sandbox execution — that needs
``E2B_API_KEY`` and would burn paid sandbox-minutes. The tests cover the
boundary between Plato and the SDK: missing SDK, missing credentials,
empty input, and the importability invariant.
"""
from __future__ import annotations

import asyncio
import builtins
import sys

import pytest

from plato.executor import ExecutorResult, get_executor
from plato.executor.e2b_backend import E2BExecutor


def _drive(executor: E2BExecutor, **overrides) -> ExecutorResult:
    """Helper: synchronously call the async ``run`` with sensible defaults."""
    payload = {
        "research_idea": "i",
        "methodology": "print('hello')",
        "data_description": "d",
        "project_dir": "/tmp",
        "keys": None,
    }
    payload.update(overrides)
    return asyncio.run(executor.run(**payload))


def test_module_imports_when_sdk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing ``plato.executor.e2b_backend`` must not require the SDK."""
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", None)
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "e2b_code_interpreter":
            raise ImportError("simulated: no e2b in this env")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    sys.modules.pop("plato.executor.e2b_backend", None)
    import importlib

    mod = importlib.import_module("plato.executor.e2b_backend")
    assert hasattr(mod, "E2BExecutor")


def test_run_returns_structured_failure_when_sdk_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the SDK can't be imported, ``run`` returns ``success=False``."""
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", None)
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "e2b_code_interpreter":
            raise ImportError("simulated: no e2b SDK")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    ex = E2BExecutor()
    result = _drive(ex)

    assert isinstance(result, ExecutorResult)
    assert result.artifacts["backend"] == "e2b"
    assert result.artifacts["success"] is False
    assert result.artifacts["stage"] == "sdk_import"
    error = result.artifacts["error"]
    assert "E2B SDK not installed" in error
    assert "e2b-code-interpreter" in error
    assert "E2B_API_KEY" in error
    assert "E2BExecutor failed" in result.results


def test_run_returns_credential_error_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the SDK imports but no API key is reachable, surface a cred error."""

    class _FakeSandbox:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Sandbox should not be instantiated when creds missing")

    ex = E2BExecutor()
    ex._sandbox_cls = _FakeSandbox  # bypass lazy import
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    result = _drive(ex)
    assert result.artifacts["success"] is False
    assert result.artifacts["stage"] == "credentials"
    assert "E2B_API_KEY" in result.artifacts["error"]


def test_run_returns_validation_error_for_empty_methodology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty methodology must short-circuit before we hit the network."""

    class _FakeSandbox:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Sandbox should not be instantiated for empty input")

    ex = E2BExecutor()
    ex._sandbox_cls = _FakeSandbox
    monkeypatch.setenv("E2B_API_KEY", "fake-key-not-used")

    result = _drive(ex, methodology="", research_idea="")
    assert result.artifacts["success"] is False
    assert result.artifacts["stage"] == "input_validation"


def test_executor_is_registered_under_e2b() -> None:
    """The skeleton still self-registers so DomainProfile.executor='e2b' works."""
    ex = get_executor("e2b")
    # See test_modal_executor.py for why this isn't an isinstance check.
    assert type(ex).__name__ == "E2BExecutor"
    assert ex.name == "e2b"


def test_lazy_init_caches_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed ``_lazy_init`` must not retry on every ``run`` call."""
    real_import = builtins.__import__
    call_count = {"n": 0}

    def _fake_import(name, *args, **kwargs):
        if name == "e2b_code_interpreter":
            call_count["n"] += 1
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    ex = E2BExecutor()
    _drive(ex)
    _drive(ex)
    _drive(ex)
    assert call_count["n"] == 1, "import was retried on every run"


def test_lazy_init_returns_class_when_sdk_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the SDK is importable, ``_lazy_init`` returns the Sandbox class + no error."""

    class _FakeSandbox:
        pass

    fake_module = type(sys)("e2b_code_interpreter")
    fake_module.Sandbox = _FakeSandbox  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", fake_module)

    ex = E2BExecutor()
    Sandbox, err = ex._lazy_init()
    assert err is None
    assert Sandbox is _FakeSandbox
    # And the cached value comes back on the second call.
    assert ex._lazy_init() == (_FakeSandbox, None)


def test_lazy_init_success_with_creds_passes_credential_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK present + ``E2B_API_KEY`` set: no init error, no credential error."""

    class _FakeSandbox:
        pass

    fake_module = type(sys)("e2b_code_interpreter")
    fake_module.Sandbox = _FakeSandbox  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", fake_module)
    monkeypatch.setenv("E2B_API_KEY", "test-key")

    ex = E2BExecutor()
    Sandbox, err = ex._lazy_init()
    assert err is None and Sandbox is _FakeSandbox
    assert ex._check_credentials(None) is None


def test_lazy_init_succeeds_but_credential_check_fails_when_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK present + ``E2B_API_KEY`` absent: ``_lazy_init`` is OK, cred probe fires."""

    class _FakeSandbox:
        pass

    fake_module = type(sys)("e2b_code_interpreter")
    fake_module.Sandbox = _FakeSandbox  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", fake_module)
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    ex = E2BExecutor()
    Sandbox, err = ex._lazy_init()
    assert err is None and Sandbox is _FakeSandbox
    cred_err = ex._check_credentials(None)
    assert cred_err is not None
    assert "E2B_API_KEY" in cred_err
