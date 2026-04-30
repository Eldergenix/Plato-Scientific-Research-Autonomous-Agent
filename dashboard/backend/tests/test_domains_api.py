"""Tests for ``GET /api/v1/domains``.

The router is intentionally standalone (it doesn't yet ship inside
``create_app``), so each test mounts it on a throwaway FastAPI instance.
That keeps the route fully unit-testable without touching ``server.py``.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from plato_dashboard.api.domains import router as domains_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(domains_router)
    return TestClient(app)


def test_get_domains_returns_astro_and_biology() -> None:
    resp = _client().get("/api/v1/domains")
    assert resp.status_code == 200
    body = resp.json()

    names = {d["name"] for d in body["domains"]}
    assert {"astro", "biology"} <= names
    assert body["default"] == "astro"


def test_each_domain_has_full_schema() -> None:
    resp = _client().get("/api/v1/domains")
    assert resp.status_code == 200

    expected_keys = {
        "name",
        "retrieval_sources",
        "keyword_extractor",
        "journal_presets",
        "executor",
        "novelty_corpus",
    }
    for profile in resp.json()["domains"]:
        assert expected_keys <= profile.keys(), profile
        assert isinstance(profile["retrieval_sources"], list)
        assert isinstance(profile["journal_presets"], list)
        assert isinstance(profile["name"], str)
        assert isinstance(profile["keyword_extractor"], str)
        assert isinstance(profile["executor"], str)
        assert isinstance(profile["novelty_corpus"], str)


def test_astro_payload_matches_registered_profile() -> None:
    body = _client().get("/api/v1/domains").json()
    astro = next(d for d in body["domains"] if d["name"] == "astro")

    assert astro["retrieval_sources"] == [
        "semantic_scholar",
        "arxiv",
        "openalex",
        "ads",
    ]
    assert astro["keyword_extractor"] == "cmbagent"
    assert astro["executor"] == "cmbagent"
    assert astro["novelty_corpus"] == "arxiv:astro-ph"
    assert "AAS" in astro["journal_presets"]
    assert "NONE" in astro["journal_presets"]


def test_biology_payload_matches_registered_profile() -> None:
    body = _client().get("/api/v1/domains").json()
    bio = next(d for d in body["domains"] if d["name"] == "biology")

    assert bio["retrieval_sources"] == ["pubmed", "openalex", "semantic_scholar"]
    assert bio["keyword_extractor"] == "mesh"
    assert bio["novelty_corpus"] == "pubmed"
    assert "NATURE" in bio["journal_presets"]


def test_domains_listing_is_sorted_alphabetically() -> None:
    body = _client().get("/api/v1/domains").json()
    names = [d["name"] for d in body["domains"]]
    assert names == sorted(names)
