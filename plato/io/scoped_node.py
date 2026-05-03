"""LangGraph-compatible scope decorator for langgraph_agents nodes.

LangGraph's ``add_node`` accepts a plain callable — there's no slot for
extra kwargs like ``scopes=``. The right pattern for retrofitting a
file-scope policy onto an existing graph is therefore a thin wrapper:
register ``scoped_node(idea_maker, IDEA_SCOPE)`` instead of
``idea_maker`` directly.

Inside the wrapped node, ``state["_writer"]`` is a ready-to-use
:class:`plato.io.ScopedWriter` rooted at ``state["files"]["Folder"]``.
The key is dropped from the partial-update copy of state we pass to the
underlying node, so downstream nodes never see a stale writer reference
in their checkpoint.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Union

from .scoped_writer import FileScope, ScopedWriter

NodeReturn = Union[dict, Awaitable[dict]]
NodeFn = Callable[..., NodeReturn]


def scoped_node(fn: NodeFn, scope: FileScope) -> NodeFn:
    """Wrap ``fn`` so it sees a ``ScopedWriter`` under ``state['_writer']``.

    Works for both sync and async LangGraph nodes — the wrapper
    matches the wrapped function's flavor so LangGraph's executor
    picks the right call path. The wrapper signature mirrors what
    LangGraph expects: ``(state, [config]) -> partial_state``.
    """
    if asyncio.iscoroutinefunction(fn):
        async def _async_wrapper(state: dict[str, Any], *args: Any, **kwargs: Any) -> dict:
            folder = state["files"]["Folder"]
            writer = ScopedWriter(folder, scope)
            # Copy state so we don't mutate the caller's dict — same
            # reason iter-5 made idea_maker return new dicts.
            scoped_state = {**state, "_writer": writer}
            return await fn(scoped_state, *args, **kwargs)

        _async_wrapper.__name__ = fn.__name__
        _async_wrapper.__qualname__ = fn.__qualname__
        _async_wrapper.__doc__ = fn.__doc__
        return _async_wrapper

    def _sync_wrapper(state: dict[str, Any], *args: Any, **kwargs: Any) -> dict:
        folder = state["files"]["Folder"]
        writer = ScopedWriter(folder, scope)
        scoped_state = {**state, "_writer": writer}
        return fn(scoped_state, *args, **kwargs)

    _sync_wrapper.__name__ = fn.__name__
    _sync_wrapper.__qualname__ = fn.__qualname__
    _sync_wrapper.__doc__ = fn.__doc__
    return _sync_wrapper


__all__ = ["scoped_node"]
