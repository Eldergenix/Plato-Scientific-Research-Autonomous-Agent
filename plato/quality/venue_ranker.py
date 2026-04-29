"""
Pluggable venue allowlist / scoring.

Source venues come back from retrieval in many forms — e.g. ``ApJL``,
``"The Astrophysical Journal Letters"``, ``"Astrophys. J. Lett."``. The
allowlist matches *bidirectionally and case-insensitively*: a venue passes
if any allowlist entry is a substring of the venue **or** the venue is a
substring of an allowlist entry. This catches both abbreviated and
expanded forms without needing a curated alias map.

``score`` is currently 0/1 but is the seam where ranked tiers (e.g. flagship
vs. workshop) would land later.
"""
from __future__ import annotations

from typing import Iterable


# Domain-keyed defaults shipped with Plato. Callers can pass their own
# allowlist; ``domain`` selects one of these when ``allowlist`` is None.
DEFAULT_ALLOWLISTS: dict[str, set[str]] = {
    "astro": {
        "AAS Journals",
        "ApJ",
        "ApJL",
        "MNRAS",
        "A&A",
        "PRD",
        "PRL",
        "JCAP",
        "Nature Astronomy",
    },
    "biology": {
        "Nature",
        "Cell",
        "Science",
        "PLOS Biology",
        "eLife",
    },
    "ml": {
        "NeurIPS",
        "ICML",
        "ICLR",
        "JMLR",
    },
}


class VenueRanker:
    """Allowlist-based scorer for source venues."""

    def __init__(
        self,
        allowlist: Iterable[str] | None = None,
        *,
        domain: str | None = None,
    ) -> None:
        if allowlist is not None:
            entries = set(allowlist)
        elif domain is not None:
            if domain not in DEFAULT_ALLOWLISTS:
                raise KeyError(
                    f"Unknown venue domain {domain!r}. "
                    f"Known: {sorted(DEFAULT_ALLOWLISTS)}"
                )
            entries = set(DEFAULT_ALLOWLISTS[domain])
        else:
            entries = set()

        self.domain = domain
        self.allowlist: set[str] = entries
        # Pre-lowered list for case-insensitive matching.
        self._lower_allowlist: list[str] = [v.lower() for v in entries if v]

    def is_allowed(self, venue: str | None) -> bool:
        """Bidirectional, case-insensitive substring match.

        - Returns False for ``None`` or empty venue.
        - Returns True if any allowlist entry is a substring of the venue
          (e.g. ``"ApJ"`` matches ``"The Astrophysical Journal (ApJ)"``)
          OR the venue is a substring of an allowlist entry
          (e.g. ``"AAS"`` matches ``"AAS Journals"``).
        """
        if not venue:
            return False
        v = venue.strip().lower()
        if not v:
            return False
        for entry in self._lower_allowlist:
            if entry in v or v in entry:
                return True
        return False

    def score(self, venue: str | None) -> int:
        """Return 1 if allowed, else 0. Extension point for tiered ranks."""
        return 1 if self.is_allowed(venue) else 0


__all__ = ["VenueRanker", "DEFAULT_ALLOWLISTS"]
