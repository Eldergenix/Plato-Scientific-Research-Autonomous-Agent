"""LangGraph ``astream_events`` bridge → dashboard EventBus.

This module wraps a compiled LangGraph runnable's ``astream_events(version='v2')``
stream and republishes each event onto an :class:`EventBus` channel of the form
``f"run:{run_id}"`` using the dashboard's flat event shape. The dashboard UI
already knows how to render these kinds:

    - ``node.entered`` / ``node.exited``  → progress dots / spinner
    - ``log.line``                         → streamed log panel
    - ``tokens.delta``                     → token meter
    - ``error``                            → red banner

Final state strategy
--------------------
``astream_events`` does NOT return the final graph state (the async iterator
just yields events and ends). Two viable approaches:

    1. Capture the final ``on_chain_end`` event whose ``name`` is the graph's
       top-level name (``"LangGraph"`` for ``StateGraph.compile()`` outputs).
       Its ``data.output`` is the final state dict.
    2. Run ``await graph.ainvoke(state, ...)`` separately.

We use approach (1) because re-invoking would double the LLM cost. We capture
the *outermost* ``on_chain_end`` (the last one whose ``parent_ids`` is empty
or whose ``run_id`` matches the first ``on_chain_start`` we saw). If, for any
reason, no such event was captured, we fall back to ``ainvoke``.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..events.bus import EventBus
from ..domain.models import StageId


_DEFAULT_RUN_TIMEOUT_S = 30 * 60  # 30 minutes


def _run_timeout_seconds() -> float:
    """Read PLATO_RUN_TIMEOUT_SECONDS or fall back to 30 minutes."""
    raw = os.environ.get("PLATO_RUN_TIMEOUT_SECONDS")
    if not raw:
        return float(_DEFAULT_RUN_TIMEOUT_S)
    try:
        val = float(raw)
    except ValueError:
        return float(_DEFAULT_RUN_TIMEOUT_S)
    return val if val > 0 else float(_DEFAULT_RUN_TIMEOUT_S)


# Names of LangGraph nodes we surface to the dashboard. Anything else (the
# implicit synthetic ``__start__`` / ``__end__`` chains, conditional edge
# routers, etc.) is filtered out — UI noise.
AGENT_NODE_NAMES: frozenset[str] = frozenset(
    {
        # langgraph_agents (idea / methods / referee / literature)
        "idea_maker",
        "idea_hater",
        "maker",          # alias for idea_maker registered in agents_graph
        "hater",          # alias for idea_hater
        "methods",
        "novelty",
        "semantic_scholar",
        "literature_summary",
        "referee",
        "preprocess_node",
        # paper_agents
        "keywords_node",
        "abstract_node",
        "introduction_node",
        "methods_node",
        "results_node",
        "conclusions_node",
        "plots_node",
        "refine_results",
        "citations_node",
    }
)

_TOOL_OUTPUT_TRUNCATE = 500


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _summarize(value: Any, limit: int = _TOOL_OUTPUT_TRUNCATE) -> str:
    """Stringify ``value`` and truncate, preserving a tail marker."""
    text = "" if value is None else str(value)
    text = text.replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _extract_chunk_text(chunk: Any) -> str:
    """Pull the text content out of an ``on_chat_model_stream`` chunk.

    LangChain v0.2+ wraps deltas as ``AIMessageChunk`` with ``.content``
    that may be a plain string or a list of ``{type, text}`` parts.
    """
    if chunk is None:
        return ""
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                txt = part.get("text") or part.get("content")
                if isinstance(txt, str):
                    parts.append(txt)
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(content)


def _extract_usage(event_data: dict) -> Optional[dict]:
    """Try several known keys for usage metadata. Returns ``None`` if absent."""
    output = event_data.get("output")
    candidates: list[Any] = [event_data.get("usage_metadata"), output]
    for cand in candidates:
        if cand is None:
            continue
        usage = getattr(cand, "usage_metadata", None)
        if isinstance(usage, dict):
            return usage
        if isinstance(cand, dict) and isinstance(cand.get("usage_metadata"), dict):
            return cand["usage_metadata"]
    return None


def _extract_model_name(event: dict) -> str:
    """Best-effort model name from chat_model events."""
    metadata = event.get("metadata") or {}
    for key in ("ls_model_name", "model_name", "ls_model_type"):
        v = metadata.get(key)
        if isinstance(v, str) and v:
            return v
    name = event.get("name")
    return name if isinstance(name, str) else "unknown"


async def stream_graph(
    graph: Any,
    state: Any,
    run_id: str,
    stage: StageId,
    bus: EventBus,
) -> Any:
    """Stream a LangGraph ``graph`` and publish dashboard events to ``bus``.

    Parameters
    ----------
    graph
        Compiled LangGraph runnable (output of ``builder.compile()``).
    state
        Initial graph state (the same dict you'd pass to ``graph.invoke``).
    run_id
        The dashboard run identifier; events are published to channel
        ``f"run:{run_id}"``.
    stage
        The dashboard stage id (``"idea"``, ``"method"``, ``"paper"``, …).
        Surfaced as the ``source`` field on log lines and ``stage`` on node
        events so the UI can colorize per stage.
    bus
        The shared :class:`EventBus` instance.

    Returns
    -------
    Any
        The final graph state dict (whatever the topmost ``on_chain_end``
        produced as ``data.output``). Falls back to ``await graph.ainvoke``
        if no such event was observed.
    """

    channel = f"run:{run_id}"

    # node_name → start_time for duration tracking.
    node_start: dict[str, float] = {}

    # run_id → buffered streaming text for chat_model events (a single graph
    # run can spawn many parallel LLM calls, so we key by the LangGraph
    # event ``run_id`` not by node name).
    chat_buffers: dict[str, list[str]] = {}
    chat_node_for: dict[str, str] = {}      # event run_id → enclosing node name
    chat_model_for: dict[str, str] = {}     # event run_id → model name

    # Track which node we're currently inside (top of the stack), so chunks
    # from nested LLM calls get attributed correctly.
    node_stack: list[str] = []

    # Top-level graph end event capture.
    final_state: Any = None
    top_run_id: Optional[str] = None

    async def _publish(event: dict) -> None:
        event.setdefault("ts", _utc_now_iso())
        event.setdefault("run_id", run_id)
        await bus.publish(channel, event)

    async def _drain() -> None:
        nonlocal final_state, top_run_id
        async for ev in graph.astream_events(state, version="v2"):
            etype = ev.get("event")
            name = ev.get("name") or ""
            ev_run_id = ev.get("run_id") or ""
            data = ev.get("data") or {}

            # ─── Top-level graph boundary capture ───────────────────────────
            if etype == "on_chain_start" and top_run_id is None and not (ev.get("parent_ids") or []):
                top_run_id = ev_run_id

            if etype == "on_chain_end" and ev_run_id == top_run_id:
                # The outermost graph completion — capture its output as final state.
                final_state = data.get("output", final_state)

            # ─── Agent node lifecycle ───────────────────────────────────────
            if name in AGENT_NODE_NAMES:
                if etype == "on_chain_start":
                    node_start[ev_run_id] = time.monotonic()
                    node_stack.append(name)
                    await _publish(
                        {
                            "kind": "node.entered",
                            "name": name,
                            "stage": stage,
                        }
                    )
                elif etype == "on_chain_end":
                    started = node_start.pop(ev_run_id, None)
                    duration_ms = (
                        int((time.monotonic() - started) * 1000)
                        if started is not None
                        else None
                    )
                    if node_stack and node_stack[-1] == name:
                        node_stack.pop()
                    await _publish(
                        {
                            "kind": "node.exited",
                            "name": name,
                            "stage": stage,
                            "duration_ms": duration_ms,
                        }
                    )

            # ─── Chat-model streaming → buffered log line ───────────────────
            elif etype == "on_chat_model_start":
                chat_buffers[ev_run_id] = []
                chat_node_for[ev_run_id] = node_stack[-1] if node_stack else "llm"
                chat_model_for[ev_run_id] = _extract_model_name(ev)

            elif etype == "on_chat_model_stream":
                chunk = data.get("chunk")
                text = _extract_chunk_text(chunk)
                if text:
                    chat_buffers.setdefault(ev_run_id, []).append(text)

            elif etype == "on_chat_model_end":
                buf = chat_buffers.pop(ev_run_id, [])
                agent = chat_node_for.pop(ev_run_id, "llm")
                model = chat_model_for.pop(ev_run_id, _extract_model_name(ev))
                full_text = "".join(buf).strip()
                if full_text:
                    await _publish(
                        {
                            "kind": "log.line",
                            "source": stage,
                            "agent": agent,
                            "level": "info",
                            "text": full_text,
                        }
                    )
                # Token usage, if present.
                usage = _extract_usage(data)
                if usage:
                    await _publish(
                        {
                            "kind": "tokens.delta",
                            "model": model,
                            "prompt": int(usage.get("input_tokens", 0) or 0),
                            "completion": int(usage.get("output_tokens", 0) or 0),
                        }
                    )

            # ─── Tool call lifecycle ────────────────────────────────────────
            elif etype == "on_tool_start":
                tool_input = data.get("input")
                await _publish(
                    {
                        "kind": "log.line",
                        "source": stage,
                        "agent": "tool",
                        "level": "tool",
                        "text": f"▶ {name}: {_summarize(tool_input)}",
                    }
                )

            elif etype == "on_tool_end":
                tool_output = data.get("output")
                await _publish(
                    {
                        "kind": "log.line",
                        "source": stage,
                        "agent": "tool",
                        "level": "tool",
                        "text": f"✓ {name} → {_summarize(tool_output)}",
                    }
                )

    timeout_s = _run_timeout_seconds()
    try:
        await asyncio.wait_for(_drain(), timeout=timeout_s)
    except asyncio.TimeoutError as exc:
        msg = (
            f"LangGraph stream exceeded PLATO_RUN_TIMEOUT_SECONDS="
            f"{timeout_s:.0f}s and was aborted"
        )
        await _publish({"kind": "error", "stage": stage, "message": msg})
        raise TimeoutError(msg) from exc
    except asyncio.CancelledError:
        # Cooperative cancellation — let the worker decide whether to publish.
        raise
    except Exception as exc:  # noqa: BLE001 — re-raised after publish.
        await _publish(
            {
                "kind": "error",
                "stage": stage,
                "message": str(exc),
            }
        )
        raise

    # Fallback: if we somehow never saw the topmost on_chain_end, fall back
    # to ainvoke. This is rare but keeps the contract honest.
    if final_state is None:
        try:
            final_state = await graph.ainvoke(state)
        except Exception as exc:  # noqa: BLE001
            await _publish(
                {
                    "kind": "error",
                    "stage": stage,
                    "message": f"final-state fallback failed: {exc}",
                }
            )
            raise

    return final_state


async def stream_invoke_sync_graph(
    graph: Any,
    state: Any,
    run_id: str,
    stage: StageId,
    bus: EventBus,
) -> Any:
    """Convenience wrapper for graphs whose canonical entry is sync ``invoke``.

    LangGraph's ``astream_events`` works on both sync and async graphs, so
    this is the same as :func:`stream_graph` — it exists as a named seam so
    callers from sync stages (``get_idea``, ``referee``) can document intent
    at the call site.
    """
    return await stream_graph(graph, state, run_id, stage, bus)


# ──────────────────────────────────────────────────────────────────────────────
# Self-test: build a tiny LangGraph with two nodes and verify the bridge
# publishes the expected event shapes. Run with:
#
#     python -m plato_dashboard.worker.langgraph_bridge
#
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio as _asyncio
    import json as _json
    from typing import TypedDict

    from langchain_core.runnables import RunnableLambda
    from langgraph.graph import StateGraph, START, END

    class _S(TypedDict, total=False):
        x: int
        log: list[str]

    # We register node names matching AGENT_NODE_NAMES so the bridge surfaces
    # them as node.entered / node.exited.
    def _idea_maker(s: _S) -> _S:
        return {"x": s.get("x", 0) + 1, "log": [*(s.get("log", [])), "maker"]}

    def _methods(s: _S) -> _S:
        return {"x": s.get("x", 0) * 10, "log": [*(s.get("log", [])), "methods"]}

    builder = StateGraph(_S)
    builder.add_node("idea_maker", RunnableLambda(_idea_maker))
    builder.add_node("methods", RunnableLambda(_methods))
    builder.add_edge(START, "idea_maker")
    builder.add_edge("idea_maker", "methods")
    builder.add_edge("methods", END)
    test_graph = builder.compile()

    async def _main() -> None:
        bus = EventBus()

        captured: list[dict] = []

        async def _consumer() -> None:
            async for ev in bus.subscribe("run:test-1"):
                captured.append(ev)
                if ev.get("kind") == "node.exited" and ev.get("name") == "methods":
                    return

        consumer_task = _asyncio.create_task(_consumer())
        # Yield once so the subscriber is registered before we publish.
        await _asyncio.sleep(0)

        final = await stream_graph(
            test_graph,
            {"x": 1, "log": []},
            run_id="test-1",
            stage="idea",
            bus=bus,
        )

        try:
            await _asyncio.wait_for(consumer_task, timeout=2.0)
        except _asyncio.TimeoutError:
            consumer_task.cancel()

        print("=== final state ===")
        print(_json.dumps(final, default=str, indent=2))
        print("=== events ===")
        for ev in captured:
            print(_json.dumps(ev, default=str))

        kinds = [e.get("kind") for e in captured]
        names = [(e.get("kind"), e.get("name")) for e in captured]
        assert ("node.entered", "idea_maker") in names, names
        assert ("node.entered", "methods") in names, names
        assert ("node.exited", "idea_maker") in names, names
        assert ("node.exited", "methods") in names, names
        assert "error" not in kinds, kinds
        print("\nOK: bridge emitted node.entered/exited for both nodes.")

    _asyncio.run(_main())
