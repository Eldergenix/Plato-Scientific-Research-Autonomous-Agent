"""
In-memory retraction database.

The canonical input is the Retraction Watch CSV export, whose default DOI
column is ``OriginalPaperDOI``. We normalize DOIs to lowercase and strip
whitespace + a leading ``doi:`` / ``https://doi.org/`` prefix so callers can
pass DOIs from any source format and still hit the set.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable


def _normalize_doi(doi: str) -> str:
    """Lowercase, strip, and drop common DOI URL/prefix forms."""
    s = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s


class RetractionDB:
    """A set of retracted DOIs with case- and prefix-insensitive lookup."""

    def __init__(self, dois: Iterable[str] = (), source: str = "manual") -> None:
        self.source = source
        self._dois: set[str] = set()
        for d in dois:
            if d:
                self._dois.add(_normalize_doi(d))

    def add(self, doi: str) -> None:
        """Add a single DOI (normalized) to the set."""
        if not doi:
            return
        self._dois.add(_normalize_doi(doi))

    def is_retracted(self, doi: str) -> bool:
        """Return True if ``doi`` (case-insensitive) is in the retraction set."""
        if not doi:
            return False
        return _normalize_doi(doi) in self._dois

    def __contains__(self, doi: str) -> bool:
        return self.is_retracted(doi)

    def __iter__(self):
        return iter(self._dois)

    def __len__(self) -> int:
        return len(self._dois)

    @classmethod
    def empty(cls) -> "RetractionDB":
        """An empty database — useful for tests and as a default."""
        return cls((), source="empty")

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        doi_column: str = "OriginalPaperDOI",
    ) -> "RetractionDB":
        """Load DOIs from a CSV (Retraction Watch format by default).

        Rows where the DOI column is missing or blank are skipped silently —
        the public Retraction Watch dump contains many such rows.
        """
        p = Path(path)
        dois: list[str] = []
        with p.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                value = (row.get(doi_column) or "").strip()
                if value:
                    dois.append(value)
        return cls(dois, source=f"csv:{p.name}")


__all__ = ["RetractionDB"]
