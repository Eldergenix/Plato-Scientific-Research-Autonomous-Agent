from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from threading import Lock
from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..auth import USER_COOKIE, USER_HEADER, extract_user_id
from ..domain.models import Project
from ..settings import Settings, get_settings
from ..storage.project_store import ProjectStore
from ..storage.publication_store import (
    PublicationStore,
    resolve_publications_database_url,
)

router = APIRouter()

_TAG_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_HOST_RE = re.compile(
    r"\A(?:localhost|\[[0-9a-fA-F:.]+\]|[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)(?::[0-9]{1,5})?\Z"
)
_STORE_LOCK = Lock()
_PUBLICATION_STORES: dict[tuple[Path, str], PublicationStore] = {}


class FeedAuthor(BaseModel):
    id: str | None = None
    user_id: str | None = None
    name: str = Field(max_length=240)
    affiliation: str | None = Field(default=None, max_length=320)
    avatar_url: str | None = None
    role: str | None = Field(default=None, max_length=80)


class PublishPublicationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    creator_name: str | None = Field(default=None, max_length=240)
    creator_affiliation: str | None = Field(default=None, max_length=320)
    creator_avatar_url: str | None = None
    source_run_id: str | None = Field(default=None, max_length=128)
    tagged_authors: list[FeedAuthor] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, max_length=20)


class PublicationCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    user_name: str | None = Field(default=None, max_length=240)
    user_affiliation: str | None = Field(default=None, max_length=320)
    user_avatar_url: str | None = None
    tagged_authors: list[FeedAuthor] = Field(default_factory=list)


class PublicationShareRequest(BaseModel):
    target: str = Field("link", max_length=80)


class AuthorTagRequest(BaseModel):
    authors: list[FeedAuthor] = Field(min_length=1, max_length=20)


class PublicationComment(BaseModel):
    id: str
    publication_id: str
    user_id: str
    user_name: str
    user_affiliation: str | None = None
    user_avatar_url: str | None = None
    body: str
    tagged_authors: list[FeedAuthor] = Field(default_factory=list)
    created_at: datetime


class Publication(BaseModel):
    id: str
    project_id: str
    creator_user_id: str
    creator_name: str
    creator_affiliation: str | None = None
    creator_avatar_url: str | None = None
    title: str
    description: str
    paper_pdf_url: str
    first_page_preview_url: str
    source_run_id: str | None = None
    source_stage: str
    authors: list[FeedAuthor] = Field(default_factory=list)
    tagged_authors: list[FeedAuthor] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    published_at: datetime
    updated_at: datetime
    like_count: int
    comment_count: int
    share_count: int
    comments: list[PublicationComment] = Field(default_factory=list)


class PublicationFeed(BaseModel):
    publications: list[Publication]


def _publication_store(settings: Settings = Depends(get_settings)) -> PublicationStore:
    database_url = resolve_publications_database_url(settings.project_root)
    cache_key = (settings.project_root, database_url)
    with _STORE_LOCK:
        store = _PUBLICATION_STORES.get(cache_key)
        if store is None:
            store = PublicationStore(settings.project_root, database_url=database_url)
            _PUBLICATION_STORES[cache_key] = store
        return store


def _require_actor(request: Request) -> str:
    user_id = extract_user_id(request)
    if user_id:
        return user_id
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "auth_required",
            "message": f"Send '{USER_HEADER}' or '{USER_COOKIE}' before publishing or reacting.",
        },
    )


def _project_store_for_actor(settings: Settings, actor: str) -> ProjectStore:
    return ProjectStore(settings.project_root / "users" / actor, user_id=actor)


def _load_owned_project(
    settings: Settings, actor: str, pid: str
) -> tuple[Project, Path]:
    stores = [
        _project_store_for_actor(settings, actor),
        ProjectStore(settings.project_root),
    ]
    for store in stores:
        try:
            project = store.load(pid)
        except FileNotFoundError:
            continue
        if project.user_id not in (None, actor):
            continue
        return project, store.project_dir(pid)
    raise HTTPException(404, detail={"code": "project_not_found"})


