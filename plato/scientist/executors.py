"""Choose where an experiment script runs.

``local`` is the container's own sandbox (network namespace, unprivileged user,
rlimits). ``modal`` runs the same script in a Modal Labs sandbox, optionally with a GPU,
when Modal credentials are configured; otherwise the run stays local and says why.
``e2b`` never reaches this function: the pipeline sends it to the E2B workspace
(``nodes._run_recipe``), which rebuilds each recorded recipe in a fresh sandbox.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .guard import SandboxResult, run_python
from .guard.modal_runner import modal_configured, run_python_modal

if TYPE_CHECKING:
    from .nodes import ScientistConfig

logger = logging.getLogger(__name__)
EXECUTORS = ("local", "modal", "e2b")


async def run_experiment(
    config: ScientistConfig, code: str, *, inputs: dict[str, bytes]
) -> SandboxResult:
    if config.executor == "modal":
        if modal_configured():
            return await run_python_modal(
                code, inputs=inputs, limits=config.sandbox, gpu=config.gpu
            )
        logger.warning(
            "executor 'modal' selected but Modal is not configured; running locally"
        )
    elif config.executor not in ("local", ""):
        logger.warning(
            "executor %r is not available here; running locally", config.executor
        )
    return await run_python(
        code,
        inputs=inputs,
        limits=config.sandbox,
        require_network_isolation=config.require_network_isolation,
    )
