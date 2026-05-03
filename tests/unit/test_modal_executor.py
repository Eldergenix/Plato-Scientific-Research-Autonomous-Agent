"""Unit tests for :class:`plato.executor.modal_backend.ModalExecutor`.

We deliberately do **not** exercise actual remote execution — that needs
Modal credentials and would burn paid CPU-seconds. The tests cover the
boundary between Plato and the SDK: missing SDK, missing credentials,
empty input, and the importability invariant.
"""
from __future__ import annotations

import asyncio
import builtins
import sys
from types import SimpleNamespace

import pytest

from plato.executor import ExecutorResult, get_executor
from plato.executor.modal_backend import ModalExecutor


def _drive(executor: ModalExecutor, **overrides) -> ExecutorResult:
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
    """Importing ``plato.executor.modal_backend`` must not require ``modal``.

    We simulate the SDK being absent by removing it from ``sys.modules``
    and patching ``builtins.__import__`` to raise ``ImportError`` for it,
    then re-import the backend module. The import must succeed (the SDK
    is lazy-loaded inside ``run``).
    """
    # Make sure modal is genuinely not importable.
    monkeypatch.setitem(sys.modules, "modal", None)
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "modal":
            raise ImportError("simulated: no modal in this env")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    # Reimporting under the patch must not blow up.
    sys.modules.pop("plato.executor.modal_backend", None)
    import importlib

    mod = importlib.import_module("plato.executor.modal_backend")
    assert hasattr(mod, "ModalExecutor")


def test_run_returns_structured_failure_when_sdk_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``import modal`` fails, ``run`` returns ``success=False``."""
    monkeypatch.setitem(sys.modules, "modal", None)
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "modal":
            raise ImportError("simulated: no modal SDK")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    ex = ModalExecutor()
    result = _drive(ex)

    assert isinstance(result, ExecutorResult)
    assert result.artifacts["backend"] == "modal"
    assert result.artifacts["success"] is False
    assert result.artifacts["stage"] == "sdk_import"
    error = result.artifacts["error"]
    assert "Modal SDK not installed" in error
    assert "pip install modal" in error
    assert "modal token new" in error
    # The markdown body must surface the same actionable hint.
    assert "ModalExecutor failed" in result.results
    assert "pip install modal" in result.results


def test_run_returns_credential_error_when_token_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``modal`` imports but token store is empty, surface a cred error."""
    fake_modal = SimpleNamespace(
        config=SimpleNamespace(config=lambda: {"token_id": None, "token_secret": None}),
    )
    monkeypatch.setitem(sys.modules, "modal", fake_modal)

    ex = ModalExecutor()
    # Bypass the import path — pre-populate the cached module so the
    # executor uses our fake.
    ex._modal = fake_modal

    result = _drive(ex)
    assert result.artifacts["success"] is False
    assert result.artifacts["stage"] == "credentials"
    assert "modal token new" in result.artifacts["error"]


def test_run_returns_validation_error_for_empty_methodology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty methodology must short-circuit before we hit the network."""
    fake_modal = SimpleNamespace(
        config=SimpleNamespace(config=lambda: {"token_id": "tok", "token_secret": "sec"}),
    )
    ex = ModalExecutor()
    ex._modal = fake_modal

    result = _drive(ex, methodology="", research_idea="")
    assert result.artifacts["success"] is False
    assert result.artifacts["stage"] == "input_validation"


def test_executor_is_registered_under_modal() -> None:
    """The skeleton still self-registers so DomainProfile.executor='modal' works."""
    ex = get_executor("modal")
    # We compare by class name + name attr rather than isinstance: the
    # importability test above re-imports the module under monkeypatch,
    # which gives us a *new* ModalExecutor class identity. The registry
    # entry was registered against the original class.
    assert type(ex).__name__ == "ModalExecutor"
    assert ex.name == "modal"


def test_lazy_init_caches_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed ``_lazy_init`` must not retry on every ``run`` call."""
    real_import = builtins.__import__
    call_count = {"n": 0}

    def _fake_import(name, *args, **kwargs):
        if name == "modal":
            call_count["n"] += 1
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    ex = ModalExecutor()
    _drive(ex)
    _drive(ex)
    _drive(ex)
    assert call_count["n"] == 1, "import was retried on every run"


def test_lazy_init_returns_module_when_sdk_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``modal`` is importable, ``_lazy_init`` returns the module + no error."""
    fake_modal = SimpleNamespace(
        config=SimpleNamespace(
            config=lambda: {"token_id": "tok", "token_secret": "sec"}
        ),
    )
    monkeypatch.setitem(sys.modules, "modal", fake_modal)

    ex = ModalExecutor()
    module, err = ex._lazy_init()
    assert err is None
    assert module is fake_modal
    # Repeat call returns cached value rather than re-importing.
    assert ex._lazy_init() == (fake_modal, None)


def test_lazy_init_success_with_creds_passes_credential_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK present + credentials configured: no init or credential error."""
    fake_modal = SimpleNamespace(
        config=SimpleNamespace(
            config=lambda: {"token_id": "tok", "token_secret": "sec"}
        ),
    )
    monkeypatch.setitem(sys.modules, "modal", fake_modal)

    ex = ModalExecutor()
    module, err = ex._lazy_init()
    assert err is None and module is fake_modal
    # And the credential probe sees the populated tokens.
    assert ex._check_credentials(module) is None


def test_lazy_init_succeeds_but_credential_check_fails_when_tokens_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK present + creds missing: ``_lazy_init`` is OK, credential probe fires."""
    fake_modal = SimpleNamespace(
        config=SimpleNamespace(
            config=lambda: {"token_id": None, "token_secret": None}
        ),
    )
    monkeypatch.setitem(sys.modules, "modal", fake_modal)

    ex = ModalExecutor()
    module, err = ex._lazy_init()
    assert err is None and module is fake_modal
    cred_err = ex._check_credentials(module)
    assert cred_err is not None
    assert "modal token new" in cred_err


def test_run_returns_not_implemented_failure_when_remote_path_unimplemented() -> None:
    """Remote execution is still TODO; the skeleton must surface that as a
    structured ``not_implemented`` failure rather than a silent no-op or an
    uncaught ``NotImplementedError``.

    Sibling tests above probe the SDK-import / credential / validation
    branches that fire before we reach the remote call. This pins the
    last branch so a regression to e.g. a returning-None run fails this
    suite. Once ADR 0007 §1 lands the remote path, drop this test.
    """
    fake_modal = SimpleNamespace(
        config=SimpleNamespace(config=lambda: {"token_id": "tok", "token_secret": "sec"}),
    )
    ex = ModalExecutor()
    ex._modal = fake_modal  # bypass the import path
    result = _drive(ex)
    assert isinstance(result, ExecutorResult)
    assert result.artifacts["success"] is False
    assert result.artifacts["stage"] == "not_implemented"
    assert "ModalExecutor remote execution is not yet implemented" in result.artifacts["error"]
