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
import inspect
from typing import Any, Awaitable, Callable, Optional, Union, cast

from langchain_core.runnables import RunnableConfig

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
    accepts_config = _accepts_config(fn)

    if asyncio.iscoroutinefunction(fn):

        async def _async_wrapper(
            state: dict[str, Any],
            config: Optional[RunnableConfig] = None,
        ) -> dict:
            folder = state["files"]["Folder"]
            writer = ScopedWriter(folder, scope)
            # Copy state so we don't mutate the caller's dict — same
            # reason iter-5 made idea_maker return new dicts.
            scoped_state = {**state, "_writer": writer}
            if accepts_config:
                return cast(dict, await fn(scoped_state, config))
            return cast(dict, await fn(scoped_state))

        _async_wrapper.__name__ = fn.__name__
        _async_wrapper.__qualname__ = fn.__qualname__
        _async_wrapper.__doc__ = fn.__doc__
        return _async_wrapper

    def _sync_wrapper(
        state: dict[str, Any],
        config: Optional[RunnableConfig] = None,
    ) -> dict:
        folder = state["files"]["Folder"]
        writer = ScopedWriter(folder, scope)
        scoped_state = {**state, "_writer": writer}
        if accepts_config:
            return cast(dict, fn(scoped_state, config))
        return cast(dict, fn(scoped_state))

    _sync_wrapper.__name__ = fn.__name__
    _sync_wrapper.__qualname__ = fn.__qualname__
    _sync_wrapper.__doc__ = fn.__doc__
    return _sync_wrapper


def _accepts_config(fn: NodeFn) -> bool:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return True
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        }
    ]
    return (
        any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in positional)
        or len(positional) >= 2
    )


__all__ = ["scoped_node"]
