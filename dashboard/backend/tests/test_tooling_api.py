"""Tests for backend-backed tool and MCP configuration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from plato_dashboard import tooling


def test_tooling_lists_real_plato_tools(client) -> None:
    resp = client.get("/api/v1/tooling")
    assert resp.status_code == 200
    body = resp.json()
    tool_ids = {tool["id"] for tool in body["tools"]}
    assert "search_literature" in tool_ids
    assert "run_scientific_analysis" in tool_ids
    assert "prepare_expansionhunter_denovo" in tool_ids
    assert "prepare_gauchian_calling" in tool_ids
    assert "research-planner" not in tool_ids
    assert body["mcp_servers"][0]["id"] == "plato-tool-registry"


def test_tool_toggle_persists_per_user(client, tmp_project_root: Path) -> None:
    resp = client.put(
        "/api/v1/tooling/tools/search_literature",
        json={"enabled": False},
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    prefs = tmp_project_root / "users" / "alice" / "tooling_config.json"
    assert json.loads(prefs.read_text())["disabled_tools"] == ["search_literature"]

    alice = client.get("/api/v1/tooling", headers={"X-Plato-User": "alice"}).json()
    bob = client.get("/api/v1/tooling", headers={"X-Plato-User": "bob"}).json()
    alice_tool = next(
        tool for tool in alice["tools"] if tool["id"] == "search_literature"
    )
    bob_tool = next(tool for tool in bob["tools"] if tool["id"] == "search_literature")
    assert alice_tool["enabled"] is False
    assert bob_tool["enabled"] is True


def test_tool_toggle_persists_per_lab(client, tmp_project_root: Path) -> None:
    resp = client.put(
        "/api/v1/tooling/tools/search_literature",
        json={"enabled": False},
        headers={"X-Plato-User": "lab_org_alpha"},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    prefs = tmp_project_root / "users" / "lab_org_alpha" / "tooling_config.json"
    assert json.loads(prefs.read_text())["disabled_tools"] == ["search_literature"]

    lab = client.get("/api/v1/tooling", headers={"X-Plato-User": "lab_org_alpha"}).json()
    personal = client.get(
        "/api/v1/tooling", headers={"X-Plato-User": "user_scientist_a"}
    ).json()
    lab_tool = next(tool for tool in lab["tools"] if tool["id"] == "search_literature")
    personal_tool = next(
        tool for tool in personal["tools"] if tool["id"] == "search_literature"
    )
    assert lab_tool["enabled"] is False
    assert personal_tool["enabled"] is True


def test_unknown_tool_toggle_404s(client) -> None:
    resp = client.put("/api/v1/tooling/tools/not_real", json={"enabled": False})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "unknown_tool"


def test_custom_mcp_create_persists_without_echoing_auth(
    client, tmp_project_root: Path
) -> None:
    resp = client.post(
        "/api/v1/tooling/mcp/custom",
        json={
            "name": "Local docs",
            "transport": "stdio",
            "target": f"{sys.executable} -m plato.tools.mcp_server",
            "auth": "PLATO_TEST_TOKEN=secret",
            "enabled": False,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Local docs"
    assert body["enabled"] is False
    assert body["auth_configured"] is True
    assert "auth" not in body

    prefs = json.loads((tmp_project_root / "tooling_config.json").read_text())
    assert prefs["custom_mcp_servers"][0]["auth"] == "PLATO_TEST_TOKEN=secret"


def test_custom_mcp_test_uses_protocol_and_stores_tools(client, monkeypatch) -> None:
    async def fake_probe_mcp_server(server):
        assert server.transport == "stdio"
        return tooling.McpProbeResult(
            ok=True,
            status="ok",
            message="Connected and listed 1 MCP tool.",
            tools=["list_plato_tools"],
            latency_ms=1,
        )

    monkeypatch.setattr(tooling, "probe_mcp_server", fake_probe_mcp_server)
    created = client.post(
        "/api/v1/tooling/mcp/custom",
        json={
            "name": "Plato custom",
            "transport": "stdio",
            "target": "python -m plato.tools.mcp_server",
            "enabled": False,
        },
    )
    assert created.status_code == 201

    server_id = created.json()["id"]
    tested = client.post(f"/api/v1/tooling/mcp/{server_id}/test")
    assert tested.status_code == 200
    body = tested.json()
    assert body["status"] == "ok"
    assert "list_plato_tools" in body["tools"]

    state = client.get("/api/v1/tooling").json()
    custom = next(
        server for server in state["custom_mcp_servers"] if server["id"] == server_id
    )
    assert custom["status"] == "ok"
    assert custom["tool_count"] >= 1


def test_builtin_mcp_toggle_and_test(client, monkeypatch) -> None:
    async def fake_probe_mcp_server(server):
        return tooling.McpProbeResult(
            ok=True,
            status="ok",
            message="Connected and listed 2 MCP tools.",
            tools=["run_scientific_analysis", "genomics_tool_report"],
            latency_ms=1,
        )

    monkeypatch.setattr(tooling, "probe_mcp_server", fake_probe_mcp_server)
    disabled = client.put(
        "/api/v1/tooling/mcp/plato-tool-registry",
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["status"] == "inactive"

    enabled = client.put(
        "/api/v1/tooling/mcp/plato-tool-registry",
        json={"enabled": True},
    )
    assert enabled.status_code == 200
    body = enabled.json()
    assert body["enabled"] is True
    assert body["status"] == "ok"
    assert "run_scientific_analysis" in body["tools"]
    assert "genomics_tool_report" in body["tools"]
