"""Capabilities middleware — single source of truth for what a request can do.

Every long-running endpoint consults ``Capabilities`` to decide:
  - Is this stage allowed in the current deployment shape?
  - Has the session blown its dollar budget?
  - Are there too many concurrent runs already?

Lands in Phase 1 (not Phase 4 polish) because both local and demo
deployments depend on it.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request, status

from ..auth import extract_user_id
from ..domain.models import Capabilities, StageId
from ..settings import Settings, get_settings
from ..storage.project_store import ProjectStore

_log = logging.getLogger(__name__)


def get_capabilities(request: Request, settings: Settings = Depends(get_settings)) -> Capabilities:
    if settings.is_demo:
        return Capabilities(
            is_demo=True,
            allowed_stages=list(settings.demo_allowed_stages),  # type: ignore[arg-type]
            max_concurrent_runs=settings.demo_max_concurrent_runs,
            session_budget_cents=settings.demo_session_budget_cents,
            session_used_cents=_session_used_cents(request, settings),
            notes=[
                "Demo mode: cmbagent and code-execution stages are disabled.",
                f"Hard cap of ${settings.demo_session_budget_cents / 100:.2f} per session.",
                "Projects auto-clean after 30 minutes idle.",
            ],
        )
    return Capabilities(
        is_demo=False,
        allowed_stages=["data", "idea", "literature", "method", "results", "paper", "referee"],
        max_concurrent_runs=settings.local_max_concurrent_runs,
        session_budget_cents=None,
    )


def _session_used_cents(request: Request, settings: Settings) -> int:
    """Sum the dollar spend across the current user's projects.

    Reads ``project.totalCostCents`` from each project's meta.json — the same
    value the frontend already shows on the costs page. We deliberately do not
    sum live ledger entries from token_tracker here: the meta.json totals are
    durable across worker restarts and reconciled at every stage boundary
    (run_manager._reconcile_run), whereas the live ledger is process-local
    and would lie if the user has a multi-worker deployment.

    Returns 0 on any error (missing user_id, missing root, malformed meta) so
    a misconfigured environment doesn't lock every user out of the demo.
    """
    try:
        user_id = extract_user_id(request) or ""
        if not user_id:
            return 0
        # Per-user project root mirrors the layout enforced by
        # ProjectStore.__init__ (settings.project_root / "users" / <uid>).
        user_root = settings.project_root / "users" / user_id
        if not user_root.exists():
            return 0
        # Bind the store to user_id so list_projects + load apply the
        # iter-2 tenant guard. Without this argument the guard is a no-op.
        store = ProjectStore(root=user_root, user_id=user_id)
        return sum(p.total_cost_cents for p in store.list_projects())
    except Exception:  # noqa: BLE001 — never let budget read crash the request
        _log.exception("session_used_cents lookup failed; defaulting to 0")
        return 0


def require_stage_allowed(stage: StageId, caps: Capabilities) -> None:
    if stage not in caps.allowed_stages:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "stage_locked",
                "stage": stage,
                "message": (
                    "This stage is disabled in demo mode. "
                    "Run the dashboard locally to unlock all stages."
                    if caps.is_demo
                    else "This stage is not allowed for the current session."
                ),
                "is_demo": caps.is_demo,
            },
        )


def require_under_budget(caps: Capabilities, projected_cents: int = 0) -> None:
    if caps.session_budget_cents is None:
        return
    remaining = caps.session_budget_cents - caps.session_used_cents
    if remaining - projected_cents < 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "budget_exhausted",
                "session_used_cents": caps.session_used_cents,
                "session_budget_cents": caps.session_budget_cents,
                "message": "Session budget exhausted. Run locally with your own keys for unlimited usage.",
            },
        )
