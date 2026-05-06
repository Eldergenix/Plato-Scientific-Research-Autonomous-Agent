"""Scientific capability discovery for dashboard settings."""
from __future__ import annotations

from fastapi import APIRouter

from plato.tools.scientific_capabilities import (
    ScientificCapabilityReport,
    build_scientific_capability_report,
)

router = APIRouter()


@router.get("/scientific-capabilities", response_model=ScientificCapabilityReport)
def get_scientific_capabilities() -> ScientificCapabilityReport:
    """Return reviewed scientific integrations and deterministic checks."""
    return build_scientific_capability_report()


__all__ = ["router"]
