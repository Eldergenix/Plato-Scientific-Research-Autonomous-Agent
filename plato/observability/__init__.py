"""
Optional Langfuse tracing for Plato workflows + manifest token tracking.

If ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are set in the
environment (and ``langfuse`` is installed), :func:`get_langfuse_callback`
returns a LangChain ``BaseCallbackHandler`` suitable for passing as
``config={"callbacks": [...]}`` to a LangGraph invocation.

When a :class:`~plato.state.manifest.ManifestRecorder` is also passed,
:func:`callbacks_for` appends a :class:`ManifestCallbackHandler` so every
``on_llm_end`` event drains its token usage into the recorder — this is
how the manifest's ``tokens_in`` / ``tokens_out`` / ``cost_usd`` fields
get populated.

Install the optional Langfuse dependency with::

    pip install "plato[obs]"
"""
from __future__ import annotations

import os
import warnings
from typing import TYPE_CHECKING, Any

from .manifest_callback import ManifestCallbackHandler

if TYPE_CHECKING:
    from ..state.manifest import ManifestRecorder


def get_langfuse_callback(
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """Build a Langfuse callback handler if Langfuse is configured.

    Returns ``None`` (a no-op for the caller) if either the env vars are
    missing or the optional ``langfuse`` dependency is not installed.
    """
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        return None

    try:
        from langfuse.callback import CallbackHandler
    except ImportError:
        warnings.warn(
            "LANGFUSE_* env vars are set but langfuse is not installed. "
            "Run `pip install langfuse` to enable tracing.",
            RuntimeWarning,
            stacklevel=2,
        )
        return None

    return CallbackHandler(
        session_id=session_id,
        user_id=user_id,
        metadata=metadata or {},
    )


def callbacks_for(
    run_id: str,
    workflow: str,
    recorder: "ManifestRecorder | None" = None,
) -> list[Any]:
    """Helper that returns callback handlers for use in LangGraph configs.

    Always appends a :class:`ManifestCallbackHandler` when *recorder* is
    supplied (so token counts land in the manifest). Appends the LangFuse
    handler too when Langfuse is configured.
    """
    handlers: list[Any] = []
    cb = get_langfuse_callback(session_id=run_id, metadata={"workflow": workflow})
    if cb is not None:
        handlers.append(cb)
    if recorder is not None:
        handlers.append(ManifestCallbackHandler(recorder))
    return handlers


__all__ = ["get_langfuse_callback", "callbacks_for", "ManifestCallbackHandler"]
