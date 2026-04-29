"""
DOI and arXiv-id parsing utilities.

Pure stdlib helpers used by the retrieval adapters and citation validators.
No I/O, no third-party deps.
"""
from __future__ import annotations

import re

__all__ = [
    "parse_doi",
    "parse_arxiv_id",
    "normalize_doi",
    "is_valid_doi",
    "is_valid_arxiv_id",
]


# Core DOI regex per CrossRef recommendation:
# https://www.crossref.org/blog/dois-and-matching-regular-expressions/
# A DOI starts with "10." followed by 4-9 digits, then a slash, then any of
# [-._;()/:A-Z0-9] (case-insensitive). We do not anchor end-of-string so we
# can extract a DOI embedded in a larger URL or text blob.
_DOI_CORE = r"10\.\d{4,9}/[-._;()/:A-Z0-9]+"
_DOI_RE = re.compile(_DOI_CORE, re.IGNORECASE)

# Tail characters that are commonly trailing punctuation / sentence terminators
# but not part of the DOI itself.
_DOI_TRAILING_STRIP = ".,;:)]}>\"'"

# arXiv "new" identifier scheme (post-April 2007): YYMM.NNNNN (4-5 digits)
# optionally with version suffix "vN".
_ARXIV_NEW_RE = re.compile(r"\b(\d{4}\.\d{4,5})(v\d+)?\b")

# arXiv "old" identifier scheme (pre-April 2007): archive.subject-class/YYMMNNN
# e.g. cond-mat/0211143, astro-ph.CO/0506000, hep-th/9901001
_ARXIV_OLD_RE = re.compile(
    r"\b([a-z][a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?\b",
    re.IGNORECASE,
)


def normalize_doi(s: str | None) -> str | None:
    """Normalize a DOI: strip whitespace, drop common URL prefixes, lowercase.

    Returns None if input is empty/None or no DOI can be extracted.
    """
    if not s:
        return None
    return parse_doi(s)


def parse_doi(s: str | None) -> str | None:
    """Extract a DOI from an arbitrary string.

    Handles ``https://doi.org/10.x/y``, ``http://dx.doi.org/10.x/y``,
    ``doi:10.x/y``, and bare ``10.x/y``.

    Returns the canonical lowercase form ``10.<registrant>/<suffix>`` or
    ``None`` if no DOI is present.
    """
    if not s:
        return None
    candidate = s.strip()
    if not candidate:
        return None

    match = _DOI_RE.search(candidate)
    if match is None:
        return None

    doi = match.group(0).rstrip(_DOI_TRAILING_STRIP)
    return doi.lower()


def parse_arxiv_id(s: str | None) -> str | None:
    """Extract an arXiv identifier from an arbitrary string.

    Handles ``https://arxiv.org/abs/2401.12345v1``, ``arXiv:2401.12345``,
    bare ``2401.12345``, and the pre-2007 form ``cond-mat/0211143``. The
    version suffix (``v\\d+``) is stripped.

    Returns the canonical id (e.g. ``2401.12345`` or ``cond-mat/0211143``)
    or ``None`` if no arXiv id can be parsed.
    """
    if not s:
        return None
    candidate = s.strip()
    if not candidate:
        return None

    new_match = _ARXIV_NEW_RE.search(candidate)
    if new_match is not None:
        return new_match.group(1)

    old_match = _ARXIV_OLD_RE.search(candidate)
    if old_match is not None:
        identifier = old_match.group(1)
        # Preserve the canonical casing: archive name (before '.' or '/') is
        # lowercase by convention (e.g. "cond-mat", "hep-th"), while the
        # optional subject-class subdivision after a '.' (e.g. ".CO") is
        # uppercase. We lowercase only the archive portion before the dot
        # (or slash, when no dot is present).
        prefix, _, num = identifier.partition("/")
        if "." in prefix:
            archive, _, subject_class = prefix.partition(".")
            normalized_prefix = f"{archive.lower()}.{subject_class}"
        else:
            normalized_prefix = prefix.lower()
        return f"{normalized_prefix}/{num}"

    return None


def is_valid_doi(s: str | None) -> bool:
    """Return True if ``s`` parses to a syntactically valid DOI."""
    return parse_doi(s) is not None


def is_valid_arxiv_id(s: str | None) -> bool:
    """Return True if ``s`` parses to a syntactically valid arXiv id."""
    return parse_arxiv_id(s) is not None
