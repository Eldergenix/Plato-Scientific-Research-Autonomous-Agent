from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

_PUBLICATION_ID_PREFIX = "pub"
_COMMENT_ID_PREFIX = "cmt"
_SHARE_ID_PREFIX = "shr"
_SCHEMA_LOCK = Lock()

metadata = MetaData()

publications = Table(
    "publications",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), nullable=False, index=True),
    Column("creator_user_id", String(128), nullable=False, index=True),
    Column("creator_name", String(240), nullable=False),
    Column("creator_affiliation", String(320), nullable=True),
    Column("creator_avatar_url", Text, nullable=True),
    Column("title", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("paper_pdf_url", Text, nullable=False),
    Column("first_page_preview_url", Text, nullable=False),
    Column("source_run_id", String(128), nullable=True),
    Column("source_stage", String(64), nullable=False, default="paper"),
    Column("authors_json", Text, nullable=False),
    Column("tagged_authors_json", Text, nullable=False),
    Column("tags_json", Text, nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False, index=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

publication_comments = Table(
    "publication_comments",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("publication_id", String(64), nullable=False, index=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("user_name", String(240), nullable=False),
    Column("user_affiliation", String(320), nullable=True),
    Column("user_avatar_url", Text, nullable=True),
    Column("body", Text, nullable=False),
    Column("tagged_authors_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

publication_likes = Table(
    "publication_likes",
    metadata,
    Column("publication_id", String(64), nullable=False, index=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("publication_id", "user_id", name="uq_publication_likes_publication_user"),
)

publication_shares = Table(
    "publication_shares",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("publication_id", String(64), nullable=False, index=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("target", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _json_dump(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def resolve_publications_database_url(project_root: Path) -> str:
    url = (
        os.environ.get("PLATO_PUBLICATIONS_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if not url:
        db_path = project_root / "publications.db"
        return f"sqlite:///{db_path}"
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def _ensure_schema(engine: Engine) -> None:
    with _SCHEMA_LOCK:
        metadata.create_all(engine)


class PublicationStore:
    def __init__(self, project_root: Path, database_url: str | None = None):
        self.database_url = database_url or resolve_publications_database_url(project_root)
        self.engine = create_engine(self.database_url, future=True, pool_pre_ping=True)
        _ensure_schema(self.engine)

    @classmethod
    def from_engine(cls, engine: Engine) -> "PublicationStore":
        store = cls.__new__(cls)
        store.database_url = str(engine.url)
        store.engine = engine
        _ensure_schema(engine)
        return store

    def create_publication(self, data: dict[str, Any]) -> dict[str, Any]:
        now = _utcnow()
        publication_id = _new_id(_PUBLICATION_ID_PREFIX)
        row = {
            "id": publication_id,
            "project_id": data["project_id"],
            "creator_user_id": data["creator_user_id"],
            "creator_name": data["creator_name"],
            "creator_affiliation": data.get("creator_affiliation"),
            "creator_avatar_url": data.get("creator_avatar_url"),
            "title": data["title"],
            "description": data["description"],
            "paper_pdf_url": data["paper_pdf_url"],
            "first_page_preview_url": data["first_page_preview_url"],
            "source_run_id": data.get("source_run_id"),
            "source_stage": data.get("source_stage") or "paper",
            "authors_json": _json_dump(data.get("authors", [])),
            "tagged_authors_json": _json_dump(data.get("tagged_authors", [])),
            "tags_json": _json_dump(data.get("tags", [])),
            "published_at": now,
            "updated_at": now,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(publications).values(**row))
        return self.get_publication(publication_id)

    def list_publications(
        self,
        *,
        tag: str | None = None,
        q: str | None = None,
        author: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = select(publications).order_by(publications.c.published_at.desc()).limit(limit)
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                func.lower(publications.c.title).like(like)
                | func.lower(publications.c.description).like(like)
                | func.lower(publications.c.creator_name).like(like)
            )
        with self.engine.begin() as conn:
            rows = [dict(row._mapping) for row in conn.execute(stmt)]

        shaped = [self._shape_publication(row) for row in rows]
        if tag:
            wanted = tag.lower()
            shaped = [
                item
                for item in shaped
                if wanted in {str(value).lower() for value in item["tags"]}
            ]
        if author:
            wanted = author.lower()
            shaped = [
                item
                for item in shaped
                if wanted in item["creator_user_id"].lower()
                or wanted in item["creator_name"].lower()
                or any(
                    wanted in str(author_record.get("name", "")).lower()
                    or wanted in str(author_record.get("user_id", "")).lower()
                    for author_record in item["authors"]
                )
            ]
        return shaped

    def get_publication(self, publication_id: str) -> dict[str, Any]:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(publications).where(publications.c.id == publication_id)
            ).first()
        if row is None:
            raise KeyError(publication_id)
        return self._shape_publication(dict(row._mapping), include_comments=True)

    def add_comment(self, publication_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self.get_publication(publication_id)
        now = _utcnow()
        row = {
            "id": _new_id(_COMMENT_ID_PREFIX),
            "publication_id": publication_id,
            "user_id": data["user_id"],
            "user_name": data["user_name"],
            "user_affiliation": data.get("user_affiliation"),
            "user_avatar_url": data.get("user_avatar_url"),
            "body": data["body"],
            "tagged_authors_json": _json_dump(data.get("tagged_authors", [])),
            "created_at": now,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(publication_comments).values(**row))
            conn.execute(
                update(publications)
                .where(publications.c.id == publication_id)
                .values(updated_at=now)
            )
        return self._shape_comment(row)

    def set_like(self, publication_id: str, user_id: str, liked: bool) -> dict[str, Any]:
        self.get_publication(publication_id)
        with self.engine.begin() as conn:
            if liked:
                existing = conn.execute(
                    select(publication_likes).where(
                        (publication_likes.c.publication_id == publication_id)
                        & (publication_likes.c.user_id == user_id)
                    )
                ).first()
                if existing is None:
                    conn.execute(
                        insert(publication_likes).values(
                            publication_id=publication_id,
                            user_id=user_id,
                            created_at=_utcnow(),
                        )
                    )
            else:
                conn.execute(
                    delete(publication_likes).where(
                        (publication_likes.c.publication_id == publication_id)
                        & (publication_likes.c.user_id == user_id)
                    )
                )
        return self.get_publication(publication_id)

    def add_share(self, publication_id: str, user_id: str, target: str) -> dict[str, Any]:
        self.get_publication(publication_id)
        with self.engine.begin() as conn:
            conn.execute(
                insert(publication_shares).values(
                    id=_new_id(_SHARE_ID_PREFIX),
                    publication_id=publication_id,
                    user_id=user_id,
                    target=target,
                    created_at=_utcnow(),
                )
            )
        return self.get_publication(publication_id)

    def tag_authors(self, publication_id: str, tagged_authors: list[dict[str, Any]]) -> dict[str, Any]:
        current = self.get_publication(publication_id)
        merged = current["tagged_authors"][:]
        seen = {
            (str(item.get("user_id") or ""), str(item.get("name") or "").lower())
            for item in merged
        }
        for author in tagged_authors:
            key = (str(author.get("user_id") or ""), str(author.get("name") or "").lower())
            if key not in seen:
                merged.append(author)
                seen.add(key)
        with self.engine.begin() as conn:
            conn.execute(
                update(publications)
                .where(publications.c.id == publication_id)
                .values(tagged_authors_json=_json_dump(merged), updated_at=_utcnow())
            )
        return self.get_publication(publication_id)

    def _shape_publication(
        self,
        row: dict[str, Any],
        *,
        include_comments: bool = False,
    ) -> dict[str, Any]:
        publication_id = row["id"]
        with self.engine.begin() as conn:
            like_count = conn.scalar(
                select(func.count()).select_from(publication_likes).where(
                    publication_likes.c.publication_id == publication_id
                )
            )
            comment_count = conn.scalar(
                select(func.count()).select_from(publication_comments).where(
                    publication_comments.c.publication_id == publication_id
                )
            )
            share_count = conn.scalar(
                select(func.count()).select_from(publication_shares).where(
                    publication_shares.c.publication_id == publication_id
                )
            )
            comments = []
            if include_comments:
                comments = [
                    self._shape_comment(dict(comment._mapping))
                    for comment in conn.execute(
                        select(publication_comments)
                        .where(publication_comments.c.publication_id == publication_id)
                        .order_by(publication_comments.c.created_at.asc())
                    )
                ]
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "creator_user_id": row["creator_user_id"],
            "creator_name": row["creator_name"],
            "creator_affiliation": row.get("creator_affiliation"),
            "creator_avatar_url": row.get("creator_avatar_url"),
            "title": row["title"],
            "description": row["description"],
            "paper_pdf_url": row["paper_pdf_url"],
            "first_page_preview_url": row["first_page_preview_url"],
            "source_run_id": row.get("source_run_id"),
            "source_stage": row.get("source_stage") or "paper",
            "authors": _json_load(row.get("authors_json"), []),
            "tagged_authors": _json_load(row.get("tagged_authors_json"), []),
            "tags": _json_load(row.get("tags_json"), []),
            "published_at": row["published_at"],
            "updated_at": row["updated_at"],
            "like_count": like_count or 0,
            "comment_count": comment_count or 0,
            "share_count": share_count or 0,
            "comments": comments,
        }

    @staticmethod
    def _shape_comment(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "publication_id": row["publication_id"],
            "user_id": row["user_id"],
            "user_name": row["user_name"],
            "user_affiliation": row.get("user_affiliation"),
            "user_avatar_url": row.get("user_avatar_url"),
            "body": row["body"],
            "tagged_authors": _json_load(row.get("tagged_authors_json"), []),
            "created_at": row["created_at"],
        }
