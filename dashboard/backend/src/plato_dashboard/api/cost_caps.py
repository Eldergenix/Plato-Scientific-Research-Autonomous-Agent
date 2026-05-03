"""Iter-26 — per-project cost cap endpoint.

GET / PUT ``/api/v1/projects/{pid}/cost_caps`` reads/writes the project's
:class:`CostCapState` (budget_cents + stop_on_exceed). The cost-meter-panel
in the dashboard used to persist these client-side via ``localStorage``
keys ``plato:budget:`` and ``plato:budget-stop:``, which meant:

1. Cross-device / cross-browser: the cap reset whenever the user
   switched browsers or cleared site data.
2. No server-side enforcement: a client could simply edit localStorage
   to bypass the cap. ``run_stage`` had no way to consult the cap.

Iter-26 moves the state to ``meta.json`` and adds server-side
enforcement in ``server.py:run_stage`` (refuse new launches when the
project's ``total_cost_cents`` is already at-or-above ``budget_cents``
and ``stop_on_exceed=True``).

Tenant scoping: every endpoint goes through ``_get_store`` (per-user
namespace) and the iter-24 ``_enforce_project_tenant`` guard.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..domain.models import CostCapState, Project
from ..settings import Settings, get_settings
from ..storage.project_store import ProjectStore


router = APIRouter()


def _get_store_dep(
    request: Request, settings: Settings = Depends(get_settings)
) -> ProjectStore:
    """Local copy of server.py's ``_get_store`` factory.

    We avoid importing from server.py to dodge a circular import at
    module-load time. The behaviour matches verbatim — same per-user
    namespace resolution, same auth_required 401 short-circuit.
    """
    from .server import _get_store  # noqa: WPS433 — intentional inline import

    return _get_store(request, settings)


def _enforce_dep(
    pid: str, request: Request, store: ProjectStore = Depends(_get_store_dep)
) -> ProjectStore:
    """Tenant guard wrapper. Raises 403/404 if the requester doesn't
    own ``pid``. Returns the store so the route can use it directly.
    """
    from .server import _enforce_project_tenant, _get_user_id

    _enforce_project_tenant(store, pid, _get_user_id(request))
    return store


@router.get(
    "/projects/{pid}/cost_caps",
    response_model=CostCapState,
)
def get_cost_caps(
    pid: str,
    request: Request,
    store: ProjectStore = Depends(_enforce_dep),
) -> CostCapState:
    """Read the current cost cap for ``pid`` (defaults to no-cap shape)."""
    try:
        proj = store.load(pid)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={"code": "project_not_found"}) from exc
    return proj.cost_caps or CostCapState()


@router.put(
    "/projects/{pid}/cost_caps",
    response_model=CostCapState,
)
def put_cost_caps(
    pid: str,
    body: CostCapState,
    request: Request,
    store: ProjectStore = Depends(_enforce_dep),
) -> CostCapState:
    """Persist a new cost cap for ``pid``.

    Pass ``budget_cents=null`` (or omit the field) to clear an existing
    cap. The body is validated by Pydantic so non-ints / negatives are
    rejected at the schema layer.
    """
    try:
        proj = store.load(pid)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={"code": "project_not_found"}) from exc

    proj.cost_caps = body
    store.save(proj)
    return proj.cost_caps


__all__ = ["router"]
