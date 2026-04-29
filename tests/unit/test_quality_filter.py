"""Phase 2 R3 stream B — source-quality filter unit tests."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from plato.quality import QualityFilter, RetractionDB, VenueRanker
from plato.state.models import Source


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _src(
    sid: str,
    *,
    doi: str | None = None,
    venue: str | None = None,
    retracted: bool = False,
) -> Source:
    return Source(
        id=sid,
        doi=doi,
        title=f"Title {sid}",
        venue=venue,
        retracted=retracted,
        retrieved_via="arxiv",
        fetched_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# RetractionDB
# ---------------------------------------------------------------------------


def test_retraction_db_add_contains_len():
    db = RetractionDB(["10.1/foo"])
    assert len(db) == 1
    assert "10.1/foo" in db
    assert db.is_retracted("10.1/foo")

    db.add("10.2/bar")
    assert len(db) == 2
    assert "10.2/bar" in db


def test_retraction_db_doi_normalization_uppercase_and_prefix():
    """Uppercase DOI and ``https://doi.org/`` prefix should still match."""
    db = RetractionDB(["10.1/Foo"])
    assert db.is_retracted("10.1/FOO")
    assert db.is_retracted("https://doi.org/10.1/foo")
    assert db.is_retracted("doi:10.1/Foo")
    assert not db.is_retracted("10.1/other")
    # blank/None-ish input is safe and false
    assert not db.is_retracted("")


def test_retraction_db_empty():
    db = RetractionDB.empty()
    assert len(db) == 0
    assert not db.is_retracted("10.1/anything")


def test_retraction_db_from_csv(tmp_path: Path):
    csv_path = tmp_path / "rw.csv"
    csv_path.write_text(
        "Record ID,OriginalPaperDOI,Title\n"
        "1,10.1/retracted,Bad result\n"
        "2,,Missing DOI row gets skipped\n"
        "3,10.2/Also-Retracted,Another\n",
        encoding="utf-8",
    )
    db = RetractionDB.from_csv(csv_path)
    assert len(db) == 2
    assert db.is_retracted("10.1/retracted")
    # case-insensitive lookup
    assert db.is_retracted("10.2/ALSO-RETRACTED")


# ---------------------------------------------------------------------------
# VenueRanker
# ---------------------------------------------------------------------------


def test_venue_ranker_default_astro_allows_known():
    r = VenueRanker(domain="astro")
    assert r.is_allowed("ApJ")
    assert r.is_allowed("MNRAS")
    assert r.score("ApJ") == 1


def test_venue_ranker_blocks_unknown():
    r = VenueRanker(domain="astro")
    assert not r.is_allowed("Random Blog")
    assert not r.is_allowed(None)
    assert not r.is_allowed("")
    assert r.score("Random Blog") == 0


def test_venue_ranker_case_insensitive():
    r = VenueRanker(domain="astro")
    assert r.is_allowed("apj")
    assert r.is_allowed("APJ")
    assert r.is_allowed("mnras")


def test_venue_ranker_substring_allowlist_inside_venue():
    """Allowlist entry as substring of the venue — e.g. journal full name."""
    r = VenueRanker(domain="astro")
    # "ApJL" is the allowlist entry; full-name venue contains it.
    assert r.is_allowed("The Astrophysical Journal Letters (ApJL)")
    # "Nature Astronomy" allowlist entry is contained in a longer venue string.
    assert r.is_allowed("Nature Astronomy, Vol. 9")


def test_venue_ranker_substring_venue_inside_allowlist():
    """Venue as substring of an allowlist entry — e.g. abbreviation."""
    r = VenueRanker(domain="astro")
    # "AAS" alone is a substring of allowlist entry "AAS Journals".
    assert r.is_allowed("AAS")
    # "ICML" venue should match allowlist on a ranker built for ML.
    ml = VenueRanker(domain="ml")
    assert ml.is_allowed("ICML")


def test_venue_ranker_custom_allowlist():
    r = VenueRanker(allowlist=["My Journal"])
    assert r.is_allowed("My Journal")
    assert not r.is_allowed("Other Journal")


