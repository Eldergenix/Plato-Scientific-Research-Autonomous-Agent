"""Executor backend discovery endpoint.

Plato ships four executor backends in :mod:`plato.executor`: ``cmbagent``
(the default real one), ``local_jupyter`` (kernel-based, lazy import),
``modal`` (stub), and ``e2b`` (stub). The dashboard's settings page wants
to render them as a single picker so a user can flip the default for new
runs without editing YAML.

This router exposes a tiny read-only catalogue. Per-executor *preferences*
(which one to default to) live next door in
:mod:`plato_dashboard.api.executor_preferences` so the persistence
concern stays separate from discovery — and so we don't fight Stream 6's
``user_preferences`` namespace at integration time.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

ExecutorKind = Literal["real", "stub", "lazy"]


class ExecutorInfo(BaseModel):
    name: str
    available: bool
    kind: ExecutorKind
    description: str


class ExecutorList(BaseModel):
    executors: list[ExecutorInfo]
    default: str


# Hand-tuned per-backend descriptions. Source of truth for the catalogue
# UI — short enough to fit in a card subtitle without truncation.
_DESCRIPTIONS: dict[str, str] = {
    "cmbagent": (
        "Default backend. Wraps cmbagent's planning + control loop "
        "(engineer / researcher / planner) on top of OpenAI + Anthropic."
    ),
    "local_jupyter": (
        "Run generated code in a local Jupyter kernel. Requires "
        "jupyter-client; the execution loop itself is still scaffolding."
    ),
    "modal": (
        "Modal Labs sandbox executor. Stub — install the modal SDK and "
        "configure credentials before this can run."
    ),
    "e2b": (
        "E2B sandbox executor. Stub — install the e2b SDK and configure "
        "credentials before this can run."
    ),
}


def _classify_kind(name: str) -> ExecutorKind:
    """Map an executor name to one of {real, lazy, stub}.

    ``cmbagent`` is "real" when its host package imports cleanly; otherwise
    we downgrade it to "lazy" so the UI surfaces the install-required
    state. ``local_jupyter`` is always "lazy" — it depends on
    ``jupyter_client`` which we don't pull in by default. ``modal`` and
    ``e2b`` are pure scaffolds.
    """
    if name == "cmbagent":
        try:
            import cmbagent  # noqa: F401
        except ImportError:
            return "lazy"
        return "real"
    if name == "local_jupyter":
        return "lazy"
    return "stub"


def _is_available(name: str, kind: ExecutorKind) -> bool:
    """Best-effort check that ``get_executor(name).run`` won't immediately
    fall over with NotImplementedError.

    We don't actually invoke ``run`` — instantiating the executor is
    enough. For ``cmbagent`` we additionally require the upstream package
    to import; for ``local_jupyter`` we require ``jupyter_client``.
    """
    from plato.executor import get_executor

    try:
        get_executor(name)
    except KeyError:
        return False

    if kind == "stub":
        return False
    if name == "cmbagent":
        try:
            import cmbagent  # noqa: F401
        except ImportError:
            return False
        return True
    if name == "local_jupyter":
        try:
            import jupyter_client  # noqa: F401
        except ImportError:
            return False
        # The current scaffold raises NotImplementedError on run() even
        # with jupyter installed, so the kernel-execution loop isn't
        # plumbed yet. Surface that honestly.
        return False
    return True


@router.get("/executors", response_model=ExecutorList)
def list_executors_endpoint() -> ExecutorList:
    """Return the full executor catalogue with per-backend status."""
    from plato.executor import list_executors

    items: list[ExecutorInfo] = []
    for name in list_executors():
        kind = _classify_kind(name)
        items.append(
            ExecutorInfo(
                name=name,
                available=_is_available(name, kind),
                kind=kind,
                description=_DESCRIPTIONS.get(name, ""),
            )
        )
    return ExecutorList(executors=items, default="cmbagent")


__all__ = ["router", "ExecutorInfo", "ExecutorList"]
