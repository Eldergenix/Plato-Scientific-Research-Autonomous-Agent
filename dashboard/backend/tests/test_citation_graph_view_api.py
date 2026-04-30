"""Smoke tests for ``GET /api/v1/runs/{run_id}/citation_graph``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _seed_run_dir(project_root: Path, project_id: str, run_id: str) -> Path:
    run_dir = project_root / project_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _full_payload() -> dict:
    return {
        "seeds": [
            {
                "id": "W1",
                "title": "Seed paper one",
                "doi": "10.1000/seed1",
                "openalex_id": "W1",
            },
            {
                "id": "W2",
                "title": "Seed paper two",
                "doi": None,
                "openalex_id": "W2",
            },
        ],
        "expanded": [
            {
                "id": "W3",
                "title": "Expansion paper three",
                "doi": "10.1000/exp3",
                "openalex_id": "W3",
            },
            {
                "id": "W4",
                "title": "Expansion paper four",
                "doi": None,
                "openalex_id": "W4",
            },
        ],
        "edges": [
            {"from": "W1", "to": "W3", "kind": "references"},
            {"from": "W1", "to": "W4", "kind": "references"},
            {"from": "W2", "to": "W3", "kind": "cited_by"},
        ],
        "stats": {
            "seed_count": 2,
            "expanded_count": 2,
            "edge_count": 3,
            "duplicates_filtered": 1,
        },
    }


def test_returns_404_for_unknown_run(client) -> None:
    resp = client.get("/api/v1/runs/run_nope/citation_graph")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "run_not_found"


def test_returns_empty_payload_when_artefact_missing(
    client, tmp_project_root: Path
) -> None:
    """Run dir exists but neither citation_graph.json nor manifest.json does."""
    _seed_run_dir(tmp_project_root, "prj_a", "run_empty")

    resp = client.get("/api/v1/runs/run_empty/citation_graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "seeds": [],
        "expanded": [],
        "edges": [],
        "stats": {
            "seed_count": 0,
            "expanded_count": 0,
            "edge_count": 0,
            "duplicates_filtered": 0,
        },
    }


def test_returns_full_payload_from_canonical_file(
    client, tmp_project_root: Path
) -> None:
    run_dir = _seed_run_dir(tmp_project_root, "prj_a", "run_full")
    (run_dir / "citation_graph.json").write_text(json.dumps(_full_payload()))

    resp = client.get("/api/v1/runs/run_full/citation_graph")
    assert resp.status_code == 200
    body = resp.json()

    assert {n["id"] for n in body["seeds"]} == {"W1", "W2"}
    assert {n["id"] for n in body["expanded"]} == {"W3", "W4"}
    assert len(body["edges"]) == 3
    assert body["stats"]["seed_count"] == 2
    assert body["stats"]["expanded_count"] == 2
    assert body["stats"]["edge_count"] == 3


def test_falls_back_to_manifest_extra_when_canonical_absent(
    client, tmp_project_root: Path
) -> None:
    run_dir = _seed_run_dir(tmp_project_root, "prj_a", "run_manifest")
    (run_dir / "manifest.json").write_text(
        json.dumps({"extra": {"citation_graph": _full_payload()}})
    )

    resp = client.get("/api/v1/runs/run_manifest/citation_graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["seed_count"] == 2
    assert body["stats"]["expanded_count"] == 2


def test_canonical_wins_over_manifest_fallback(
    client, tmp_project_root: Path
) -> None:
    run_dir = _seed_run_dir(tmp_project_root, "prj_a", "run_both")
    (run_dir / "citation_graph.json").write_text(
        json.dumps(
            {
                "seeds": [{"id": "C1", "title": "canonical"}],
                "expanded": [],
                "edges": [],
            }
        )
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "extra": {
                    "citation_graph": {
                        "seeds": [{"id": "M1", "title": "manifest"}],
                        "expanded": [],
                        "edges": [],
                    }
                }
            }
        )
    )

    resp = client.get("/api/v1/runs/run_both/citation_graph")
    assert resp.status_code == 200
    assert resp.json()["seeds"][0]["id"] == "C1"


def test_drops_expanded_node_colliding_with_seed(
    client, tmp_project_root: Path
) -> None:
    """Self-loops in expanded should be filtered + counted as duplicates."""
    run_dir = _seed_run_dir(tmp_project_root, "prj_a", "run_dedup")
    (run_dir / "citation_graph.json").write_text(
        json.dumps(
            {
                "seeds": [{"id": "W1", "title": "seed"}],
                "expanded": [
                    {"id": "W1", "title": "self-loop"},
                    {"id": "W2", "title": "ok"},
                ],
                "edges": [],
            }
        )
    )

    resp = client.get("/api/v1/runs/run_dedup/citation_graph")
    assert resp.status_code == 200
    body = resp.json()
    assert {n["id"] for n in body["expanded"]} == {"W2"}
    assert body["stats"]["duplicates_filtered"] >= 1


def test_drops_edges_pointing_at_unknown_nodes(
    client, tmp_project_root: Path
) -> None:
    """An edge that references a node id we dropped is itself dropped."""
    run_dir = _seed_run_dir(tmp_project_root, "prj_a", "run_orphan")
    (run_dir / "citation_graph.json").write_text(
        json.dumps(
            {
                "seeds": [{"id": "S1", "title": "seed"}],
                "expanded": [{"id": "E1", "title": "expansion"}],
                "edges": [
                    {"from": "S1", "to": "E1", "kind": "references"},
                    # Orphan: ghost target.
                    {"from": "S1", "to": "ghost", "kind": "references"},
                ],
            }
        )
    )

    resp = client.get("/api/v1/runs/run_orphan/citation_graph")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["edges"]) == 1
    assert body["edges"][0]["to"] == "E1"


def test_blocks_cross_tenant_request(
    client, tmp_project_root: Path
) -> None:
    """A request with X-Plato-User != manifest.user_id is forbidden."""
    run_dir = _seed_run_dir(tmp_project_root, "prj_a", "run_owned")
    (run_dir / "manifest.json").write_text(
        json.dumps({"user_id": "alice", "extra": {}})
    )
    (run_dir / "citation_graph.json").write_text(json.dumps(_full_payload()))

    resp = client.get(
        "/api/v1/runs/run_owned/citation_graph",
        headers={"X-Plato-User": "bob"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "cross_tenant_blocked"


def test_same_tenant_passes(client, tmp_project_root: Path) -> None:
    run_dir = _seed_run_dir(tmp_project_root, "prj_a", "run_owned_match")
    (run_dir / "manifest.json").write_text(
        json.dumps({"user_id": "alice", "extra": {}})
    )
    (run_dir / "citation_graph.json").write_text(json.dumps(_full_payload()))

    resp = client.get(
        "/api/v1/runs/run_owned_match/citation_graph",
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 200


def test_response_schema_keys(client, tmp_project_root: Path) -> None:
    """Every response must expose the four top-level keys with the right types."""
    run_dir = _seed_run_dir(tmp_project_root, "prj_a", "run_schema")
    (run_dir / "citation_graph.json").write_text(json.dumps(_full_payload()))

    resp = client.get("/api/v1/runs/run_schema/citation_graph")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"seeds", "expanded", "edges", "stats"}
    assert isinstance(body["seeds"], list)
    assert isinstance(body["expanded"], list)
    assert isinstance(body["edges"], list)
    assert isinstance(body["stats"], dict)
    assert set(body["stats"].keys()) == {
        "seed_count",
        "expanded_count",
        "edge_count",
        "duplicates_filtered",
    }
    for node in body["seeds"] + body["expanded"]:
        assert set(node.keys()) == {"id", "title", "doi", "openalex_id"}
    for edge in body["edges"]:
        assert set(edge.keys()) == {"from", "to", "kind"}
        assert edge["kind"] in ("references", "cited_by")


@pytest.mark.parametrize("payload", [None, "string", 42, ["a", "b"]])
def test_corrupt_root_value_returns_empty(
    client, tmp_project_root: Path, payload
) -> None:
    """A canonical file with a non-dict root degrades to an empty payload."""
    run_dir = _seed_run_dir(tmp_project_root, "prj_a", f"run_garbled_{type(payload).__name__}")
    (run_dir / "citation_graph.json").write_text(json.dumps(payload))

    resp = client.get(f"/api/v1/runs/{run_dir.name}/citation_graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["seed_count"] == 0
