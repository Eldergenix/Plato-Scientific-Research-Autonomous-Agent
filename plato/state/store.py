"""
Phase 2 — R5: SQLite store for sources, claims, evidence links, and validations.

The :class:`Store` persists the four Pydantic models defined in
:mod:`plato.state.models` (``Source``, ``Claim``, ``EvidenceLink``,
``ValidationResult``) plus per-run metadata and produced-artifact rows.
The schema is small but covers the join queries Phase 2 needs:

* Look up a source by DOI / arXiv id (de-duplicated).
* List claims drafted in a particular run, with their evidence links.
* Record citation-validation outcomes per source.

Everything goes through SQLAlchemy 2.0 ``mapped_column`` ORM models so
schema changes have one obvious place to land. Idempotent UPSERTs are
implemented with SQLite's ``ON CONFLICT`` clause via
``sqlalchemy.dialects.sqlite.insert``; that means the store talks SQLite
specifically (not vendor-portable, by design — Phase 2 ships the
single-process research database, not a multi-tenant deployment).

WAL mode is enabled on every ``connect`` so concurrent readers (e.g. a
dashboard inspecting an in-flight run) don't block the writer.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    create_engine,
    event,
    select,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
)

from .models import Claim, EvidenceLink, Source, ValidationResult

_DEFAULT_DB_PATH = "~/.plato/research.db"


# ---------------------------------------------------------------------------
# WAL: enabled on every fresh sqlite connection. Safe to register globally —
# it only fires for sqlite engines.
# ---------------------------------------------------------------------------


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Turn WAL on so concurrent readers don't block the writer."""
    # The listener is registered on the abstract Engine class; bail early
    # for any non-sqlite dialects that may have been instantiated elsewhere.
    cls_name = dbapi_connection.__class__.__module__
    if "sqlite" not in cls_name:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        # Foreign-key enforcement is intentionally left off: claims may be
        # added in a run before the run row is materialized, and Phase 2
        # schema is still settling. The FKs are documentation /
        # join hints rather than hard constraints for now.
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    pass


class _RunRow(_Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String)
    manifest_json: Mapped[str] = mapped_column(String)


class _SourceRow(_Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    doi: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    arxiv_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    openalex_id: Mapped[str | None] = mapped_column(String, nullable=True)
    semantic_scholar_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String)
    authors_json: Mapped[str] = mapped_column(String)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String, nullable=True)
    abstract: Mapped[str | None] = mapped_column(String, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    retracted: Mapped[bool] = mapped_column(Boolean, default=False)
    retrieved_via: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class _ClaimRow(_Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("runs.run_id"), nullable=True
    )
    source_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("sources.id"), nullable=True
    )
    text: Mapped[str] = mapped_column(String)
    quote_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String, nullable=True)


