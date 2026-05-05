# SSE Events

> Every event the dashboard backend emits to the per-run channel
> `run:{run_id}`. Consumers (the Next.js frontend, integration tests,
> any third-party tooling) should switch on the `kind` discriminant.

The FastAPI server exposes the channel at:

```
GET /api/v1/projects/{pid}/runs/{run_id}/events
```

…as a `text/event-stream`. Events are JSON objects, one per SSE
`data:` line. The full TypeScript discriminated union lives at
`dashboard/frontend/src/lib/api.ts` (`RunEvent`).

All events carry, by default:

| Field | Type | Notes |
|---|---|---|
| `kind` | string | The discriminant. |
| `ts` | string \| number | ISO-8601 timestamp emitted by the worker. |
| `run_id` | string | Set by the bus republisher when missing on the source event. |
| `project_id` | string | Same. |
| `stage` | string | Same. |

Per-event payload fields below are documented in addition to those.

---

## Lifecycle

### `stage.started`

Emitted once, by the child subprocess, just after it opens its event
writer and before any work begins.

| Field | Type | Notes |
|---|---|---|
| `stage` | StageId | `"data" \| "idea" \| "method" \| "results" \| "paper" \| "referee" \| "literature"` |
| `config` | object | The launch config the worker received (mode, models, extras). |

The parent supervisor flips `Run.status` from `"queued"` to
`"running"` when this event lands.

Frontend handler: `RunEventStageStarted` in `api.ts`; `useProject`
treats it as the trigger for the run-detail panel to leave its
"queued" placeholder.

### `stage.heartbeat`

Emitted by `LogTailer._publish_line` when it parses a step / attempt
counter out of a cmbagent log line.

| Field | Type | Notes |
|---|---|---|
| `step` | int (optional) | Current step number. |
| `total_steps` | int (optional) | Total steps in this run. |
| `attempt` | int (optional) | Current attempt within a step. |
| `total_attempts` | int (optional) | Configured cap. |

Either `(step, total_steps)` or `(attempt, total_attempts)` is set
per event, never both. Frontend handler: `RunEventStageHeartbeat`;
the `RunMonitor` progress bar reads this to render `4 / 6 steps`.

### `stage.finished`

Emitted exactly once per run. Sources:
- The child subprocess on normal exit (`succeeded` / `cancelled` /
  `failed`).
- The parent supervisor's synthesis path when the child died without
  publishing a `stage.finished` of its own (segfault, OOM, hard
  crash). The supervisor emits an `error` event first in that case.
- The supervisor's `CancelledError` branch when a cancel arrives
  mid-run.

| Field | Type | Notes |
|---|---|---|
| `status` | string | `"succeeded" \| "failed" \| "cancelled"`. |

Frontend handler: `RunEventStageFinished`; closes out the per-run
SSE subscription and triggers the post-run reconciliation pass.

---

## Agent

### `node.entered`

Emitted by `langgraph_bridge.py` for every LangGraph node in
`AGENT_NODE_NAMES` (`idea_maker`, `idea_hater`, `methods_node`,
`paper_node`, etc.) when its `on_chain_start` event fires.

| Field | Type | Notes |
|---|---|---|
| `name` | string | Node name from `AGENT_NODE_NAMES`. |
| `stage` | StageId | The owning stage. |

Frontend handler: `RunEventNodeEntered`; `useProject` collects them
into a ring-buffered `nodeEvents` list that powers `AgentSwimlane`.

### `node.exited`

Emitted by `langgraph_bridge.py` on the matching `on_chain_end`.

| Field | Type | Notes |
|---|---|---|
| `name` | string | Same as the entered event. |
| `stage` | StageId | Same. |
| `duration_ms` | int (optional) | Milliseconds the node spent active. |

Frontend handler: `RunEventNodeExited`.

### `tokens.delta`

Emitted by `langgraph_bridge.py` on every `on_chat_model_end` whose
response carries usage info, and by the child subprocess via the
manifest callback.

| Field | Type | Notes |
|---|---|---|
| `model` | string | Provider model name (e.g. `gpt-4o`, `claude-sonnet-4`). |
| `prompt` | int | Input tokens. |
| `completion` | int | Output tokens. |

Frontend handler: `RunEventTokensDelta`. The supervisor also folds
the deltas into `Run.token_input` / `Run.token_output` and forwards
them to `token_tracker.record_tokens_delta` for the cross-project
ledger.

---

## Code

### `code.execute`

Emitted once per executor cell after `Plato.get_results` returns.
The child subprocess reads `plato.executor_artifacts["cells"]` and
fans the list out as one event per cell. There are no separate
`started` / `line` / `exit` sub-kinds — the executor protocol
doesn't currently carry an event-emitter callback, so the cells
arrive as a post-stage burst.

