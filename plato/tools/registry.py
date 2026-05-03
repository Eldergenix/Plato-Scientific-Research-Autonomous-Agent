"""
Phase 5 — §5.4 typed tool registry with permission gates.

This is the cross-cutting tool registry. Anything an agent node might call —
search adapters, citation validators, claim extractors, future LLM helpers —
is registered as a :class:`Tool` with a typed input/output schema and an
explicit permission set. The registry is intentionally separate from
:mod:`plato.retrieval` (which only holds ``SourceAdapter`` instances): tools
are broader than retrieval and may declare side effects we want to gate
(``filesystem_write``, ``code_exec``, ``llm``).

The registry is process-global by design. Callers that need isolation in
tests should snapshot ``_REGISTRY``, clear it, and restore it (mirroring
the existing ``ADAPTER_REGISTRY`` test pattern).
"""
from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Literal, Union

from pydantic import BaseModel, ConfigDict


Permission = Literal[
    "network",
    "filesystem_read",
    "filesystem_write",
    "code_exec",
    "llm",
]
"""Effects a Tool can declare. Callers gate execution with ``allowed_permissions``."""


# A tool callable accepts a Pydantic ``BaseModel`` payload and returns
# either a ``BaseModel`` (sync tool) or a coroutine that awaits to a
# ``BaseModel`` (async tool). Async detection happens via
# :func:`is_async`. The Union is necessary because Python typing can't
# express "either sync or async" any more precisely.
ToolFn = Callable[[BaseModel], Union[BaseModel, Awaitable[BaseModel]]]
"""Type of the underlying callable a :class:`Tool` wraps."""


class ToolMetadata(BaseModel):
    """Static facts about a tool: identity, intent, side effects, taxonomy."""

    name: str
    description: str
    permissions: set[Permission]
    category: str = "generic"
    """One of ``"retrieval" | "validation" | "extraction" | "generic"`` (free-form)."""


class Tool(BaseModel):
    """A registered tool: metadata + typed schemas + sync-or-async callable."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    metadata: ToolMetadata
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    fn: ToolFn


_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool, *, overwrite: bool = False) -> Tool:
    """Register ``tool``. Raises ``ValueError`` on name collision unless ``overwrite``."""
    name = tool.metadata.name
    if not overwrite and name in _REGISTRY:
        raise ValueError(
            f"Tool {name!r} is already registered; pass overwrite=True to replace."
        )
    _REGISTRY[name] = tool
    return tool


def get(name: str) -> Tool:
    """Return the registered :class:`Tool` for ``name`` or raise ``KeyError``."""
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown tool {name!r}. Registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def list_tools(category: str | None = None) -> list[str]:
    """Return registered tool names, optionally filtered by ``category``."""
    if category is None:
        return sorted(_REGISTRY)
    return sorted(
        name
        for name, tool in _REGISTRY.items()
        if tool.metadata.category == category
    )


def call(
    name: str,
    payload: BaseModel,
    *,
    allowed_permissions: set[Permission] | None = None,
) -> Any:
    """Invoke the registered tool ``name`` with a typed ``payload``.

    Parameters
    ----------
    name:
        Registered tool name.
    payload:
        Pydantic model whose type must match ``tool.input_schema``. Callers
        are expected to construct the typed payload themselves; we re-validate
        defensively to catch ``BaseModel`` subclasses that don't match.
    allowed_permissions:
        If provided, the tool's declared ``permissions`` must be a subset.
        Otherwise we raise :class:`PermissionError` *before* invoking ``fn``.
        ``None`` disables the gate (use only for trusted internal callers).

    Returns
    -------
    The raw result of ``fn``. For async tools this is the coroutine — the
    caller awaits it. We do not auto-schedule: agent nodes already run on an
    event loop and double-scheduling would be wrong.
    """
    tool = get(name)

    if allowed_permissions is not None:
        missing = tool.metadata.permissions - allowed_permissions
        if missing:
            raise PermissionError(
                f"Tool {name!r} requires permissions {sorted(missing)} "
                f"not in allowed_permissions {sorted(allowed_permissions)}."
            )

    if not isinstance(payload, tool.input_schema):
        # Re-validate via the declared schema. This covers cases where a
        # caller hands us a BaseModel of a different class but with the
        # right shape.
        payload = tool.input_schema.model_validate(payload.model_dump())

    return tool.fn(payload)


def is_async(name: str) -> bool:
    """Return True iff the registered tool ``name`` is an async coroutine.

    Callers that need to know whether to ``await`` the result of
    :func:`call` should consult this first. Cheaper than ``inspect`` at
    every call site and resilient to wrapping (we look through
    ``functools.partial`` etc.).
    """
    fn = get(name).fn
    while hasattr(fn, "func") and not inspect.iscoroutinefunction(fn):
        # functools.partial / wrapt-style proxies: drill in.
        fn = fn.func
    return inspect.iscoroutinefunction(fn)


__all__ = [
    "Permission",
    "ToolFn",
    "ToolMetadata",
    "Tool",
    "register",
    "get",
    "list_tools",
    "call",
    "is_async",
]
