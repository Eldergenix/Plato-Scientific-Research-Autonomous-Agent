"""
Phase 2 R3 stream B — source-quality filtering.

Companion to citation validation. Plato historically had no retraction or
venue gating — sources flowed straight from retrieval into reasoning. This
package fills that gap with two pluggable building blocks and a combiner:

- :class:`RetractionDB` — set of retracted DOIs (e.g. Retraction Watch).
- :class:`VenueRanker` — domain-tuned allowlist of trusted venues.
- :class:`QualityFilter` — applies both to a list of ``Source`` objects.

The filter logs (via ``logging.getLogger("plato.quality")``) the per-reason
reject counts so downstream stages get an audit trail without changing the
returned data shape.
"""
from __future__ import annotations

from .filter import QualityFilter
from .retraction_db import RetractionDB
from .venue_ranker import VenueRanker

__all__ = ["QualityFilter", "RetractionDB", "VenueRanker"]