| Field | Type | Notes |
|---|---|---|
| `index` | int (optional) | Zero-based cell index. |
| `source` | string (optional) | Python source the executor evaluated. |
| `stdout` | string \| null | Captured stdout. |
| `stderr` | string \| null | Captured stderr. |
| `executor` | string \| null | `cmbagent \| local_jupyter \| modal \| e2b`. |
| `error` | object \| null | `{ ename, evalue }` when the cell raised. |

Frontend handler: `RunEventCodeExecute`; the `ResultsStage` CodePane
groups events by `index` and renders source + stdout + error inline.

---

## Plot

### `plot.created`

Emitted by the parent supervisor's post-stage diff. The supervisor
snapshots `input_files/plots/` before the paper subprocess launches,
then diffs the live directory against the snapshot after
`stage.finished` and publishes one event per new file. Currently
scoped to the paper stage (the only stage whose `plots_node` writes
new plots).

| Field | Type | Notes |
|---|---|---|
| `name` | string | Filename (e.g. `comparison_loss.png`). |
| `path` | string | Project-relative path: `input_files/plots/<name>`. |
| `url` | string | Stitched API URL: `/api/v1/projects/{pid}/files/{path}`. |

Frontend handler: `RunEventPlotCreated`; pushes the file into the
`PlotGrid`'s live list without waiting for a `/plots` refetch.

---

## Error

### `error`

Emitted whenever the child catches an unhandled exception, fails to
import Plato, or hits a setup-time error. The supervisor also
synthesizes one when the child dies without emitting a
`stage.finished` of its own.

| Field | Type | Notes |
|---|---|---|
| `message` | string | The exception's `str(exc)` or a synthesized cause. |
| `traceback` | string (optional) | `traceback.format_exc()` from the child. |

Frontend handler: `RunEventError`; surfaces a banner in the run
detail panel with the message and a collapsible traceback section.

---

## Render

The four `render.qd.*` events come from `_post_paper_render`, the
detached task the supervisor spawns after a successful paper run.
The render task runs *outside* the per-project lock so the run is
reported "completed" before Quarkdown's headless-chrome PDF
pipeline (10–30s) starts.

### `render.qd.started`

Fired once, before the render orchestrator runs. Carries no payload
past the default ids. Frontend handler: `RunEventRenderQdStarted`.

### `render.qd.completed`

Fired once on render success (including the soft-fail case where one
or more doctype subprocesses exited non-zero — the success
discriminant is the absence of an unhandled exception, not an
all-zero return code map).

| Field | Type | Notes |
|---|---|---|
| `artifacts` | object | Map keyed by `paged \| plain \| docs \| slides`. |
| `artifacts[doctype].html` | string \| null | Project-relative path to the rendered HTML. |
| `artifacts[doctype].pdf` | string \| null | Project-relative path to the PDF. |
| `artifacts[doctype].returncode` | int | Quarkdown CLI exit code (0 = ok). |
| `stderr` | object (optional) | Per-doctype stderr capture (truncated to 8KB) for any doctype with `returncode != 0`. |

Frontend handler: `RunEventRenderQdCompleted`; the run detail panel
reads `artifacts` to surface "Open PDF" / "Open slides" buttons.

### `render.qd.skipped`

Fired when `paper_md` was empty or whitespace-only — the renderer
would otherwise emit a stub HTML containing only header directives.

| Field | Type | Notes |
|---|---|---|
| `reason` | string | Currently `"paper_md is empty"`. |

### `render.qd.failed`

Fired only when the orchestrator itself raised — e.g. missing
`quarkdown` binary, FS permission errors. Per-doctype subprocess
failures land in `render.qd.completed` with non-zero `returncode`,
not here.

| Field | Type | Notes |
|---|---|---|
| `error` | string | `str(exc)` from the orchestrator. |

Frontend handler: `RunEventRenderQdFailed`.

---

## Log

### `log.line`

Emitted from three sources, all with the same payload shape:
1. The child subprocess's `_LogStream` shim, which converts every
   `print` call inside Plato into an event.
2. `langgraph_bridge.py` for buffered chat-model output and tool
   call markers (`▶ tool: ...`, `✓ tool → ...`).
3. `LogTailer` for cmbagent log files watched on disk.

| Field | Type | Notes |
|---|---|---|
| `source` | string | Origin tag — usually the stage id. |
| `agent` | string \| null | Detected agent name (parsed from line prefixes), `"tool"`, or `null`. |
| `level` | string | `"info" \| "warn" \| "error" \| "tool"`. |
| `text` | string | The log content, with the trailing newline stripped. |

Frontend handler: `RunEventLogLine`; rendered into `AgentLogStream`
with the level driving the color and the agent driving the gutter
label.

---

## Versioning

Adding a new event kind is non-breaking by design: the frontend's
`RunEvent` union ends in `RunEventUnknown` (`{ kind: string;
[key: string]: unknown }`) so unknown discriminants fall through
without crashing. Adding fields to an existing event is also
non-breaking. Removing or renaming either a kind or a field is a
breaking change — bump it in this doc and the corresponding `api.ts`
type.
