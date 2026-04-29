"""Helpers for trajectory tests: record node-call order and check sequences."""
from __future__ import annotations

import inspect
from typing import Any, Callable


class TrajectoryRecorder:
    """Records the order in which named functions are invoked.

    Wrap a node callable with ``recorder.wrap("node_name", fn)`` to get a
    drop-in replacement that appends ``"node_name"`` to ``recorder.calls``
    every time it's called and then delegates to the original. Sync and
    async functions are both supported; the wrapper preserves the
    coroutine-ness of the wrapped callable.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def wrap(self, name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(fn):
            async def aw(state, config):
                self.calls.append(name)
                return await fn(state, config)
            return aw

        def sw(state, config):
            self.calls.append(name)
            return fn(state, config)
        return sw


def ordered_substring(haystack: list[str], needle: list[str]) -> bool:
    """Return True if ``needle`` appears as a (non-contiguous) subsequence of
    ``haystack``.

    Examples:
        >>> ordered_substring(["a", "b", "c", "d"], ["b", "c"])
        True
        >>> ordered_substring(["a", "c", "b", "d"], ["b", "c"])
        False
        >>> ordered_substring(["a", "b"], ["b", "z"])
        False
    """
    it = iter(haystack)
    return all(any(item == n for item in it) for n in needle)
