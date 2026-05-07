"""Tool and MCP configuration shared by the API and worker runtime."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .auth import auth_required, extract_user_id
from .settings import Settings

McpTransport = Literal["stdio", "http", "sse"]
McpStatus = Literal["untested", "ok", "error", "inactive"]

_CONFIG_FILENAME = "tooling_config.json"
_ENV_NAME_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
_CONFIG_LOCK = threading.RLock()


class ToolInfo(BaseModel):
    id: str
    name: str
    description: str
    category: str
    permissions: list[str]
    enabled: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class McpProbeResult(BaseModel):
    ok: bool
    status: McpStatus
    message: str
    tools: list[str] = Field(default_factory=list)
    latency_ms: int | None = None


class McpServerInfo(BaseModel):
    id: str
    name: str
    description: str
    transport: McpTransport
    target: str
    enabled: bool
    built_in: bool
    auth_configured: bool = False
    status: McpStatus = "untested"
    status_message: str | None = None
    tools: list[str] = Field(default_factory=list)
    tool_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    last_checked_at: str | None = None


class ToolingState(BaseModel):
    tools: list[ToolInfo]
    mcp_servers: list[McpServerInfo]
    custom_mcp_servers: list[McpServerInfo]


class _StoredMcpStatus(BaseModel):
    status: McpStatus = "untested"
    status_message: str | None = None
    tools: list[str] = Field(default_factory=list)
    last_checked_at: str | None = None


class _StoredCustomMcpServer(BaseModel):
    id: str
    name: str
    description: str = ""
    transport: McpTransport
    target: str
    auth: str = ""
    enabled: bool = False
    created_at: str
    updated_at: str
    status: McpStatus = "untested"
    status_message: str | None = None
    tools: list[str] = Field(default_factory=list)
    last_checked_at: str | None = None


class _ToolingPrefs(BaseModel):
    disabled_tools: list[str] = Field(default_factory=list)
    disabled_builtin_mcp_servers: list[str] = Field(default_factory=list)
    builtin_mcp_status: dict[str, _StoredMcpStatus] = Field(default_factory=dict)
    custom_mcp_servers: list[_StoredCustomMcpServer] = Field(default_factory=list)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_user_id(request) -> str | None:  # noqa: ANN001 - FastAPI Request at call sites
    user_id = extract_user_id(request)
    if user_id is None and auth_required():
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail={
                "code": "auth_required",
                "message": "Missing required header 'X-Plato-User'.",
            },
        )
    return user_id


def config_path(settings: Settings, user_id: str | None) -> Path:
    if user_id is None:
        return settings.project_root / _CONFIG_FILENAME
    return settings.project_root / "users" / user_id / _CONFIG_FILENAME


def read_prefs(path: Path) -> _ToolingPrefs:
    if not path.is_file():
        return _ToolingPrefs()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _ToolingPrefs()
    if not isinstance(payload, dict):
        return _ToolingPrefs()
    try:
        return _ToolingPrefs.model_validate(payload)
    except ValueError:
        return _ToolingPrefs()


def write_prefs(path: Path, prefs: _ToolingPrefs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(prefs.model_dump(mode="json"), indent=2), encoding="utf-8")
    os.replace(tmp, path)


def disabled_tool_names_for_project_dir(project_dir: Path, project_root: Path) -> list[str]:
    try:
        relative = project_dir.resolve().relative_to((project_root / "users").resolve())
    except ValueError:
        prefs_path = project_root / _CONFIG_FILENAME
    else:
        prefs_path = project_root / "users" / relative.parts[0] / _CONFIG_FILENAME
    return sorted(set(read_prefs(prefs_path).disabled_tools))


def builtin_mcp_servers() -> list[McpServerInfo]:
    return [
        McpServerInfo(
            id="plato-tool-registry",
            name="Plato Tool Registry",
            description=(
                "Local stdio MCP server exposing Plato's registered scientific tools "
                "and their schemas."
            ),
            transport="stdio",
            target=f"{shlex.quote(sys.executable)} -m plato.tools.mcp_server",
            enabled=True,
            built_in=True,
        )
    ]


def tooling_state(settings: Settings, user_id: str | None) -> ToolingState:
    from plato.tools import get, is_enabled, list_tools
    from plato.tools.registry import disabled_tools_context

    prefs = read_prefs(config_path(settings, user_id))
    disabled = set(prefs.disabled_tools)
    disabled_builtin_mcp = set(prefs.disabled_builtin_mcp_servers)
    with disabled_tools_context(disabled):
        tools = []
        for name in list_tools():
            tool = get(name)
            tools.append(
                ToolInfo(
                    id=name,
                    name=name,
                    description=tool.metadata.description,
                    category=tool.metadata.category,
                    permissions=sorted(tool.metadata.permissions),
                    enabled=is_enabled(name),
                    input_schema=tool.input_schema.model_json_schema(),
                    output_schema=tool.output_schema.model_json_schema(),
                )
            )

    mcp_servers = []
    for server in builtin_mcp_servers():
        status = prefs.builtin_mcp_status.get(server.id)
        mcp_servers.append(
            server.model_copy(
                update={
                    "enabled": server.id not in disabled_builtin_mcp,
                    "status": status.status if status else "untested",
                    "status_message": status.status_message if status else None,
                    "tools": status.tools if status else [],
                    "tool_count": len(status.tools) if status else 0,
                    "last_checked_at": status.last_checked_at if status else None,
                }
            )
        )

    custom = [_custom_to_info(server) for server in prefs.custom_mcp_servers]
    return ToolingState(tools=tools, mcp_servers=mcp_servers, custom_mcp_servers=custom)


def set_tool_enabled(settings: Settings, user_id: str | None, tool_id: str, enabled: bool) -> ToolInfo:
    from plato.tools import get

    try:
        get(tool_id)
    except KeyError as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_tool", "message": f"Unknown tool {tool_id!r}."},
        ) from exc

    with _CONFIG_LOCK:
        path = config_path(settings, user_id)
        prefs = read_prefs(path)
        disabled = set(prefs.disabled_tools)
        if enabled:
            disabled.discard(tool_id)
        else:
            disabled.add(tool_id)
        prefs.disabled_tools = sorted(disabled)
        write_prefs(path, prefs)
    return next(tool for tool in tooling_state(settings, user_id).tools if tool.id == tool_id)


def _custom_to_info(server: _StoredCustomMcpServer) -> McpServerInfo:
    return McpServerInfo(
        id=server.id,
        name=server.name,
        description=server.description,
        transport=server.transport,
        target=server.target,
        enabled=server.enabled,
        built_in=False,
        auth_configured=bool(server.auth.strip()),
        status=server.status,
        status_message=server.status_message,
        tools=server.tools,
        tool_count=len(server.tools),
        created_at=server.created_at,
        updated_at=server.updated_at,
        last_checked_at=server.last_checked_at,
    )


def _apply_probe(record: _StoredCustomMcpServer, result: McpProbeResult) -> None:
    record.status = result.status
    record.status_message = result.message
    record.tools = result.tools
    record.last_checked_at = utcnow_iso()
    record.updated_at = utcnow_iso()


def _apply_builtin_probe(prefs: _ToolingPrefs, server_id: str, result: McpProbeResult) -> None:
    prefs.builtin_mcp_status[server_id] = _StoredMcpStatus(
        status=result.status,
        status_message=result.message,
        tools=result.tools,
        last_checked_at=utcnow_iso(),
    )


def create_custom_mcp_server(
    settings: Settings,
    user_id: str | None,
    *,
    name: str,
    transport: McpTransport,
    target: str,
    description: str = "",
    auth: str = "",
    enabled: bool = False,
) -> McpServerInfo:
    validate_mcp_shape(transport, target, auth)
    now = utcnow_iso()
    record = _StoredCustomMcpServer(
        id=f"mcp-{uuid.uuid4()}",
        name=name.strip(),
        description=description.strip(),
        transport=transport,
        target=target.strip(),
        auth=auth.strip(),
        enabled=enabled,
        created_at=now,
        updated_at=now,
        status="inactive" if not enabled else "untested",
    )
    with _CONFIG_LOCK:
        path = config_path(settings, user_id)
        prefs = read_prefs(path)
        prefs.custom_mcp_servers.insert(0, record)
        write_prefs(path, prefs)
    return _custom_to_info(record)


def delete_custom_mcp_server(settings: Settings, user_id: str | None, server_id: str) -> None:
    with _CONFIG_LOCK:
        path = config_path(settings, user_id)
        prefs = read_prefs(path)
        remaining = [server for server in prefs.custom_mcp_servers if server.id != server_id]
        if len(remaining) == len(prefs.custom_mcp_servers):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail={"code": "unknown_mcp_server"})
        prefs.custom_mcp_servers = remaining
        write_prefs(path, prefs)


def update_custom_mcp_server(
    settings: Settings,
    user_id: str | None,
    server_id: str,
    *,
    name: str | None = None,
    transport: McpTransport | None = None,
    target: str | None = None,
    description: str | None = None,
    auth: str | None = None,
    enabled: bool | None = None,
) -> McpServerInfo:
    with _CONFIG_LOCK:
        path = config_path(settings, user_id)
        prefs = read_prefs(path)
        for server in prefs.custom_mcp_servers:
            if server.id != server_id:
                continue
            next_transport = transport or server.transport
            next_target = target.strip() if target is not None else server.target
            next_auth = auth.strip() if auth is not None else server.auth
            validate_mcp_shape(next_transport, next_target, next_auth)
            if name is not None:
                server.name = name.strip()
            if description is not None:
                server.description = description.strip()
            server.transport = next_transport
            server.target = next_target
            server.auth = next_auth
            if enabled is not None:
                server.enabled = enabled
                if not enabled:
                    server.status = "inactive"
                    server.status_message = "Server disabled by user."
            server.updated_at = utcnow_iso()
            write_prefs(path, prefs)
            return _custom_to_info(server)
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail={"code": "unknown_mcp_server"})


def set_mcp_enabled(
    settings: Settings,
    user_id: str | None,
    server_id: str,
    enabled: bool,
) -> McpServerInfo:
    with _CONFIG_LOCK:
        path = config_path(settings, user_id)
        prefs = read_prefs(path)
        builtin = {server.id: server for server in builtin_mcp_servers()}
        if server_id in builtin:
            disabled = set(prefs.disabled_builtin_mcp_servers)
            if enabled:
                disabled.discard(server_id)
            else:
                disabled.add(server_id)
                prefs.builtin_mcp_status[server_id] = _StoredMcpStatus(
                    status="inactive",
                    status_message="Server disabled by user.",
                    tools=[],
                    last_checked_at=utcnow_iso(),
                )
            prefs.disabled_builtin_mcp_servers = sorted(disabled)
            write_prefs(path, prefs)
            return next(server for server in tooling_state(settings, user_id).mcp_servers if server.id == server_id)
    return update_custom_mcp_server(settings, user_id, server_id, enabled=enabled)


def validate_mcp_shape(transport: McpTransport, target: str, auth: str = "") -> None:
    target = target.strip()
    if not target:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail={"code": "mcp_target_required"})
    if transport == "stdio":
        parts = _parse_stdio_target(target)
        if not parts:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail={"code": "invalid_stdio_command"})
    else:
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail={"code": "invalid_mcp_url"})
    try:
        _parse_auth(transport, auth)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_mcp_auth", "message": str(exc)},
        ) from exc


def _parse_stdio_target(target: str) -> list[str]:
    try:
        return shlex.split(target)
    except ValueError:
        return []


def _parse_auth(transport: McpTransport, auth: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in auth.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if transport == "stdio":
            if "=" not in line:
                raise ValueError("stdio environment entries must use KEY=value.")
            key, value = line.split("=", 1)
            key = key.strip()
            if not _ENV_NAME_RE.match(key):
                raise ValueError(f"Invalid environment variable name {key!r}.")
            values[key] = value.strip()
        else:
            if ":" in line:
                key, value = line.split(":", 1)
            elif "=" in line:
                key, value = line.split("=", 1)
            else:
                raise ValueError("HTTP/SSE auth entries must use Header: value or Header=value.")
            key = key.strip()
            if not key or any(char.isspace() for char in key):
                raise ValueError(f"Invalid header name {key!r}.")
            values[key] = value.strip()
    return values


async def probe_mcp_server(server: McpServerInfo | _StoredCustomMcpServer) -> McpProbeResult:
    started = datetime.now(timezone.utc)

    async def _probe() -> McpProbeResult:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.sse import sse_client
            from mcp.client.stdio import stdio_client
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:
            return McpProbeResult(
                ok=False,
                status="error",
                message=f"MCP SDK is not installed: {exc}",
            )

        if server.transport == "stdio":
            parts = _parse_stdio_target(server.target)
            if not parts:
                return McpProbeResult(ok=False, status="error", message="Invalid stdio command.")
            env = os.environ.copy()
            env.update(_parse_auth("stdio", getattr(server, "auth", "")))
            params = StdioServerParameters(command=parts[0], args=parts[1:], env=env)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=8)) as session:
                    await session.initialize()
                    tools = await session.list_tools()
        elif server.transport == "http":
            headers = _parse_auth("http", getattr(server, "auth", ""))
            async with streamablehttp_client(
                server.target,
                headers=headers or None,
                timeout=8,
                sse_read_timeout=8,
            ) as (read, write, _):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=8)) as session:
                    await session.initialize()
                    tools = await session.list_tools()
        else:
            headers = _parse_auth("sse", getattr(server, "auth", ""))
            async with sse_client(
                server.target,
                headers=headers or None,
                timeout=8,
                sse_read_timeout=8,
            ) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=8)) as session:
                    await session.initialize()
                    tools = await session.list_tools()

        tool_names = sorted(tool.name for tool in tools.tools)
        latency = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return McpProbeResult(
            ok=True,
            status="ok",
            message=f"Connected and listed {len(tool_names)} MCP tools.",
            tools=tool_names,
            latency_ms=latency,
        )

    try:
        return await asyncio.wait_for(_probe(), timeout=10)
    except Exception as exc:  # noqa: BLE001 - reported to the user
        latency = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return McpProbeResult(
            ok=False,
            status="error",
            message=f"{exc.__class__.__name__}: {exc}",
            latency_ms=latency,
        )


async def test_and_store_mcp_server(
    settings: Settings,
    user_id: str | None,
    server_id: str,
) -> McpServerInfo:
    path = config_path(settings, user_id)
    builtin = {server.id: server for server in builtin_mcp_servers()}
    if server_id in builtin:
        result = await probe_mcp_server(builtin[server_id])
        with _CONFIG_LOCK:
            prefs = read_prefs(path)
            _apply_builtin_probe(prefs, server_id, result)
            write_prefs(path, prefs)
        return next(server for server in tooling_state(settings, user_id).mcp_servers if server.id == server_id)

    with _CONFIG_LOCK:
        prefs = read_prefs(path)
        server_to_probe = next(
            (
                server.model_copy(deep=True)
                for server in prefs.custom_mcp_servers
                if server.id == server_id
            ),
            None,
        )
    if server_to_probe is not None:
        result = await probe_mcp_server(server_to_probe)
        with _CONFIG_LOCK:
            prefs = read_prefs(path)
            for server in prefs.custom_mcp_servers:
                if server.id == server_id:
                    _apply_probe(server, result)
                    write_prefs(path, prefs)
                    return _custom_to_info(server)

    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail={"code": "unknown_mcp_server"})
