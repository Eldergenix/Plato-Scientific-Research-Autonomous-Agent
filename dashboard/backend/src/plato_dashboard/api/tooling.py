"""Tools and MCP server management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..settings import Settings, get_settings
from ..tooling import (
    McpServerInfo,
    McpTransport,
    ToolInfo,
    ToolingState,
    create_custom_mcp_server,
    delete_custom_mcp_server,
    resolve_user_id,
    set_mcp_enabled,
    set_tool_enabled,
    test_and_store_mcp_server,
    tooling_state,
    update_custom_mcp_server,
)

router = APIRouter()


class ToggleUpdate(BaseModel):
    enabled: bool


class CustomMcpCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    transport: McpTransport
    target: str = Field(min_length=1, max_length=1000)
    auth: str = Field(default="", max_length=4000)
    enabled: bool = False


class CustomMcpUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    transport: McpTransport | None = None
    target: str | None = Field(default=None, min_length=1, max_length=1000)
    auth: str | None = Field(default=None, max_length=4000)
    enabled: bool | None = None


@router.get("/tooling", response_model=ToolingState)
def get_tooling(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ToolingState:
    return tooling_state(settings, resolve_user_id(request))


@router.put("/tooling/tools/{tool_id}", response_model=ToolInfo)
def update_tool_enabled(
    tool_id: str,
    body: ToggleUpdate,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ToolInfo:
    return set_tool_enabled(settings, resolve_user_id(request), tool_id, body.enabled)


@router.put("/tooling/mcp/{server_id}", response_model=McpServerInfo)
async def update_mcp_enabled(
    server_id: str,
    body: ToggleUpdate,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> McpServerInfo:
    user_id = resolve_user_id(request)
    server = set_mcp_enabled(settings, user_id, server_id, body.enabled)
    if body.enabled:
        server = await test_and_store_mcp_server(settings, user_id, server_id)
    return server


@router.post("/tooling/mcp/{server_id}/test", response_model=McpServerInfo)
async def test_mcp_server(
    server_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> McpServerInfo:
    return await test_and_store_mcp_server(settings, resolve_user_id(request), server_id)


@router.post("/tooling/mcp/custom", response_model=McpServerInfo, status_code=201)
async def create_custom_mcp(
    body: CustomMcpCreate,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> McpServerInfo:
    user_id = resolve_user_id(request)
    server = create_custom_mcp_server(
        settings,
        user_id,
        name=body.name,
        description=body.description,
        transport=body.transport,
        target=body.target,
        auth=body.auth,
        enabled=body.enabled,
    )
    if body.enabled:
        server = await test_and_store_mcp_server(settings, user_id, server.id)
    return server


@router.patch("/tooling/mcp/custom/{server_id}", response_model=McpServerInfo)
async def update_custom_mcp(
    server_id: str,
    body: CustomMcpUpdate,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> McpServerInfo:
    user_id = resolve_user_id(request)
    server = update_custom_mcp_server(
        settings,
        user_id,
        server_id,
        name=body.name,
        description=body.description,
        transport=body.transport,
        target=body.target,
        auth=body.auth,
        enabled=body.enabled,
    )
    if body.enabled:
        server = await test_and_store_mcp_server(settings, user_id, server_id)
    return server


@router.delete("/tooling/mcp/custom/{server_id}", status_code=204)
def delete_custom_mcp(
    server_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    delete_custom_mcp_server(settings, resolve_user_id(request), server_id)
