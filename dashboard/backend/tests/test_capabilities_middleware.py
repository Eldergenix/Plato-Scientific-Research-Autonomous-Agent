"""Direct unit tests for ``require_stage_allowed`` and ``require_under_budget``."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from plato_dashboard.api.capabilities import (
    require_stage_allowed,
    require_under_budget,
)
from plato_dashboard.domain.models import Capabilities


def _local_caps(**overrides) -> Capabilities:
    base = dict(
        is_demo=False,
        allowed_stages=["data", "idea", "literature", "method", "results", "paper", "referee"],
        max_concurrent_runs=2,
        session_budget_cents=None,
    )
    base.update(overrides)
    return Capabilities(**base)


def _demo_caps(**overrides) -> Capabilities:
    base = dict(
        is_demo=True,
        allowed_stages=["data", "idea", "method", "literature"],
        max_concurrent_runs=1,
        session_budget_cents=50,
        session_used_cents=0,
    )
    base.update(overrides)
    return Capabilities(**base)


def test_require_stage_allowed_passes_for_local_caps() -> None:
    require_stage_allowed("results", _local_caps())  # no exception


def test_require_stage_allowed_rejects_results_in_demo() -> None:
    with pytest.raises(HTTPException) as exc:
        require_stage_allowed("results", _demo_caps())
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "stage_locked"
    assert exc.value.detail["is_demo"] is True


def test_require_stage_allowed_rejects_paper_in_demo() -> None:
    with pytest.raises(HTTPException) as exc:
        require_stage_allowed("paper", _demo_caps())
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "stage_locked"


def test_require_under_budget_noop_when_no_cap() -> None:
    require_under_budget(_local_caps())  # no exception


def test_require_under_budget_passes_with_remaining() -> None:
    require_under_budget(_demo_caps(session_used_cents=10), projected_cents=20)


def test_require_under_budget_blocks_when_exhausted() -> None:
    caps = _demo_caps(session_used_cents=50)
    with pytest.raises(HTTPException) as exc:
        require_under_budget(caps, projected_cents=1)
    assert exc.value.status_code == 402
    assert exc.value.detail["code"] == "budget_exhausted"
