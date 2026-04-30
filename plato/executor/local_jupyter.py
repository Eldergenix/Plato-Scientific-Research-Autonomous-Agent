"""
``LocalJupyterExecutor`` — execute generated code in a local Jupyter kernel.

This backend is a thin scaffold: it lazy-imports ``jupyter_client`` only on
``run()`` so the module remains import-safe even when jupyter isn't
installed. Wiring the actual code-generation -> kernel-execution loop is
out of scope for this stream and lands in a follow-up workflow.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import ExecutorResult, register_executor

__all__ = ["LocalJupyterExecutor"]


class LocalJupyterExecutor:
    """Executor that runs code cells in a locally launched Jupyter kernel."""

    name = "local_jupyter"

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
        try:
            import jupyter_client  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "LocalJupyterExecutor requires jupyter-client. "
                "Install it with: pip install jupyter-client"
            ) from exc

        # Real implementation lands in a follow-up workflow once the
        # Executor Protocol is in production use.
        raise NotImplementedError(
            "LocalJupyterExecutor scaffold: kernel-based execution loop "
            "is not implemented yet."
        )


register_executor(LocalJupyterExecutor(), overwrite=True)
