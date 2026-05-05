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
import re
import warnings
from typing import TYPE_CHECKING, Any

from .manifest_callback import ManifestCallbackHandler

if TYPE_CHECKING:
    from ..state.manifest import ManifestRecorder


# Secret-shaped patterns we never want leaving the process via tracing
# payloads. We match the canonical prefixes for the four LLM providers we
# call (OpenAI/Anthropic/Google/Perplexity) plus generic Bearer tokens. The
# replacement is a fixed-length placeholder so partial-string equality
# checks downstream don't accidentally skip the redaction.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),                # OpenAI / many vendors
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),            # Anthropic
    re.compile(r"AIza[0-9A-Za-z_-]{16,}"),               # Google API keys
    re.compile(r"pplx-[A-Za-z0-9_-]{16,}"),              # Perplexity
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}", re.I),  # generic bearer tokens
]
_REDACTED = "<REDACTED-SECRET>"

# Metadata keys we never trace through. Conservative match: any key whose
# lowercase form contains one of these substrings is dropped before the
# Langfuse handler sees it.
_DROP_METADATA_KEYS = (
    "authorization", "auth", "api_key", "apikey", "secret",
    "password", "token", "private_key",
)


def _scrub_str(value: str) -> str:
    out = value
    for pat in _SECRET_PATTERNS:
        out = pat.sub(_REDACTED, out)
    return out


def _scrub(value: Any) -> Any:
    """Recursively redact secrets from str/list/dict payloads.

    Returns a new structure; the input is never mutated. Non-str/list/dict
    types are passed through unchanged.
    """
    if isinstance(value, str):
        return _scrub_str(value)
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and any(
                drop in k.lower() for drop in _DROP_METADATA_KEYS
            ):
                out[k] = _REDACTED
                continue
            out[k] = _scrub(v)
        return out
    return value


def get_langfuse_callback(
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """Build a Langfuse callback handler if Langfuse is configured.

    Returns ``None`` (a no-op for the caller) if either the env vars are
    missing or the optional ``langfuse`` dependency is not installed.

    The handler is wrapped so any prompt/completion payload that flows
    through ``on_llm_start`` / ``on_llm_end`` is run through a secret
    scrubber before it reaches the network. Operators who want stronger
    guarantees should also configure Langfuse's own data-masking rules
    server-side; this layer is a defense-in-depth client-side filter.
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

    base = CallbackHandler(
        session_id=session_id,
        user_id=user_id,
        metadata=_scrub(metadata or {}),
    )
    return _RedactingCallbackHandler(base)


class _RedactingCallbackHandler:
    """Thin proxy around a Langfuse CallbackHandler that scrubs payloads.

    LangChain's callback dispatch calls ``handler.on_<event>(...)`` with
    keyword args including ``prompts``, ``messages``, ``response``, etc.
    We intercept those, run them through the secret scrubber, and forward.

    Any attribute we don't intercept (e.g. ``handler.flush``) falls through
    via __getattr__ so the upstream API surface is preserved.
    """

    _INTERCEPTED_EVENTS = {
        "on_llm_start", "on_chat_model_start", "on_llm_new_token",
        "on_llm_end", "on_llm_error",
        "on_chain_start", "on_chain_end", "on_chain_error",
        "on_tool_start", "on_tool_end", "on_tool_error",
        "on_text", "on_agent_action", "on_agent_finish",
    }

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name in self._INTERCEPTED_EVENTS and callable(attr):
            def _scrubbed(*args: Any, **kwargs: Any) -> Any:
                args = tuple(_scrub(a) for a in args)
                kwargs = {k: _scrub(v) for k, v in kwargs.items()}
                return attr(*args, **kwargs)
            return _scrubbed
        return attr


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