class _EvidenceLinkRow(_Base):
    __tablename__ = "evidence_links"

    claim_id: Mapped[str] = mapped_column(
        String, ForeignKey("claims.id"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(
        String, ForeignKey("sources.id"), primary_key=True
    )
    support: Mapped[str] = mapped_column(String)
    strength: Mapped[str] = mapped_column(String)
    quote_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


class _ValidationRow(_Base):
    __tablename__ = "validations"

    source_id: Mapped[str] = mapped_column(
        String, ForeignKey("sources.id"), primary_key=True
    )
    doi_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    arxiv_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    url_alive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    retracted: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime)


class _ArtifactRow(_Base):
    __tablename__ = "artifacts"

    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.run_id"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String, primary_key=True)
    sha256: Mapped[str] = mapped_column(String)


# ---------------------------------------------------------------------------
# Pydantic <-> ORM helpers
# ---------------------------------------------------------------------------


def _source_to_row(s: Source) -> dict[str, Any]:
    """Convert a Source pydantic model into a dict ready for ORM insert."""
    return {
        "id": s.id,
        "doi": s.doi,
        "arxiv_id": s.arxiv_id,
        "openalex_id": s.openalex_id,
        "semantic_scholar_id": s.semantic_scholar_id,
        "title": s.title,
        "authors_json": json.dumps(s.authors),
        "year": s.year,
        "venue": s.venue,
        "abstract": s.abstract,
        "pdf_url": s.pdf_url,
        "url": s.url,
        "retracted": bool(s.retracted),
        "retrieved_via": s.retrieved_via,
        "fetched_at": s.fetched_at,
    }


def _row_to_source(row: _SourceRow) -> Source:
    return Source(
        id=row.id,
        doi=row.doi,
        arxiv_id=row.arxiv_id,
        openalex_id=row.openalex_id,
        semantic_scholar_id=row.semantic_scholar_id,
        title=row.title,
        authors=json.loads(row.authors_json) if row.authors_json else [],
        year=row.year,
        venue=row.venue,
        abstract=row.abstract,
        pdf_url=row.pdf_url,
        url=row.url,
        retracted=bool(row.retracted),
        retrieved_via=cast(Any, row.retrieved_via),
        fetched_at=row.fetched_at,
    )


def _claim_to_row(c: Claim, run_id: str | None) -> dict[str, Any]:
    quote_start: int | None = None
    quote_end: int | None = None
    if c.quote_span is not None:
        quote_start, quote_end = c.quote_span
    return {
        "id": c.id,
        "run_id": run_id,
        "source_id": c.source_id,
        "text": c.text,
        "quote_start": quote_start,
        "quote_end": quote_end,
        "section": c.section,
    }


def _evidence_to_row(e: EvidenceLink) -> dict[str, Any]:
    quote_start: int | None = None
    quote_end: int | None = None
    if e.quote_span is not None:
        quote_start, quote_end = e.quote_span
    return {
        "claim_id": e.claim_id,
        "source_id": e.source_id,
        "support": e.support,
        "strength": e.strength,
        "quote_start": quote_start,
        "quote_end": quote_end,
    }


def _validation_to_row(v: ValidationResult) -> dict[str, Any]:
    return {
        "source_id": v.source_id,
        "doi_resolved": bool(v.doi_resolved),
        "arxiv_resolved": bool(v.arxiv_resolved),
        "url_alive": v.url_alive,
        "retracted": bool(v.retracted),
        "error": v.error,
        "checked_at": v.checked_at,
    }


def _row_to_validation(row: _ValidationRow) -> ValidationResult:
    return ValidationResult(
        source_id=row.source_id,
        doi_resolved=bool(row.doi_resolved),
        arxiv_resolved=bool(row.arxiv_resolved),
        url_alive=None if row.url_alive is None else bool(row.url_alive),
        retracted=bool(row.retracted),
        error=row.error,
        checked_at=row.checked_at,
    )


# ---------------------------------------------------------------------------
# Public Store
# ---------------------------------------------------------------------------


class Store:
    """
    SQLite-backed durable store for the Phase 2 research models.

    Each public method opens a fresh ``Session`` and commits before
    returning, so callers don't have to worry about transaction lifetimes.
    All UPSERTs are idempotent: re-adding a Source with the same DOI
    updates fields in place rather than producing a duplicate row.
    """

    def __init__(self, db_path: str | os.PathLike[str] | None = None) -> None:
        path = Path(db_path) if db_path is not None else Path(_DEFAULT_DB_PATH)
        path = path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = path

        # ``future=True`` is the default in SQLAlchemy 2.0 but we set it
        # explicitly so the intent is unmistakable. ``check_same_thread``
        # is left at its default (``True``) — the Store opens fresh
        # sessions per call rather than holding a connection across
        # threads, which is the safer pattern.
        self._engine = create_engine(
            f"sqlite:///{path}",
            future=True,
        )
        _Base.metadata.create_all(self._engine)

    # -- Sources -----------------------------------------------------------

    def add_source(self, s: Source) -> None:
        """
        UPSERT a Source. The conflict target is chosen in the same order
        the model surfaces dedupe keys: ``doi`` first, then ``arxiv_id``,
        then the internal ``id``.
        """
        row = _source_to_row(s)
        if s.doi is not None:
            conflict_cols = ["doi"]
        elif s.arxiv_id is not None:
            conflict_cols = ["arxiv_id"]
        else:
            conflict_cols = ["id"]

        # Update everything except the conflict column on conflict so
        # late-arriving fields (e.g. an abstract fetched in a second pass)
        # are persisted.
        update_cols = {
            k: v for k, v in row.items() if k not in conflict_cols
        }

        stmt = sqlite_insert(_SourceRow).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_=update_cols,
        )
        with Session(self._engine) as session:
            session.execute(stmt)
            session.commit()

    def get_source(self, source_id: str) -> Source | None:
        with Session(self._engine) as session:
            row = session.get(_SourceRow, source_id)
            if row is None:
                return None
            return _row_to_source(row)

    def list_sources(
        self, run_id: str | None = None, limit: int = 100
    ) -> list[Source]:
        """
        List sources. When ``run_id`` is given, scope to sources cited by
        a claim recorded under that run (sources themselves are not
        directly tagged with a run_id — they're shared across runs).
        """
        with Session(self._engine) as session:
            if run_id is None:
                stmt = select(_SourceRow).limit(limit)
                rows = session.execute(stmt).scalars().all()
                return [_row_to_source(r) for r in rows]

            stmt = (
                select(_SourceRow)
                .join(_ClaimRow, _ClaimRow.source_id == _SourceRow.id)
                .where(_ClaimRow.run_id == run_id)
                .distinct()
                .limit(limit)
            )
            rows = session.execute(stmt).scalars().all()
            return [_row_to_source(r) for r in rows]

    # -- Claims ------------------------------------------------------------

    def add_claim(self, c: Claim, run_id: str | None = None) -> None:
        row = _claim_to_row(c, run_id)
        # Claims are also UPSERTed so re-runs that re-emit the same claim
        # id don't double-count.
        update_cols = {k: v for k, v in row.items() if k != "id"}
        stmt = sqlite_insert(_ClaimRow).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_=update_cols,
        )
        with Session(self._engine) as session:
            session.execute(stmt)
            session.commit()

    # -- Evidence links ----------------------------------------------------

    def add_evidence(self, e: EvidenceLink) -> None:
        row = _evidence_to_row(e)
        update_cols = {
            k: v
            for k, v in row.items()
            if k not in {"claim_id", "source_id"}
        }
        stmt = sqlite_insert(_EvidenceLinkRow).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["claim_id", "source_id"],
            set_=update_cols,
        )
        with Session(self._engine) as session:
            session.execute(stmt)
            session.commit()

    # -- Validations -------------------------------------------------------

    def add_validation(self, v: ValidationResult) -> None:
        row = _validation_to_row(v)
        update_cols = {k: val for k, val in row.items() if k != "source_id"}
        stmt = sqlite_insert(_ValidationRow).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_id"],
            set_=update_cols,
        )
        with Session(self._engine) as session:
            session.execute(stmt)
            session.commit()

    def get_validation(self, source_id: str) -> ValidationResult | None:
        with Session(self._engine) as session:
            row = session.get(_ValidationRow, source_id)
            if row is None:
                return None
            return _row_to_validation(row)


__all__ = ["Store"]
