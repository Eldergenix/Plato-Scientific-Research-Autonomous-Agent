"""
``ModalExecutor`` — stub backend for Modal Labs (modal.com) sandboxes.

The real implementation will spin up a Modal sandbox per run and stream
generated code into it. For now this stub just registers itself so domain
profiles can declare ``executor="modal"`` and we surface a clean error
message until the SDK integration lands.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import ExecutorResult, register_executor

__all__ = ["ModalExecutor"]


class ModalExecutor:
    """Stub Modal sandbox executor — raises :class:`NotImplementedError` on run."""

    name = "modal"

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
            "ModalExecutor stub: install modal SDK and configure"
        )


register_executor(ModalExecutor(), overwrite=True)
