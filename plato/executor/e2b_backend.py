"""
``E2BExecutor`` — stub backend for E2B (e2b.dev) sandboxes.

Like :mod:`plato.executor.modal_backend`, this stub exists so domain
profiles can declare ``executor="e2b"`` today; the real SDK integration
lands in a follow-up workflow.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import ExecutorResult, register_executor

__all__ = ["E2BExecutor"]


class E2BExecutor:
    """Stub E2B sandbox executor — raises :class:`NotImplementedError` on run."""

    name = "e2b"

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
        raise NotImplementedError(
            "E2BExecutor stub: install e2b SDK and configure"
        )


register_executor(E2BExecutor(), overwrite=True)
