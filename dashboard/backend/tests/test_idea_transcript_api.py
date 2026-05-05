"""Iter-6 — tests for the /api/v1/projects/{pid}/idea_transcript endpoint.

The endpoint reads ``<project_root>/<pid>/idea_generation_output/idea_transcript.jsonl``
and returns one entry per maker/hater turn. These tests pin the
contract via fabricated JSONL files so the suite runs without hitting
any LLM.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app() -> FastAPI:
    from plato_dashboard.api.idea_transcript import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(tmp_project_root: Path):  # noqa: ARG001 — fixture sets project_root
    app = _make_app()
    with TestClient(app) as c:
        yield c


def _write_transcript(project_root: Path, pid: str, lines: list[dict]) -> Path:
    out_dir = project_root / pid / "idea_generation_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = out_dir / "idea_transcript.jsonl"
    log.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return log


def test_returns_empty_when_project_missing(client) -> None:
    resp = client.get("/api/v1/projects/no_such_pid/idea_transcript")
    assert resp.status_code == 200
    assert resp.json() == {"turns": []}


def test_returns_empty_when_log_missing(client, tmp_project_root: Path) -> None:
    (tmp_project_root / "pid_a").mkdir()
    resp = client.get("/api/v1/projects/pid_a/idea_transcript")
    assert resp.status_code == 200
    assert resp.json() == {"turns": []}


def test_returns_turns_in_order(client, tmp_project_root: Path) -> None:
    _write_transcript(
        tmp_project_root,
        "pid_b",
        [
            {
                "agent": "idea_maker",
                "text": "first idea",
                "ts": "2026-05-04T10:00:00+00:00",
                "iteration": 0,
            },
            {
                "agent": "idea_hater",
                "text": "no good",
                "ts": "2026-05-04T10:01:00+00:00",
                "iteration": 0,
            },
            {
                "agent": "idea_maker",
                "text": "second idea",
                "ts": "2026-05-04T10:02:00+00:00",
                "iteration": 1,
            },
        ],
    )
    resp = client.get("/api/v1/projects/pid_b/idea_transcript")
    assert resp.status_code == 200
    body = resp.json()
    assert [t["agent"] for t in body["turns"]] == [
        "idea_maker",
        "idea_hater",
        "idea_maker",
    ]
    assert body["turns"][0]["text"] == "first idea"
    assert body["turns"][2]["iteration"] == 1


def test_skips_unknown_agent_and_torn_lines(
    client, tmp_project_root: Path
) -> None:
    out_dir = tmp_project_root / "pid_torn" / "idea_generation_output"
    out_dir.mkdir(parents=True)
    log = out_dir / "idea_transcript.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps(
                    {"agent": "idea_maker", "text": "ok", "ts": "x"}
                ),
                "{ not valid json",  # torn flush
                json.dumps({"agent": "random_role", "text": "spoof"}),
                json.dumps({"agent": "idea_hater", "text": ""}),
                "",  # blank line
            ]
        )
        + "\n"
    )
    resp = client.get("/api/v1/projects/pid_torn/idea_transcript")
    assert resp.status_code == 200
    turns = resp.json()["turns"]
    # Only the well-formed maker turn survives. The empty hater text is
    # technically valid (str), so it's preserved — frontend renders an
    # empty bubble. The unknown agent is dropped because the Pydantic
    # schema only allows idea_maker / idea_hater.
    agents = [t["agent"] for t in turns]
    assert "random_role" not in agents
    assert agents.count("idea_maker") == 1
    assert agents.count("idea_hater") == 1
