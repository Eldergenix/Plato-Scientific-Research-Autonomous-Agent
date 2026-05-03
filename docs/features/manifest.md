# Reproducibility Manifest

> R9. Every Plato workflow emits `manifest.json` capturing the inputs
> needed to re-run the same workflow against the same prompts and
> get the same answer (modulo LLM nondeterminism).

## What gets recorded

```python
class RunManifest(BaseModel):
    run_id: str               # uuid; also the LangGraph thread_id
    workflow: str             # "get_idea_fast" | "get_paper" | ...
    domain: str | None        # active DomainProfile name
    user_id: str | None       # X-Plato-User caller (multi-tenant)
    started_at: datetime
    ended_at: datetime | None
    status: Literal["running", "success", "error"]
    error: str | None
    git_sha: str | None       # git rev-parse HEAD at start
    project_sha: str          # sha256 of project_dir contents
    models: dict[str, str]    # role → model name
    source_ids: list[str]     # ids referenced during the run
    tokens_in: int            # populated by ManifestCallbackHandler
    tokens_out: int
    cost_usd: float
    prompt_hashes: dict[str, str]  # node_name → sha256(rendered_prompt)
    seeds: dict[str, int]
    extra: dict               # workflow-specific bag
```

Persisted to `<project_dir>/runs/<run_id>/manifest.json` via
`ManifestRecorder` (`plato/state/manifest.py`).

## Lifecycle

1. `Plato._start_manifest(workflow, models=..., extra=...)` opens
   the recorder. The manifest is written to disk immediately with
   `status="running"`, so a process kill mid-run leaves a row that
   tells the dashboard "this one didn't finish."
2. The recorder is threaded through the LangGraph state as
   `state["recorder"]` (since iter 7) so any node can call
   `recorder.add_tokens(...)` or `recorder.update(prompt_hashes={...})`.
3. `recorder.finish("success" | "error", error=...)` writes the
   final timestamp + status atomically (temp + rename, like the
   storage layer's atomic writes).

## Token + cost wiring

`ManifestCallbackHandler` (R8) listens to `on_llm_end` events from
LangChain and forwards token counts into the recorder:

```python
recorder.add_tokens(input_tokens=..., output_tokens=..., cost_usd=...)
```

Cost is a per-million-token-price table for the 9 models Plato
wires; unknown models contribute zero. The handler is wired into
every workflow's `callbacks_for(...)` call so every LLM call lands
in the manifest.

## Prompt hashes (iter 15)

`LLM_call_stream` records `sha256(rendered_prompt)` into the
recorder when a recorder is in scope and a `node_name` is supplied.
This makes "did the prompt drift between runs?" a 30-second diff
instead of a manual prompt-by-prompt walk.

## Dashboard view

`/runs/[runId]` renders the manifest via `ManifestPanel`. Token /
cost / model / source-id sections are surfaced as separate cards.
The git sha is hyperlinked to the GitHub commit when a remote URL
is configured.

## Auditing

The on-disk manifests are the canonical record for cost
reconciliation, debugging "why did this run pick that source?",
and CI eval-harness aggregation (every nightly task's manifest is
read into `evals/results/<task_id>/metrics.json`).

## See also

- `plato/state/manifest.py` — `RunManifest` + `ManifestRecorder`
- `plato/observability/manifest_callback.py` — token-tracking
  callback
- `dashboard/frontend/src/components/manifest/manifest-panel.tsx`
