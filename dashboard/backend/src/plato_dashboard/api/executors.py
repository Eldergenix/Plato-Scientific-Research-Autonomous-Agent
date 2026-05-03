"""Executor backend discovery endpoint.

Plato ships four executor backends in :mod:`plato.executor`:

- ``cmbagent`` — the historical default, wraps cmbagent's planning loop.
- ``local_jupyter`` — kernel-based execution via ``jupyter_client``.
- ``modal`` — Modal Labs sandbox per run (iter-20 real impl).
- ``e2b`` — E2B Code Interpreter sandbox per run (iter-20 real impl).

The dashboard's settings page wants to render them as a single picker so a
user can flip the default for new runs without editing YAML.

This router exposes a tiny read-only catalogue. Per-executor *preferences*
(which one to default to) live next door in
:mod:`plato_dashboard.api.executor_preferences` so the persistence concern
stays separate from discovery.

Iter-21 update: every backend now has a real implementation. The
classification logic was previously hard-coded to call ``local_jupyter`` /
``modal`` / ``e2b`` "scaffolds" and report them as ``available=False``
even after their respective real impls landed. We now probe the host
SDK at request time and surface ``"real"`` / ``"lazy"`` honestly so users
can actually pick the backend they want from the UI.
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
        "Historical default. Wraps cmbagent's planning + control loop "
        "(engineer / researcher / planner) on top of OpenAI + Anthropic."
    ),
    "local_jupyter": (
        "Run generated code in a local Jupyter kernel. "
        "Requires the jupyter-client package (pip install jupyter-client)."
    ),
    "modal": (
        "Modal Labs sandbox executor. Spins up a per-run sandbox with "
        "matplotlib pre-installed. Requires the modal SDK + a configured "
        "Modal token (pip install modal && modal token new)."
    ),
    "e2b": (
        "E2B Code Interpreter sandbox executor. Each run runs in its own "
        "Jupyter-flavoured sandbox. Requires the e2b-code-interpreter SDK "
        "and the E2B_API_KEY env var."
    ),
}


# Each backend gets a tuple of (sdk_module_name, kind_when_present).
# When the import succeeds, the executor is "real" and "available";
# when it fails, the executor is "lazy" (real impl shipped, just install
# the optional dep). This replaces the iter-17 hard-coded matrix.
_SDK_PROBES: dict[str, tuple[str, ...]] = {
    "cmbagent": ("cmbagent",),
    "local_jupyter": ("jupyter_client",),
    "modal": ("modal",),
    "e2b": ("e2b_code_interpreter",),
}


def _sdk_present(name: str) -> bool:
    """Probe each backend's optional SDK without actually importing it long-term.

    We use ``importlib.util.find_spec`` rather than a real ``import`` so
    repeated catalogue requests don't keep heavy SDK modules resident in
    sys.modules just because the dashboard rendered the settings page.
    Returns ``True`` if every required SDK module is locatable.
    """
    import importlib.util

    probes = _SDK_PROBES.get(name)
    if not probes:
        return True  # Unknown backend — let the registry decide.
    for module in probes:
        try:
            if importlib.util.find_spec(module) is None:
                return False
        except (ValueError, ImportError, ModuleNotFoundError):
            return False
    return True


def _classify_kind(name: str) -> ExecutorKind:
    """Map an executor name to one of {real, lazy, stub}.

    Iter-21 contract: all shipped backends are now real. ``"lazy"`` means
    the implementation is real but the optional SDK isn't installed in
    the current environment. ``"stub"`` is kept in the enum for
    forward-compat (e.g. a future backend that ships before its impl
    lands) but no current backend returns it.
    """
    if name not in _SDK_PROBES:
        return "stub"
    return "real" if _sdk_present(name) else "lazy"


def _is_available(name: str, kind: ExecutorKind) -> bool:
    """Best-effort: ``True`` when ``get_executor(name).run`` won't immediately
    fall over with ImportError or NotImplementedError.

    The executor must be registered AND its required SDK importable. We
    don't actually invoke ``run`` — that would spin up the sandbox /
    kernel, which is wasteful for a catalogue lookup.
    """
    from plato.executor import get_executor

    try:
        get_executor(name)
    except KeyError:
        return False

    if kind == "stub":
        return False
    return _sdk_present(name)


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