def test_venue_ranker_unknown_domain_raises():
    with pytest.raises(KeyError):
        VenueRanker(domain="not-a-domain")


# ---------------------------------------------------------------------------
# QualityFilter.is_acceptable
# ---------------------------------------------------------------------------


def test_quality_filter_clean_source_accepted():
    f = QualityFilter()
    s = _src("s1", doi="10.1/clean", venue="ApJ")
    assert f.is_acceptable(s) == (True, None)


def test_quality_filter_retracted_flag_rejects():
    f = QualityFilter()
    s = _src("s1", doi="10.1/x", venue="ApJ", retracted=True)
    assert f.is_acceptable(s) == (False, "retracted")


def test_quality_filter_retraction_db_rejects():
    db = RetractionDB(["10.1/bad"])
    f = QualityFilter(retraction_db=db)
    s = _src("s1", doi="10.1/BAD", venue="ApJ")
    assert f.is_acceptable(s) == (False, "retracted")


def test_quality_filter_venue_blocked_when_strict():
    ranker = VenueRanker(domain="astro")
    f = QualityFilter(venue_ranker=ranker, allow_unranked_venues=False)
    s = _src("s1", venue="Random Blog")
    assert f.is_acceptable(s) == (False, "venue_blocked")


def test_quality_filter_venue_allowed_when_lenient():
    """Default ``allow_unranked_venues=True`` must let unknown venues through."""
    ranker = VenueRanker(domain="astro")
    f = QualityFilter(venue_ranker=ranker)  # allow_unranked_venues defaults True
    s = _src("s1", venue="Random Blog")
    assert f.is_acceptable(s) == (True, None)


def test_quality_filter_retraction_takes_precedence_over_venue():
    """A retracted source on an allowed venue is still rejected as retracted."""
    ranker = VenueRanker(domain="astro")
    f = QualityFilter(venue_ranker=ranker, allow_unranked_venues=False)
    s = _src("s1", doi="10.1/x", venue="ApJ", retracted=True)
    assert f.is_acceptable(s) == (False, "retracted")


# ---------------------------------------------------------------------------
# QualityFilter.filter
# ---------------------------------------------------------------------------


def test_quality_filter_filter_returns_subset_and_logs(caplog):
    db = RetractionDB(["10.1/retracted"])
    ranker = VenueRanker(domain="astro")
    f = QualityFilter(
        retraction_db=db,
        venue_ranker=ranker,
        allow_unranked_venues=False,
    )

    sources = [
        _src("s1", doi="10.1/clean", venue="ApJ"),
        _src("s2", doi="10.1/retracted", venue="ApJ"),
        _src("s3", venue="Random Blog"),
        _src("s4", doi="10.2/another", venue="MNRAS"),
        _src("s5", venue="Some Workshop", retracted=True),
    ]

    with caplog.at_level(logging.INFO, logger="plato.quality"):
        kept = f.filter(sources)

    kept_ids = {s.id for s in kept}
    assert kept_ids == {"s1", "s4"}

    # A summary log line should be emitted naming both reject reasons.
    summary_records = [r for r in caplog.records if r.name == "plato.quality"]
    assert summary_records, "expected at least one log record on plato.quality"
    summary = summary_records[-1].getMessage()
    assert "rejected 3/5" in summary
    assert "retracted" in summary
    assert "venue_blocked" in summary


def test_quality_filter_filter_no_rejects_no_info_log(caplog):
    f = QualityFilter()
    sources = [_src("s1", venue="ApJ"), _src("s2", venue="MNRAS")]
    with caplog.at_level(logging.INFO, logger="plato.quality"):
        kept = f.filter(sources)
    assert len(kept) == 2
    info_records = [
        r
        for r in caplog.records
        if r.name == "plato.quality" and r.levelno >= logging.INFO
    ]
    assert info_records == []


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_public_exports():
    from plato.quality import QualityFilter as QF
    from plato.quality import RetractionDB as RD
    from plato.quality import VenueRanker as VR

    assert QF is QualityFilter
    assert RD is RetractionDB
    assert VR is VenueRanker
