"""Plato tool implementations consumed by agent nodes."""
from .registry import (
    Permission,
    Tool,
    ToolFn,
    ToolMetadata,
    call,
    get,
    is_async,
    list_tools,
    register,
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
    "call",
    "is_async",
    "builtin",
]
