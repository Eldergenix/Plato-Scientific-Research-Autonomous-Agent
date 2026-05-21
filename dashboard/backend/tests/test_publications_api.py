from __future__ import annotations

from pathlib import Path

from plato_dashboard.api import publications as publications_api
from plato_dashboard.settings import Settings


def _create_project_with_paper(client, tmp_project_root: Path) -> str:
    resp = client.post(
        "/api/v1/projects",
        json={"name": "Quantum lensing manuscript"},
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    settings = {
        "authors": [
            {
                "id": "auth_ada",
                "name": "Ada Lovelace",
                "affiliation": "Analytical Engine Lab",
                "role": "Lead author",
                "order": 0,
            }
        ],
        "dates": {},
        "tasks": [],
    }
    saved = client.put(
        f"/api/v1/projects/{pid}/publication_settings",
        json=settings,
        headers={"X-Plato-User": "alice"},
    )
    assert saved.status_code == 200, saved.text

    paper_dir = tmp_project_root / "users" / "alice" / pid / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "main.pdf").write_bytes(b"%PDF-1.5\n")
    (paper_dir / "main.tex").write_text(r"\begin{abstract}A strong research summary.\end{abstract}")
    return pid


def test_publication_feed_requires_identity_for_publish_but_not_read(client, tmp_project_root: Path) -> None:
    pid = _create_project_with_paper(client, tmp_project_root)

    anonymous = client.post(f"/api/v1/projects/{pid}/publications", json={})
    assert anonymous.status_code == 401

    created = client.post(
        f"/api/v1/projects/{pid}/publications",
        json={
            "title": "Quantum Lensing From Autonomous Search",
            "description": "A first-page feed summary.",
            "tags": ["cosmology", "agentic-science"],
            "creator_avatar_url": "https://example.test/ada.png",
            "tagged_authors": [{"name": "Grace Hopper", "affiliation": "Compiler Lab"}],
        },
        headers={"X-Plato-User": "alice"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["title"] == "Quantum Lensing From Autonomous Search"
    assert body["creator_name"] == "Ada Lovelace"
    assert body["creator_affiliation"] == "Analytical Engine Lab"
    assert body["creator_avatar_url"] == "https://example.test/ada.png"
    assert body["paper_pdf_url"].endswith(f"/projects/{pid}/files/paper/main.pdf")
    assert body["first_page_preview_url"] == body["paper_pdf_url"]
    assert body["authors"][0]["affiliation"] == "Analytical Engine Lab"
    assert body["tagged_authors"][0]["name"] == "Grace Hopper"

    feed = client.get("/api/v1/publications")
    assert feed.status_code == 200
    assert feed.json()["publications"][0]["id"] == body["id"]


def test_publication_store_dependency_reuses_process_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PLATO_PUBLICATIONS_DATABASE_URL", raising=False)
    publications_api._PUBLICATION_STORES.clear()

    settings = Settings(project_root=tmp_path)
    try:
        first = publications_api._publication_store(settings)
        second = publications_api._publication_store(settings)
    finally:
        publications_api._PUBLICATION_STORES.clear()

    assert first is second


def test_publication_social_actions_and_rss(client, tmp_project_root: Path) -> None:
    pid = _create_project_with_paper(client, tmp_project_root)
    created = client.post(
        f"/api/v1/projects/{pid}/publications",
        json={"title": "RSS-ready Plato paper", "description": "RSS description", "tags": ["rss"]},
        headers={"X-Plato-User": "alice"},
    ).json()
    publication_id = created["id"]

    comment = client.post(
        f"/api/v1/publications/{publication_id}/comments",
        json={
            "body": "Great result. Tagging Bob for review.",
            "user_name": "Grace Hopper",
            "tagged_authors": [{"name": "Bob Scientist", "user_id": "bob"}],
        },
        headers={"X-Plato-User": "grace"},
    )
    assert comment.status_code == 201, comment.text
    assert comment.json()["tagged_authors"][0]["user_id"] == "bob"

    liked = client.put(
        f"/api/v1/publications/{publication_id}/likes/me",
        headers={"X-Plato-User": "grace"},
    )
    assert liked.status_code == 200
    assert liked.json()["like_count"] == 1

    shared = client.post(
        f"/api/v1/publications/{publication_id}/shares",
        json={"target": "link"},
        headers={"X-Plato-User": "grace"},
    )
    assert shared.status_code == 201
    assert shared.json()["share_count"] == 1

    tagged = client.post(
        f"/api/v1/publications/{publication_id}/author-tags",
        json={"authors": [{"name": "Katherine Johnson", "affiliation": "NASA"}]},
        headers={"X-Plato-User": "alice"},
    )
    assert tagged.status_code == 200
    assert tagged.json()["tagged_authors"][-1]["name"] == "Katherine Johnson"

    detail = client.get(f"/api/v1/publications/{publication_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["comment_count"] == 1
    assert detail_body["comments"][0]["body"].startswith("Great result")

    filtered = client.get("/api/v1/publications?tag=rss")
    assert filtered.status_code == 200
    assert filtered.json()["publications"][0]["id"] == publication_id

    unliked = client.delete(
        f"/api/v1/publications/{publication_id}/likes/me",
        headers={"X-Plato-User": "grace"},
    )
    assert unliked.status_code == 200
    assert unliked.json()["like_count"] == 0

    rss = client.get(
        "/api/v1/publications/rss.xml",
        headers={"x-forwarded-host": "plato.example.test", "x-forwarded-proto": "https"},
    )
    assert rss.status_code == 200
    assert "application/rss+xml" in rss.headers["content-type"]
    assert "<link>https://plato.example.test/papers</link>" in rss.text
    assert "<title>RSS-ready Plato paper</title>" in rss.text
    assert "<pubDate>" in rss.text
    assert " GMT</pubDate>" in rss.text


def test_publication_rss_rejects_spoofed_forwarded_metadata(
    client,
    tmp_project_root: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("PLATO_PUBLIC_ORIGIN", raising=False)
    pid = _create_project_with_paper(client, tmp_project_root)
    created = client.post(
        f"/api/v1/projects/{pid}/publications",
        json={"title": "Safe RSS paper"},
        headers={"X-Plato-User": "alice"},
    )
    assert created.status_code == 201, created.text

    rss = client.get(
        "/api/v1/publications/rss.xml",
        headers={
            "x-forwarded-host": "evil.example/path",
            "x-forwarded-proto": "javascript",
        },
    )

    assert rss.status_code == 200
    assert "evil.example" not in rss.text
    assert "javascript://" not in rss.text


def test_publication_rss_uses_configured_public_origin(
    client,
    tmp_project_root: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLATO_PUBLIC_ORIGIN", "https://discovering.app/")
    pid = _create_project_with_paper(client, tmp_project_root)
    created = client.post(
        f"/api/v1/projects/{pid}/publications",
        json={"title": "Configured origin RSS paper"},
        headers={"X-Plato-User": "alice"},
    )
    assert created.status_code == 201, created.text

    rss = client.get(
        "/api/v1/publications/rss.xml",
        headers={
            "x-forwarded-host": "evil.example",
            "x-forwarded-proto": "http",
        },
    )

    assert rss.status_code == 200
    assert "<link>https://discovering.app/papers</link>" in rss.text
    assert "evil.example" not in rss.text


def test_publish_rejects_projects_without_pdf_artifact(client) -> None:
    created = client.post(
        "/api/v1/projects",
        json={"name": "Draft project"},
        headers={"X-Plato-User": "alice"},
    ).json()
    resp = client.post(
        f"/api/v1/projects/{created['id']}/publications",
        json={},
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "paper_artifact_missing"
