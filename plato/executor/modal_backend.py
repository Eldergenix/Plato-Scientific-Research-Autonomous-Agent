"""
``ModalExecutor`` — Modal Labs (modal.com) sandboxed code-execution backend.

Skeleton implementation. The Protocol shape, lazy-import gate, error
contract, and result mapping are wired up; remote execution is gated
behind the ``modal`` SDK actually being installed and a Modal token pair
being configured. Missing SDK or missing credentials yield a structured
failure ``ExecutorResult`` instead of an exception so the surrounding
workflow can persist the failure and surface it cleanly to the user.

Configuration
-------------

1. Install the SDK::

       pip install modal

2. Authenticate once per machine::

       modal token new

   That populates ``~/.modal.toml`` with a ``token_id`` /
   ``token_secret`` pair. The SDK reads it on import; pass
   ``token_id=...`` / ``token_secret=...`` via ``run`` kwargs to override.

3. (Optional) tune execution by passing kwargs to ``run``:

   - ``timeout`` — seconds before the cell is cancelled (default 300).
   - ``image`` — Modal image spec (defaults to a CPU image with
     ``numpy``, ``pandas``, ``matplotlib``).

What this skeleton does **not** do (yet)
----------------------------------------

- Spin up a real Modal Function or Sandbox and stream code into it.
- Mount ``project_dir`` so user data is available to the remote cell.
- Persist a sandbox across multiple calls so kernel state survives.
- Stream chart/table outputs back as ``plot_paths``.

These are tracked in ADR 0007 §1 and are out of scope for the skeleton.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import ExecutorResult, register_executor

__all__ = ["ModalExecutor"]

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 300.0


class ModalSDKUnavailable(RuntimeError):
    """Raised when the ``modal`` package can't be imported."""


class ModalExecutor:
    """Run generated code through Modal's sandbox API.

    Lazy-imports the SDK so missing optional deps don't break
    ``import plato.executor``. The first call to :meth:`run` triggers
    the import; missing SDK or missing credentials surface as a
    structured failure result, not an exception.
    """

    name = "modal"

    def __init__(self, *, default_timeout: float = DEFAULT_TIMEOUT_SEC) -> None:
        self._default_timeout = default_timeout
        self._modal: Any = None
        self._init_error: str | None = None

    def _lazy_init(self) -> tuple[Any, str | None]:
        """Import the ``modal`` SDK on first use.

        Returns ``(modal_module, error_msg)``. ``error_msg`` is non-``None``
        when the SDK is missing; in that case the module reference is
        ``None``. Cached so repeated calls don't re-pay the import cost,
        and so a transient failure is not retried on every ``run``.
        """
        if self._modal is not None or self._init_error is not None:
            return self._modal, self._init_error
        try:
            import modal  # type: ignore[import-not-found]
        except ImportError as exc:
            self._init_error = (
                "Modal SDK not installed: install via `pip install modal` "
                "and authenticate with `modal token new`. "
                f"(import failed: {exc})"
            )
            log.info("Modal SDK unavailable: %s", exc)
            return None, self._init_error
        self._modal = modal
        return modal, None

    @staticmethod
    def _check_credentials(modal_module: Any) -> str | None:
        """Return an error message if no Modal token pair is reachable.

        ``modal.config.config()`` returns a dict-like with ``token_id``
        and ``token_secret`` populated from ``~/.modal.toml`` (or the
        ``MODAL_TOKEN_ID`` / ``MODAL_TOKEN_SECRET`` env vars). If either
        is empty we surface a credential error.
        """
        try:
            cfg = modal_module.config.config()
        except Exception as exc:  # noqa: BLE001 — surface every failure as a result
            return (
                "Failed to read Modal config: "
                f"{type(exc).__name__}: {exc}. "
                "Run `modal token new` to authenticate."
            )
        token_id = cfg.get("token_id") if hasattr(cfg, "get") else None
        token_secret = cfg.get("token_secret") if hasattr(cfg, "get") else None
        if token_id and token_secret:
            return None
        return (
            "Modal credentials not configured: run `modal token new` "
            "to authenticate, or set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET "
            "in the environment."
        )

    async def run(
        self,
        *,
        research_idea: str,
        methodology: str,
        data_description: str,
        project_dir: str | Path,
        keys: Any,
        **kwargs: Any,
    ) -> ExecutorResult:
        """Execute ``methodology`` (Python source) inside a Modal sandbox.

        Returns a structured :class:`ExecutorResult` even on failure so
        callers can persist the run and surface the error to the user
        without a try/except around every executor call.
        """
        modal_module, init_err = self._lazy_init()
        if init_err is not None:
            return _failure_result(
                error=init_err,
                project_dir=project_dir,
                stage="sdk_import",
            )

        cred_err = self._check_credentials(modal_module)
        if cred_err is not None:
            return _failure_result(
                error=cred_err,
                project_dir=project_dir,
                stage="credentials",
            )

        code = methodology or research_idea or ""
        if not code.strip():
            return _failure_result(
                error="No code provided to ModalExecutor (methodology was empty).",
                project_dir=project_dir,
                stage="input_validation",
            )

        # Remote execution is not yet implemented — surface that loudly
        # so a misconfigured DomainProfile.executor='modal' doesn't look
        # like a successful no-op.
        return _failure_result(
            error=(
                "ModalExecutor remote execution is not yet implemented. "
                "Use the e2b or local_jupyter backend until ADR 0007 §1 lands."
            ),
            project_dir=project_dir,
            stage="not_implemented",
        )


def _failure_result(
    *,
    error: str,
    project_dir: str | Path,
    stage: str,
) -> ExecutorResult:
    """Build a uniform failure ``ExecutorResult`` for the modal backend."""
    return ExecutorResult(
        results=f"# ModalExecutor failed at `{stage}`\n\n{error}\n",
        artifacts={
            "backend": "modal",
            "success": False,
            "error": error,
            "stage": stage,
            "project_dir": str(project_dir),
        },
    )


register_executor(ModalExecutor(), overwrite=True)
