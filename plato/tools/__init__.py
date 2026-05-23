"""Plato tool implementations consumed by agent nodes."""

from .registry import (
    Permission,
    Tool,
    ToolFn,
    ToolMetadata,
    call,
    disabled_tools_context,
    get,
    get_disabled_tools,
    is_async,
    is_enabled,
    list_tools,
    register,
    set_disabled_tools,
)
from . import builtin  # noqa: F401  — side effect: registers built-in tools

__all__ = [
    "Tool",
    "ToolFn",
    "ToolMetadata",
    "Permission",
    "register",
    "get",
    "list_tools",
    "set_disabled_tools",
    "get_disabled_tools",
    "disabled_tools_context",
    "is_enabled",
    "call",
    "is_async",
    "builtin",
]
