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
    "_safe_project_dir",
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


def _safe_project_dir(project_dir: "str | os.PathLike[str]") -> "Path":
    """Resolve and verify ``project_dir`` against path-traversal escape.

    Iter-4: every backend (LocalJupyter / Modal / E2B / cmbagent) used
    to write artefacts to ``Path(project_dir)/"plots"/...`` without
    resolving symlinks or checking that the resulting path stays inside
    a sane root. A caller passing ``project_dir="/etc"`` would write
    under ``/etc/plots/<backend>/...`` — easy footgun for anyone who
    plumbs an LLM-suggested path into the executor.

    Returns the resolved ``Path``. Raises ``ValueError`` for paths that
    resolve outside the user's home or the system temp dir, which are
    the two roots the rest of Plato ever writes to.

    Backends call this at the top of their ``run()`` entrypoint and
    use the returned path for every subsequent join.
    """
    import os
    import tempfile
    from pathlib import Path

    resolved = Path(project_dir).expanduser().resolve(strict=False)
    allowed_roots = [
        Path.home().resolve(),
        Path(tempfile.gettempdir()).resolve(),
    ]
    # Also accept a PLATO_PROJECT_ROOT override so deploys (Railway/Spaces)
    # that write under /app or /home/plato can opt in.
    env_root = os.environ.get("PLATO_PROJECT_ROOT", "").strip()
    if env_root:
        allowed_roots.append(Path(env_root).expanduser().resolve())

    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise ValueError(
        f"project_dir {resolved!s} resolves outside allowed roots "
        f"{[str(r) for r in allowed_roots]}; refusing to write."
    )


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


