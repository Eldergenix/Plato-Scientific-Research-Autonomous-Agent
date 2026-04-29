"""Capabilities middleware — single source of truth for what a request can do.

Every long-running endpoint consults ``Capabilities`` to decide:
  - Is this stage allowed in the current deployment shape?
  - Has the session blown its dollar budget?
  - Are there too many concurrent runs already?

Lands in Phase 1 (not Phase 4 polish) because both local and demo
deployments depend on it.
"""

from __future__ import annotations
from fastapi import Depends, HTTPException, Request, status

from ..domain.models import Capabilities, StageId
from ..settings import Settings, get_settings


def get_capabilities(request: Request, settings: Settings = Depends(get_settings)) -> Capabilities:
    if settings.is_demo:
        return Capabilities(
            is_demo=True,
            allowed_stages=list(settings.demo_allowed_stages),  # type: ignore[arg-type]
            max_concurrent_runs=settings.demo_max_concurrent_runs,
            session_budget_cents=settings.demo_session_budget_cents,
            session_used_cents=_session_used_cents(request),
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


def _session_used_cents(request: Request) -> int:
    # Wired up by SessionStore in Phase 1.5 — for now zero so the meter
    # renders without blocking demo runs.
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