def _authors_from_project(project: Project) -> list[dict[str, Any]]:
    return [
        {
            "id": author.id,
            "name": author.name,
            "affiliation": author.affiliation,
            "role": author.role,
        }
        for author in sorted(
            project.publication_settings.authors, key=lambda item: item.order
        )
        if author.name.strip()
    ]


def _clean_tags(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = value.strip().lstrip("#")
        if not tag or not _TAG_RE.match(tag):
            raise HTTPException(422, detail={"code": "invalid_tag", "tag": value})
        key = tag.lower()
        if key not in seen:
            out.append(tag)
            seen.add(key)
    return out


def _description_from_paper(project_dir: Path) -> str:
    tex_path = project_dir / "paper" / "main.tex"
    if not tex_path.is_file():
        return "Published Plato research paper."
    text = tex_path.read_text(errors="ignore")
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:600] or "Published Plato research paper."


def _shape_author_list(authors: list[FeedAuthor]) -> list[dict[str, Any]]:
    return [author.model_dump(exclude_none=True) for author in authors]


def _rss_pub_date(value: datetime) -> str:
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(timezone.utc), usegmt=True)


def _first_header_value(value: str | None) -> str | None:
    first = (value or "").split(",", 1)[0].strip()
    return first or None


def _safe_host(value: str | None) -> str | None:
    if value is None or not _HOST_RE.match(value):
        return None
    port = value.rsplit(":", 1)[1] if ":" in value and not value.endswith("]") else None
    if port and port.isdigit() and int(port) > 65535:
        return None
    return value


def _safe_proto(value: str | None) -> str | None:
    proto = (value or "").strip().rstrip(":").lower()
    return proto if proto in {"http", "https"} else None


def _configured_public_origin(settings: Settings) -> str | None:
    raw = (settings.public_origin or "").strip()
    if not raw:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _public_base_url(request: Request, settings: Settings) -> str:
    configured = _configured_public_origin(settings)
    if configured:
        return configured

    forwarded_host = _safe_host(_first_header_value(request.headers.get("x-forwarded-host")))
    host = forwarded_host or _safe_host(request.url.netloc) or "localhost"
    forwarded_proto = _safe_proto(_first_header_value(request.headers.get("x-forwarded-proto")))
    proto = forwarded_proto or _safe_proto(request.url.scheme) or ("http" if "localhost" in host else "https")
    return f"{proto}://{host}".rstrip("/")


@router.get("/publications", response_model=PublicationFeed)
def list_publications(
    tag: str | None = None,
    q: str | None = None,
    author: str | None = None,
    limit: int = 50,
    store: PublicationStore = Depends(_publication_store),
) -> PublicationFeed:
    safe_limit = min(max(limit, 1), 100)
    publications = [
        Publication.model_validate(item)
        for item in store.list_publications(
            tag=tag,
            q=q,
            author=author,
            limit=safe_limit,
        )
    ]
    return PublicationFeed(publications=publications)


@router.get("/publications/rss.xml")
def rss_feed(
    request: Request,
    store: PublicationStore = Depends(_publication_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    base_url = _public_base_url(request, settings)
    items = []
    for publication in store.list_publications(limit=100):
        link = f"{base_url}/papers?publication={publication['id']}"
        authors = ", ".join(
            author["name"] for author in publication["authors"] if author.get("name")
        )
        description = publication["description"]
        if authors:
            description = f"{description}\n\nAuthors: {authors}"
        items.append(
            "\n".join(
                [
                    "<item>",
                    f"<guid>{escape(publication['id'])}</guid>",
                    f"<title>{escape(publication['title'])}</title>",
                    f"<link>{escape(link)}</link>",
                    f"<description>{escape(description)}</description>",
                    f"<pubDate>{escape(_rss_pub_date(publication['published_at']))}</pubDate>",
                    "</item>",
                ]
            )
        )
    xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8" ?>',
            '<rss version="2.0">',
            "<channel>",
            "<title>Plato research publications</title>",
            f"<link>{escape(base_url + '/papers')}</link>",
            "<description>Published research papers from Plato scientists.</description>",
            *items,
            "</channel>",
            "</rss>",
        ]
    )
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


