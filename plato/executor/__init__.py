"""
Phase 5 — sandboxed Executor interface.

A code-execution backend that takes a research idea + methodology + data
description and produces results (markdown) plus any plot/artifact paths.

The default backend is :class:`CmbagentExecutor`, which wraps the existing
``cmbagent.planning_and_control_context_carryover`` flow Plato has used
since day one. Alternative backends (``local_jupyter``, ``modal``, ``e2b``)
are stubbed here so a domain profile can swap executors via
``DomainProfile.executor`` without touching Plato itself.

Concrete executors implement :class:`Executor` and register themselves at
import time with :func:`register_executor`. The four built-in backends are
auto-imported below so simply doing ``from plato import executor`` (or
``import plato.executor``) populates :data:`EXECUTOR_REGISTRY`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

__all__ = [
    "ExecutorResult",
    "Executor",
    "EXECUTOR_REGISTRY",
    "register_executor",
    "get_executor",
    "list_executors",
]


class ExecutorResult(BaseModel):
    """The contract every executor returns from :meth:`Executor.run`."""

    results: str = Field(description="Markdown summary of the run, suitable for paper drafting.")
    plot_paths: list[str] = Field(
        default_factory=list,
        description="Absolute paths to plot/image artifacts produced during execution.",
    )
    artifacts: dict[str, Any] = Field(
        default_factory=dict,
        description="Backend-specific extras (notebooks, logs, intermediate files, ...).",
    )
    cost_usd: float = Field(default=0.0, description="Best-effort cost estimate in USD.")
    tokens_in: int = Field(default=0, description="Total prompt tokens consumed across this run.")
    tokens_out: int = Field(default=0, description="Total completion tokens produced across this run.")


@runtime_checkable
class Executor(Protocol):
    """Protocol every code-execution backend must implement."""

    name: str
    """Stable identifier matching ``DomainProfile.executor`` entries."""

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
        """Execute the experiment and return an :class:`ExecutorResult`."""
        ...


EXECUTOR_REGISTRY: dict[str, Executor] = {}


def register_executor(executor: Executor, *, overwrite: bool = False) -> None:
    """Register an Executor. Raises if name collides unless ``overwrite=True``."""
    if not overwrite and executor.name in EXECUTOR_REGISTRY:
        raise ValueError(
            f"Executor {executor.name!r} is already registered; pass overwrite=True to replace."
        )
    EXECUTOR_REGISTRY[executor.name] = executor


def get_executor(name: str) -> Executor:
    """Look up a registered executor by name (lazy-loads built-ins)."""
    _ensure_builtins_registered()
    if name not in EXECUTOR_REGISTRY:
        raise KeyError(
            f"Unknown executor {name!r}. Registered: {sorted(EXECUTOR_REGISTRY)}"
        )
    return EXECUTOR_REGISTRY[name]


def list_executors() -> list[str]:
    """Return the sorted list of registered executor names."""
    _ensure_builtins_registered()
    return sorted(EXECUTOR_REGISTRY)


# --- Lazy registration of built-in backends --------------------------------
# Each backend module triggers ``register_executor(...)`` on import. We
# defer those imports until first use so ``plato.executor`` can be
# imported without paying the (sometimes heavy) cost of every backend
# (cmbagent in particular pulls a large transitive graph). The first
# call to ``get_executor`` / ``list_executors`` fires the imports.

_BUILTIN_BACKENDS: tuple[str, ...] = (
    "cmbagent",
    "local_jupyter",
    "modal_backend",
    "e2b_backend",
)
_builtins_loaded = False


def _ensure_builtins_registered() -> None:
    """Import every built-in backend module exactly once."""
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    import importlib

    for name in _BUILTIN_BACKENDS:
        try:
            importlib.import_module(f".{name}", __name__)
        except Exception:
            # An unavailable optional backend (e.g. modal SDK not
            # installed) shouldn't block the others. Each backend
            # module handles its own optional-dep behaviour.
            pass


