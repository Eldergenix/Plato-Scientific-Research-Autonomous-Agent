"""Iter-27 — per-project approval-checkpoints endpoint.

GET / PUT ``/api/v1/projects/{pid}/approvals`` reads/writes the
project's :class:`ApprovalsState` (per-stage approval map +
``auto_skip`` global bypass). Mirrors iter-26's cost-cap pattern:
backend persistence on ``meta.json`` + iter-24 tenant guard +
``run_stage`` consults it before launching.

The frontend's approval-checkpoints.tsx used to persist these in
``localStorage`` keyed by ``plato:approvals:{pid}:{stage}`` /
``plato:approvals:auto-skip``. That meant:

1. Cross-device / cross-browser: approvals reset whenever the user
   switched browsers or cleared site data.
2. No server-side enforcement: a malicious or stale client could
   launch a downstream stage by editing localStorage. ``run_stage``
   had no way to consult the gate.

Iter-27 closes both gaps. The blocker chain (idea → literature →
method, each blocking everything downstream) lives in
``compute_blocking_approval`` so frontend and backend share one
canonical implementation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..domain.models import ApprovalsState, Project
from ..settings import Settings, get_settings
from ..storage.project_store import ProjectStore


router = APIRouter()


# Iter-27: blocker-chain definition. Source of truth for both the
# /approvals endpoint's gate evaluation and the run_stage gate.
# Mirror of approval-checkpoints.tsx::guardOrder.
_BLOCKER_CHAIN: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("idea", ("literature", "method", "results", "paper", "referee")),
    ("literature", ("method", "results", "paper", "referee")),
    ("method", ("results", "paper", "referee")),
)


def compute_blocking_approval(project: Project, target_stage: str) -> str | None:
    """Return the upstream gate stage that's blocking ``target_stage``.

    Returns ``None`` when:
    - ``project.approvals.auto_skip`` is True (escape hatch), OR
    - no upstream gate is in a blocking state for this target

    Mirrors the frontend's ``getBlockingApproval`` so a user who sees
    "blocked by idea" in the UI gets the same answer when the server
    refuses the launch.
    """
    approvals = project.approvals
    if approvals is None:
        # No checkpoints recorded yet — only block when an upstream
        # stage is "done" but unapproved. Falls through to the loop
        # below with an empty per_stage map (every state defaults to
        # "pending" → blocked).
        approvals = ApprovalsState()

    if approvals.auto_skip:
        return None

    for gate_id, blocked_stages in _BLOCKER_CHAIN:
        if target_stage not in blocked_stages:
            continue
        gate_stage = project.stages.get(gate_id)
        # Gate hasn't run yet → not THIS gate's problem to block.
        if gate_stage is None or gate_stage.status != "done":
            continue
        state = approvals.per_stage.get(gate_id, "pending")
        if state in ("approved", "skipped"):
            continue
        return gate_id
    return None


def _get_store_dep(
    request: Request, settings: Settings = Depends(get_settings)
) -> ProjectStore:
    """Local copy of server.py's ``_get_store`` factory (avoids circular import)."""
    from .server import _get_store  # noqa: WPS433

    return _get_store(request, settings)


def _enforce_dep(
    pid: str, request: Request, store: ProjectStore = Depends(_get_store_dep)
) -> ProjectStore:
    """Tenant guard wrapper — same shape as cost_caps.py."""
    from .server import _enforce_project_tenant, _get_user_id

    _enforce_project_tenant(store, pid, _get_user_id(request))
    return store


@router.get(
    "/projects/{pid}/approvals",
    response_model=ApprovalsState,
)
def get_approvals(
    pid: str,
    request: Request,
    store: ProjectStore = Depends(_enforce_dep),
) -> ApprovalsState:
    """Read the current approvals state (defaults to empty per_stage + no auto_skip)."""
    try:
        proj = store.load(pid)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={"code": "project_not_found"}) from exc
    return proj.approvals or ApprovalsState()


@router.put(
    "/projects/{pid}/approvals",
    response_model=ApprovalsState,
)
def put_approvals(
    pid: str,
    body: ApprovalsState,
    request: Request,
    store: ProjectStore = Depends(_enforce_dep),
) -> ApprovalsState:
    """Persist the new approvals state for ``pid``.

    Replaces the entire approvals payload — clients that want a partial
    update should fetch first, mutate, then PUT. Pydantic validates the
    per_stage values at the schema layer (only the four ApprovalState
    literals are accepted).
    """
    try:
        proj = store.load(pid)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={"code": "project_not_found"}) from exc

    proj.approvals = body
    store.save(proj)
    return proj.approvals


__all__ = ["router", "compute_blocking_approval"]
