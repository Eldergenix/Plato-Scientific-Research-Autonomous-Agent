# Observability

> R8. Optional Langfuse tracing for every Plato workflow + a manifest
> token-tracking handler that drains LLM usage into the run manifest's
> `tokens_in` / `tokens_out` / `cost_usd` fields.

## Quick start

Set the three env vars and Plato wires Langfuse in automatically:

```bash
export LANGFUSE_PUBLIC_KEY=pk_...
export LANGFUSE_SECRET_KEY=sk_...
export LANGFUSE_HOST=https://cloud.langfuse.com  # or your self-hosted instance
```

The dashboard `/keys` UI also accepts these values — they're stored
encrypted in `~/.plato/keys.json` and surface to the worker process
via the same KeyManager that handles the LLM-provider keys.

When the env (or in-app store) is unset, Plato runs unchanged with
no traces emitted. Install the optional dependency for tracing:

```bash
pip install "plato[obs]"
```

## What gets traced

Every workflow that goes through `_start_manifest` + `callbacks_for`:

- `get_idea_fast` (LangGraph idea/hater debate)
- `check_idea_semantic_scholar` (literature graph)
- `get_method_fast`
- `get_paper` (paper graph + reviewer panel + redraft loop)
- `referee`

Each invocation gets a unique `run_id` and the workflow name is
attached as Langfuse metadata. The same `run_id` is used as the
LangGraph `thread_id` (since iter 4) so resume-from-checkpoint
state and Langfuse traces co-locate by id.

## ManifestCallbackHandler

A second callback runs alongside Langfuse (or on its own when
Langfuse isn't configured). It listens to `on_llm_end` events,
extracts token usage from the provider response, and updates the
manifest's running totals:

```python
recorder.add_tokens(input_tokens=..., output_tokens=..., cost_usd=...)
```

Cost is computed against a small per-million-token price table for
the 9 models Plato wires today. Unknown models contribute zero
cost (token counts still tracked). The manifest lands at
`<project_dir>/runs/<run_id>/manifest.json` and is the canonical
source of cost data for the dashboard `/costs` page and the
autonomous loop's budget enforcement.

## Run-id correlation in the dashboard

The frontend sets `X-Plato-Run-Id` on every fetch issued during an
active run. The backend's middleware reads the header into the
`run_id_var` contextvar, and the centralised log formatter
(`%(run_id)s`) surfaces it on every log record — including those
emitted from worker threads spawned via `asyncio.to_thread`. Single
`run_id` flows from browser → backend → worker → LangChain.

## See also

- `plato/observability/__init__.py` — `get_langfuse_callback` +
  `callbacks_for` + `ManifestCallbackHandler`.
- `plato/logging_config.py` — `configure_logging` + `run_id_var`.
- ADR 0001 — LangGraph as default backend (defines the surface
  area Langfuse traces).
