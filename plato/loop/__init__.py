"""Phase 4 — R10: autonomous research loop.

The :class:`ResearchLoop` orchestrates an overnight, hands-off run of Plato
where each iteration is scored, accepted-or-rejected against the previous
best, and (optionally) committed onto a tracking git branch so any
iteration can be inspected post-hoc.
"""
from .research_loop import AcceptanceScore, ResearchLoop

__all__ = ["ResearchLoop", "AcceptanceScore"]
