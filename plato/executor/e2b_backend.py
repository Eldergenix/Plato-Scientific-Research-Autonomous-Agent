"""
``E2BExecutor`` — E2B (e2b.dev) sandboxed code-execution backend.

Skeleton implementation. The Protocol shape, lazy-import gate, error
contract, and result mapping are wired up; remote execution is gated
behind the ``e2b_code_interpreter`` SDK actually being installed and an
``E2B_API_KEY`` being present. Missing SDK or missing credentials yield
a structured failure ``ExecutorResult`` instead of an exception, so the
surrounding workflow can persist the failure and surface it cleanly to
the user. ADR 0007 §2 tracks the remaining production-hardening work.

Configuration
-------------

1. Install the SDK::

       pip install e2b-code-interpreter

   (The PyPI distribution name is ``e2b-code-interpreter`` but the
   import path is ``e2b_code_interpreter``.)

2. Set the API key in the environment::

       export E2B_API_KEY=e2b_xxx...

   Get a key from https://e2b.dev/dashboard. The SDK reads the variable
   on import; pass ``api_key=...`` via ``run`` kwargs to override.

3. (Optional) tune execution by passing kwargs to ``run``:

   - ``timeout`` — seconds before the cell is cancelled (default 300).
   - ``api_key`` — override the env var per-call.
   - ``template`` — E2B sandbox template ID; defaults to the standard
     code-interpreter template that ships with ``numpy``, ``pandas``,
     ``matplotlib``, and a Jupyter kernel.

What this skeleton does **not** do (yet)
----------------------------------------

- Upload ``project_dir`` to the sandbox filesystem so user data is
  available — E2B exposes a ``files.write`` API but the policy for what
  to upload (everything? only data files?) is undecided.
- Persist the sandbox across multiple calls so kernel state survives
  between methodology cells.
- Stream Jupyter results (charts, tables) back as ``plot_paths``.
- Map ``cancel_event`` onto sandbox lifecycle.

These are tracked in ADR 0007 §2 and are out of scope for the skeleton.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from . import ExecutorResult, register_executor

__all__ = ["E2BExecutor"]

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 300.0


class E2BSDKUnavailable(RuntimeError):
    """Raised when the ``e2b_code_interpreter`` package can't be imported."""


