"""
``LocalJupyterExecutor`` — execute generated code in a local Jupyter kernel.

This backend runs Python code in a locally launched Jupyter kernel via
``jupyter_client``. The kernel is started lazily on the first execute call
and reused across calls within the same executor instance, so module-level
imports and variables persist across cells (matching notebook semantics).

If ``jupyter_client`` / ``ipykernel`` aren't installed in the environment,
the executor falls back to running each code block in a one-shot Python
``subprocess``. The fallback is best-effort — state does not persist
between cells — but it keeps the executor functional everywhere a Python
interpreter is available, which is the explicit contract the ADR asks for.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import ExecutorResult, register_executor

__all__ = ["LocalJupyterExecutor", "CellResult"]

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 300.0


class CellResult(BaseModel):
    """Result of executing a single code block."""

    stdout: str = ""
    stderr: str = ""
    result: str = Field(default="", description="Repr of the last expression value, if any.")
    error: str = Field(default="", description="Traceback text when execution raised.")
    success: bool = True
    timed_out: bool = False
    duration_sec: float = 0.0
    backend: str = Field(default="jupyter", description="Either 'jupyter' or 'subprocess'.")


class LocalJupyterExecutor:
    """Executor that runs code in a locally launched Jupyter kernel.

    Falls back to a per-call ``python -c`` subprocess if ``jupyter_client``
    isn't importable, so the executor always produces real output.
    """

    name = "local_jupyter"

    def __init__(self, *, default_timeout: float = DEFAULT_TIMEOUT_SEC) -> None:
        self._default_timeout = default_timeout
        self._km: Any = None  # KernelManager
        self._kc: Any = None  # BlockingKernelClient
        self._lock = threading.Lock()
        self._using_jupyter = self._jupyter_available()
        if not self._using_jupyter:
            log.info(
                "jupyter_client not available — LocalJupyterExecutor falling "
                "back to subprocess mode."
            )

    @staticmethod
    def _jupyter_available() -> bool:
        try:
            import jupyter_client  # noqa: F401
            import ipykernel  # noqa: F401
            return True
        except ImportError:
            return False

    def _ensure_kernel(self) -> None:
        """Start the kernel + client on first use. Idempotent."""
        if self._kc is not None:
            return
        from jupyter_client import KernelManager

        km = KernelManager(kernel_name="python3")
        km.start_kernel()
        kc = km.blocking_client()
        kc.start_channels()
        try:
            kc.wait_for_ready(timeout=30)
        except Exception:
            kc.stop_channels()
            km.shutdown_kernel(now=True)
            raise
        self._km = km
        self._kc = kc

    def execute_code(
        self,
        code: str,
        *,
        timeout: float | None = None,
    ) -> CellResult:
        """Execute a single code block and return a :class:`CellResult`.

        Errors raised inside user code are captured (not propagated).
        Hitting the timeout returns ``timed_out=True`` and interrupts the
        kernel so the next call can proceed.
        """
        timeout = self._default_timeout if timeout is None else timeout
        if self._using_jupyter:
            return self._execute_via_kernel(code, timeout=timeout)
        return self._execute_via_subprocess(code, timeout=timeout)

    def _execute_via_kernel(self, code: str, *, timeout: float) -> CellResult:
        with self._lock:
            self._ensure_kernel()
            kc = self._kc
            assert kc is not None
            start = time.monotonic()
            msg_id = kc.execute(code, store_history=False)

            stdout_parts: list[str] = []
            stderr_parts: list[str] = []
            result_parts: list[str] = []
            error_text = ""
            timed_out = False
            success = True
            deadline = start + timeout

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    success = False
                    self._interrupt()
                    break
                try:
                    msg = kc.get_iopub_msg(timeout=min(remaining, 1.0))
                except queue.Empty:
                    continue
                except Exception as exc:
                    error_text = f"iopub channel error: {exc}"
                    success = False
                    break

                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue

                msg_type = msg.get("msg_type", "")
                content = msg.get("content", {})
                if msg_type == "stream":
                    if content.get("name") == "stderr":
                        stderr_parts.append(content.get("text", ""))
                    else:
                        stdout_parts.append(content.get("text", ""))
                elif msg_type in ("execute_result", "display_data"):
                    data = content.get("data", {})
                    text = data.get("text/plain")
                    if text:
                        result_parts.append(text)
                elif msg_type == "error":
                    success = False
                    tb = content.get("traceback") or []
                    error_text = "\n".join(_strip_ansi(line) for line in tb)
                    if not error_text:
                        ename = content.get("ename", "Error")
                        evalue = content.get("evalue", "")
                        error_text = f"{ename}: {evalue}"
                elif msg_type == "status" and content.get("execution_state") == "idle":
                    break

            duration = time.monotonic() - start
            return CellResult(
                stdout="".join(stdout_parts),
                stderr="".join(stderr_parts),
                result="\n".join(result_parts),
                error=error_text,
                success=success and not timed_out,
                timed_out=timed_out,
                duration_sec=duration,
                backend="jupyter",
            )

    def _execute_via_subprocess(self, code: str, *, timeout: float) -> CellResult:
        start = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return CellResult(
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                error=f"TimeoutError: exceeded {timeout}s",
                success=False,
                timed_out=True,
                duration_sec=time.monotonic() - start,
                backend="subprocess",
            )

        duration = time.monotonic() - start
        success = proc.returncode == 0
        return CellResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            error="" if success else (proc.stderr or f"exit code {proc.returncode}"),
            success=success,
            timed_out=False,
            duration_sec=duration,
            backend="subprocess",
        )

    def _interrupt(self) -> None:
        """Interrupt a runaway kernel so the next execute_code() can proceed."""
        if self._km is None:
            return
        try:
            self._km.interrupt_kernel()
        except Exception as exc:  # pragma: no cover — defensive
            log.warning("Failed to interrupt kernel: %s", exc)

    def shutdown(self) -> None:
        """Stop the kernel + client. Safe to call repeatedly."""
        with self._lock:
            kc = self._kc
            km = self._km
            self._kc = None
            self._km = None
        if kc is not None:
            try:
                kc.stop_channels()
            except Exception as exc:  # pragma: no cover
                log.debug("kc.stop_channels failed: %s", exc)
        if km is not None:
            try:
                km.shutdown_kernel(now=True)
            except Exception as exc:  # pragma: no cover
                log.debug("km.shutdown_kernel failed: %s", exc)

    def __del__(self) -> None:  # pragma: no cover — best-effort cleanup
        try:
            self.shutdown()
        except Exception:
            pass

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
        """Protocol entry point.

        ``methodology`` is treated as Python source to execute. Callers that
        want richer plan-and-execute behaviour should compose this executor
        with a planner; this method is the minimal viable mapping from the
        Executor Protocol to a single-cell run.
        """
        timeout = float(kwargs.get("timeout", self._default_timeout))
        code = methodology or research_idea or ""
        if not code.strip():
            return ExecutorResult(
                results="No code provided to LocalJupyterExecutor.",
                artifacts={"backend": "jupyter" if self._using_jupyter else "subprocess"},
            )

        cell = await asyncio.to_thread(self.execute_code, code, timeout=timeout)
        results_md = _render_markdown(cell, data_description=data_description)
        return ExecutorResult(
            results=results_md,
            artifacts={
                "backend": cell.backend,
                "stdout": cell.stdout,
                "stderr": cell.stderr,
                "error": cell.error,
                "success": cell.success,
                "timed_out": cell.timed_out,
                "duration_sec": cell.duration_sec,
                "project_dir": str(project_dir),
            },
        )


def _strip_ansi(text: str) -> str:
    """Strip ANSI colour escapes from a traceback line for clean storage."""
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _render_markdown(cell: CellResult, *, data_description: str) -> str:
    pieces = ["# LocalJupyterExecutor run"]
    if data_description:
        pieces.append(f"\n**Data:** {data_description.strip()}")
    pieces.append(f"\n**Backend:** `{cell.backend}`  ")
    pieces.append(f"**Duration:** {cell.duration_sec:.2f}s  ")
    pieces.append(f"**Success:** {cell.success}")
    if cell.stdout:
        pieces.append("\n## stdout\n```\n" + cell.stdout.rstrip() + "\n```")
    if cell.result:
        pieces.append("\n## result\n```\n" + cell.result.rstrip() + "\n```")
    if cell.stderr:
        pieces.append("\n## stderr\n```\n" + cell.stderr.rstrip() + "\n```")
    if cell.error:
        pieces.append("\n## error\n```\n" + textwrap.indent(cell.error.rstrip(), "  ") + "\n```")
    return "\n".join(pieces)


register_executor(LocalJupyterExecutor(), overwrite=True)
