"""
Composite source-quality filter.

Combines a :class:`RetractionDB` and a :class:`VenueRanker` into a single
``is_acceptable``/``filter`` interface that R3 callers (and downstream
retrieval pipelines) can apply uniformly.

Rejection precedence — retraction wins. A retracted source is rejected
even if its venue is on the allowlist, because retraction is a hard signal
about the work itself, while venue is a heuristic about provenance.
"""
from __future__ import annotations

import logging
from collections import Counter

from plato.state.models import Source

from .retraction_db import RetractionDB
from .venue_ranker import VenueRanker

logger = logging.getLogger("plato.quality")


class QualityFilter:
    """Apply retraction + venue gating to ``Source`` objects."""

    def __init__(
        self,
        *,
        retraction_db: RetractionDB | None = None,
        venue_ranker: VenueRanker | None = None,
        allow_unranked_venues: bool = True,
    ) -> None:
        self.retraction_db = retraction_db or RetractionDB.empty()
        self.venue_ranker = venue_ranker
        self.allow_unranked_venues = allow_unranked_venues

    def is_acceptable(self, source: Source) -> tuple[bool, str | None]:
        """Decide whether ``source`` passes quality gating.

        Returns ``(True, None)`` if accepted, else ``(False, reason)`` where
        reason is one of ``"retracted"`` or ``"venue_blocked"``.
        """
        # 1) Retraction — hardest signal, checked first.
        if source.retracted:
            return False, "retracted"
        if source.doi and self.retraction_db.is_retracted(source.doi):
            return False, "retracted"

        # 2) Venue allowlist — only enforced when both a ranker is configured
        # and the caller has opted in via ``allow_unranked_venues=False``.
        if self.venue_ranker is not None and not self.allow_unranked_venues:
            if not self.venue_ranker.is_allowed(source.venue):
                return False, "venue_blocked"

        return True, None

    def filter(self, sources: list[Source]) -> list[Source]:
        """Return the subset of ``sources`` that pass quality gating.

        Logs a single info-level summary of per-reason reject counts via
        ``logging.getLogger("plato.quality")``. Callers that want a richer
        audit trail should use :meth:`is_acceptable` directly.
        """
        kept: list[Source] = []
        rejects: Counter[str] = Counter()
        for src in sources:
            ok, reason = self.is_acceptable(src)
            if ok:
                kept.append(src)
            else:
                rejects[reason or "unknown"] += 1

        if rejects:
            logger.info(
                "quality_filter rejected %d/%d source(s): %s",
                sum(rejects.values()),
                len(sources),
                dict(rejects),
            )
        else:
            logger.debug(
                "quality_filter passed all %d source(s)",
                len(sources),
            )
        return kept


__all__ = ["QualityFilter"]