class E2BExecutor:
    """Run generated code inside an E2B Code Interpreter sandbox.

    Lazy-imports the SDK so missing optional deps don't break
    ``import plato.executor``. The first call to :meth:`run` triggers the
    import; missing SDK or missing credentials surface as a structured
    failure result, not an exception.
    """

    name = "e2b"

    def __init__(self, *, default_timeout: float = DEFAULT_TIMEOUT_SEC) -> None:
        self._default_timeout = default_timeout
        self._sandbox_cls: Any = None
        self._init_error: str | None = None

    def _lazy_init(self) -> tuple[Any, str | None]:
        """Import ``e2b_code_interpreter.Sandbox`` on first use.

        Returns ``(Sandbox, error_msg)``. ``error_msg`` is non-``None``
        when the SDK is missing; in that case the class reference is
        ``None``. Cached so repeated calls don't re-pay the import cost.
        """
        if self._sandbox_cls is not None or self._init_error is not None:
            return self._sandbox_cls, self._init_error
        try:
            from e2b_code_interpreter import Sandbox  # type: ignore[import-not-found]
        except ImportError as exc:
            self._init_error = (
                "E2B SDK not installed: install via "
                "`pip install e2b-code-interpreter` and configure with "
                "`export E2B_API_KEY=...`. "
                f"(import failed: {exc})"
            )
            log.info("E2B SDK unavailable: %s", exc)
            return None, self._init_error
        self._sandbox_cls = Sandbox
        return Sandbox, None

    @staticmethod
    def _check_credentials(api_key_override: str | None) -> str | None:
        """Return an error message if no API key is reachable, else ``None``."""
        if api_key_override:
            return None
        if os.environ.get("E2B_API_KEY"):
            return None
        return (
            "E2B credentials not configured: set E2B_API_KEY in the "
            "environment or pass api_key=... to run(). Get a key at "
            "https://e2b.dev/dashboard."
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
        """Execute ``methodology`` (Python source) inside an E2B sandbox.

        Returns a structured :class:`ExecutorResult` even on failure so
        callers can persist the run and surface the error to the user
        without a try/except around every executor call.
        """
        Sandbox, init_err = self._lazy_init()
        if init_err is not None:
            return _failure_result(
                error=init_err,
                project_dir=project_dir,
                stage="sdk_import",
            )

        api_key_override = kwargs.get("api_key")
        cred_err = self._check_credentials(api_key_override)
        if cred_err is not None:
            return _failure_result(
                error=cred_err,
                project_dir=project_dir,
                stage="credentials",
            )

        code = methodology or research_idea or ""
        if not code.strip():
            return _failure_result(
                error="No code provided to E2BExecutor (methodology was empty).",
                project_dir=project_dir,
                stage="input_validation",
            )

        timeout = float(kwargs.get("timeout", self._default_timeout))
        template = kwargs.get("template")

        try:
            return await asyncio.to_thread(
                self._run_sync,
                Sandbox=Sandbox,
                code=code,
                timeout=timeout,
                api_key=api_key_override,
                template=template,
                project_dir=project_dir,
                data_description=data_description,
            )
        except Exception as exc:  # noqa: BLE001 — surface every failure as a result
            log.exception("E2BExecutor remote call failed")
            return _failure_result(
                error=f"E2B remote execution failed: {type(exc).__name__}: {exc}",
                project_dir=project_dir,
                stage="remote_execution",
            )

    @staticmethod
    def _run_sync(
        *,
        Sandbox: Any,
        code: str,
        timeout: float,
        api_key: str | None,
        template: str | None,
        project_dir: str | Path,
        data_description: str,
    ) -> ExecutorResult:
        """Provision a sandbox and run ``code`` via ``run_code``.

        E2B's ``Sandbox`` is a context manager that tears the remote VM
        down on exit, which is what we want for a one-shot run.
        """
        sandbox_kwargs: dict[str, Any] = {}
        if api_key:
            sandbox_kwargs["api_key"] = api_key
        if template:
            sandbox_kwargs["template"] = template

        with Sandbox(**sandbox_kwargs) as sandbox:
            execution = sandbox.run_code(code, timeout=int(timeout))

        stdout = "".join(getattr(execution, "logs", _Empty()).stdout or []) \
            if hasattr(execution, "logs") else ""
        stderr = "".join(getattr(execution, "logs", _Empty()).stderr or []) \
            if hasattr(execution, "logs") else ""
        error_obj = getattr(execution, "error", None)
        error_text = ""
        if error_obj is not None:
            name = getattr(error_obj, "name", "Error")
            value = getattr(error_obj, "value", "")
            tb = getattr(error_obj, "traceback", "") or ""
            error_text = f"{name}: {value}\n{tb}".strip()
        success = error_obj is None

        results_md = _render_markdown(
            stdout=stdout,
            stderr=stderr,
            error=error_text,
            success=success,
            data_description=data_description,
        )
        return ExecutorResult(
            results=results_md,
            artifacts={
                "backend": "e2b",
                "stdout": stdout,
                "stderr": stderr,
                "error": error_text,
                "success": success,
                "project_dir": str(project_dir),
            },
        )


class _Empty:
    """Sentinel for ``getattr(..., default)`` on missing ``logs`` attr."""

    stdout: list[str] = []
    stderr: list[str] = []


def _failure_result(
    *,
    error: str,
    project_dir: str | Path,
    stage: str,
) -> ExecutorResult:
    """Build a uniform failure ``ExecutorResult`` for the e2b backend."""
    return ExecutorResult(
        results=f"# E2BExecutor failed at `{stage}`\n\n{error}\n",
        artifacts={
            "backend": "e2b",
            "success": False,
            "error": error,
            "stage": stage,
            "project_dir": str(project_dir),
        },
    )


def _render_markdown(
    *,
    stdout: str,
    stderr: str,
    error: str,
    success: bool,
    data_description: str,
) -> str:
    pieces = ["# E2BExecutor run"]
    if data_description:
        pieces.append(f"\n**Data:** {data_description.strip()}")
    pieces.append(f"\n**Success:** {success}")
    if stdout:
        pieces.append("\n## stdout\n```\n" + stdout.rstrip() + "\n```")
    if stderr:
        pieces.append("\n## stderr\n```\n" + stderr.rstrip() + "\n```")
    if error:
        pieces.append("\n## error\n```\n" + error.rstrip() + "\n```")
    return "\n".join(pieces)


register_executor(E2BExecutor(), overwrite=True)
