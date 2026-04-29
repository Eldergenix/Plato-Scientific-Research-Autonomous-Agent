"""Phase 2 — R5: SQLite store contract tests."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from plato.state import Store
from plato.state.models import (
    Claim,
    EvidenceLink,
    Source,
    ValidationResult,
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _make_source(
    *,
    id: str = "src-001",
    doi: str | None = "10.1234/example",
    arxiv_id: str | None = "2401.12345",
    title: str = "Test paper",
    authors: list[str] | None = None,
    retrieved_via: str = "arxiv",
) -> Source:
    return Source(
        id=id,
        doi=doi,
        arxiv_id=arxiv_id,
        title=title,
        authors=authors if authors is not None else ["Alice", "Bob"],
        year=2025,
        retrieved_via=retrieved_via,  # type: ignore[arg-type]
        fetched_at=_now(),
    )


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def test_add_and_get_source_round_trips_fields(tmp_path: Path):
    store = Store(tmp_path / "research.db")
    src = _make_source(authors=["Alice", "Bob", "Carol"], retrieved_via="arxiv")
    store.add_source(src)

    fetched = store.get_source(src.id)
    assert fetched is not None
    assert fetched.id == src.id
    assert fetched.doi == "10.1234/example"
    assert fetched.arxiv_id == "2401.12345"
    assert fetched.authors == ["Alice", "Bob", "Carol"]
    assert fetched.retrieved_via == "arxiv"
    assert fetched.year == 2025
    assert fetched.retracted is False


def test_add_source_idempotent_on_doi(tmp_path: Path):
    """Re-adding a Source with the same DOI must not duplicate rows."""
    store = Store(tmp_path / "research.db")
    src1 = _make_source(id="src-A", doi="10.9999/dup", arxiv_id=None)
    src2 = _make_source(
        id="src-B",  # different internal id, same DOI
        doi="10.9999/dup",
        arxiv_id=None,
        title="Updated title",
    )
    store.add_source(src1)
    store.add_source(src2)

    with sqlite3.connect(str(tmp_path / "research.db")) as conn:
        (count,) = conn.execute("SELECT count(*) FROM sources").fetchone()
    assert count == 1

    # And the row reflects the second add (UPSERT updated fields).
    with sqlite3.connect(str(tmp_path / "research.db")) as conn:
        (title,) = conn.execute(
            "SELECT title FROM sources WHERE doi = ?", ("10.9999/dup",)
        ).fetchone()
    assert title == "Updated title"


def test_add_source_idempotent_on_arxiv_id_when_no_doi(tmp_path: Path):
    """Without a DOI, the arxiv_id is the dedupe key."""
    store = Store(tmp_path / "research.db")
    src1 = _make_source(id="src-A", doi=None, arxiv_id="2401.AAAAA")
    src2 = _make_source(
        id="src-B",
        doi=None,
        arxiv_id="2401.AAAAA",
        title="Different title",
    )
    store.add_source(src1)
    store.add_source(src2)

    with sqlite3.connect(str(tmp_path / "research.db")) as conn:
        (count,) = conn.execute("SELECT count(*) FROM sources").fetchone()
    assert count == 1


def test_list_sources_filters_by_run_id_via_claims(tmp_path: Path):
    store = Store(tmp_path / "research.db")
    src_a = _make_source(id="src-A", doi="10.1/a", arxiv_id=None)
    src_b = _make_source(id="src-B", doi="10.1/b", arxiv_id=None)
    store.add_source(src_a)
    store.add_source(src_b)

    # claim only references src_a in run "r1"
    store.add_claim(
        Claim(id="c-1", text="atoms exist", source_id="src-A"),
        run_id="r1",
    )

    listed = store.list_sources(run_id="r1")
    assert {s.id for s in listed} == {"src-A"}

    listed_all = store.list_sources()
    assert {s.id for s in listed_all} == {"src-A", "src-B"}


# ---------------------------------------------------------------------------
# Claims & evidence links
# ---------------------------------------------------------------------------


def test_add_evidence_link_upsert(tmp_path: Path):
    db = tmp_path / "research.db"
    store = Store(db)
    store.add_source(_make_source(id="src-1", doi="10.1/x", arxiv_id=None))
    store.add_claim(Claim(id="c-1", text="hello"))

    e1 = EvidenceLink(
        claim_id="c-1",
        source_id="src-1",
        support="supports",
        strength="weak",
    )
    store.add_evidence(e1)

    # Same primary key, different fields → UPSERT updates in place.
    e2 = EvidenceLink(
        claim_id="c-1",
        source_id="src-1",
        support="refutes",
        strength="strong",
    )
    store.add_evidence(e2)

    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT support, strength FROM evidence_links "
            "WHERE claim_id = ? AND source_id = ?",
            ("c-1", "src-1"),
        ).fetchall()
    assert rows == [("refutes", "strong")]


# ---------------------------------------------------------------------------
# Validations
# ---------------------------------------------------------------------------


def test_validation_upsert_keeps_single_row(tmp_path: Path):
    db = tmp_path / "research.db"
    store = Store(db)
    store.add_source(_make_source(id="src-V", doi="10.5/v", arxiv_id=None))

    v1 = ValidationResult(
        source_id="src-V",
        doi_resolved=False,
        arxiv_resolved=False,
        url_alive=None,
        retracted=False,
        checked_at=_now(),
    )
    store.add_validation(v1)

    v2 = ValidationResult(
        source_id="src-V",
        doi_resolved=True,
        arxiv_resolved=True,
        url_alive=True,
        retracted=False,
        error=None,
        checked_at=_now(),
    )
    store.add_validation(v2)

    with sqlite3.connect(str(db)) as conn:
        (count,) = conn.execute(
            "SELECT count(*) FROM validations WHERE source_id = ?",
            ("src-V",),
        ).fetchone()
    assert count == 1

    fetched = store.get_validation("src-V")
    assert fetched is not None
    assert fetched.doi_resolved is True
    assert fetched.arxiv_resolved is True
    assert fetched.url_alive is True


# ---------------------------------------------------------------------------
# Persistence + WAL
# ---------------------------------------------------------------------------


def test_two_store_instances_share_data(tmp_path: Path):
    db = tmp_path / "research.db"
    store_a = Store(db)
    store_a.add_source(_make_source(id="src-shared", doi="10.7/shared", arxiv_id=None))

    store_b = Store(db)
    fetched = store_b.get_source("src-shared")
    assert fetched is not None
    assert fetched.doi == "10.7/shared"


def test_wal_mode_is_active(tmp_path: Path):
    db = tmp_path / "research.db"
    Store(db)  # connecting triggers PRAGMA journal_mode=WAL
    with sqlite3.connect(str(db)) as conn:
        (mode,) = conn.execute(
            "SELECT * FROM pragma_journal_mode()"
        ).fetchone()
    assert mode.lower() == "wal"