@router.get("/publications/{publication_id}", response_model=Publication)
def get_publication(
    publication_id: str,
    store: PublicationStore = Depends(_publication_store),
) -> dict[str, Any]:
    try:
        return store.get_publication(publication_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "publication_not_found"}) from exc


@router.post(
    "/projects/{pid}/publications", response_model=Publication, status_code=201
)
def publish_project_paper(
    pid: str,
    body: PublishPublicationRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    store: PublicationStore = Depends(_publication_store),
) -> dict[str, Any]:
    actor = _require_actor(request)
    project, project_dir = _load_owned_project(settings, actor, pid)
    pdf_path = project_dir / "paper" / "main.pdf"
    if not pdf_path.is_file():
        raise HTTPException(409, detail={"code": "paper_artifact_missing"})

    authors = _authors_from_project(project)
    first_author = authors[0] if authors else {}
    creator_name = body.creator_name or first_author.get("name") or actor
    creator_affiliation = body.creator_affiliation or first_author.get("affiliation")
    paper_url = f"/api/v1/projects/{pid}/files/paper/main.pdf"
    return store.create_publication(
        {
            "project_id": pid,
            "creator_user_id": actor,
            "creator_name": creator_name,
            "creator_affiliation": creator_affiliation,
            "creator_avatar_url": body.creator_avatar_url,
            "title": body.title or project.name,
            "description": body.description or _description_from_paper(project_dir),
            "paper_pdf_url": paper_url,
            "first_page_preview_url": paper_url,
            "source_run_id": body.source_run_id,
            "source_stage": "paper",
            "authors": authors,
            "tagged_authors": _shape_author_list(body.tagged_authors),
            "tags": _clean_tags(body.tags),
        }
    )


@router.post(
    "/publications/{publication_id}/comments",
    response_model=PublicationComment,
    status_code=201,
)
def add_comment(
    publication_id: str,
    body: PublicationCommentRequest,
    request: Request,
    store: PublicationStore = Depends(_publication_store),
) -> dict[str, Any]:
    actor = _require_actor(request)
    try:
        return store.add_comment(
            publication_id,
            {
                "user_id": actor,
                "user_name": body.user_name or actor,
                "user_affiliation": body.user_affiliation,
                "user_avatar_url": body.user_avatar_url,
                "body": body.body.strip(),
                "tagged_authors": _shape_author_list(body.tagged_authors),
            },
        )
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "publication_not_found"}) from exc


@router.put("/publications/{publication_id}/likes/me", response_model=Publication)
def like_publication(
    publication_id: str,
    request: Request,
    store: PublicationStore = Depends(_publication_store),
) -> dict[str, Any]:
    try:
        return store.set_like(publication_id, _require_actor(request), True)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "publication_not_found"}) from exc


@router.delete("/publications/{publication_id}/likes/me", response_model=Publication)
def unlike_publication(
    publication_id: str,
    request: Request,
    store: PublicationStore = Depends(_publication_store),
) -> dict[str, Any]:
    try:
        return store.set_like(publication_id, _require_actor(request), False)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "publication_not_found"}) from exc


@router.post(
    "/publications/{publication_id}/shares", response_model=Publication, status_code=201
)
def share_publication(
    publication_id: str,
    body: PublicationShareRequest,
    request: Request,
    store: PublicationStore = Depends(_publication_store),
) -> dict[str, Any]:
    try:
        return store.add_share(publication_id, _require_actor(request), body.target)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "publication_not_found"}) from exc


@router.post("/publications/{publication_id}/author-tags", response_model=Publication)
def tag_authors(
    publication_id: str,
    body: AuthorTagRequest,
    request: Request,
    store: PublicationStore = Depends(_publication_store),
) -> dict[str, Any]:
    _require_actor(request)
    try:
        return store.tag_authors(publication_id, _shape_author_list(body.authors))
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "publication_not_found"}) from exc
