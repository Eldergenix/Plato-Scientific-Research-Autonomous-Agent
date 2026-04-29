"""
Optional Langfuse tracing for Plato workflows.

If ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are set in the
environment (and ``langfuse`` is installed), :func:`get_langfuse_callback`
returns a LangChain ``BaseCallbackHandler`` suitable for passing as
``config={"callbacks": [...]}`` to a LangGraph invocation. When keys are
missing or the package isn't installed, it returns ``None`` and Plato
runs unchanged.

Install the optional dependency with::

    pip install "plato[obs]"
"""
from __future__ import annotations

import os
import warnings
from typing import Any


def get_langfuse_callback(
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """
    Build a Langfuse callback handler if Langfuse is configured.

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


def callbacks_for(run_id: str, workflow: str) -> list[Any]:
    """Helper that returns ``[handler]`` or ``[]`` for use in LangGraph configs."""
    cb = get_langfuse_callback(session_id=run_id, metadata={"workflow": workflow})
    return [cb] if cb is not None else []


__all__ = ["get_langfuse_callback", "callbacks_for"]
