"""Plato tool implementations consumed by agent nodes."""
from .registry import (
    Permission,
    Tool,
    ToolMetadata,
    call,
    get,
    list_tools,
    register,
)
from . import builtin  # noqa: F401  — side effect: registers built-in tools

__all__ = [
    "Tool",
    "ToolMetadata",
    "Permission",
    "register",
    "get",
    "list_tools",
    "call",
    "builtin",
]
