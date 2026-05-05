# Architecture

> Snapshot of the Plato system after Wave 5. Cross-references real
> code paths and points at the ADRs / feature docs that own each
> sub-surface.

## 1. System overview

Plato is a multi-agent scientific research assistant: a Python core
(LangGraph state machines + a domain registry + an executor protocol)
plus a FastAPI dashboard (Next.js frontend, subprocess-supervised
runs, SSE event stream) plus a post-paper Quarkdown render pipeline.
The core writes into a per-project directory; the dashboard wraps
that directory with an HTTP/SSE API and a tenant model.

```
                ┌─────────────────────────────────┐
                │   Next.js frontend (dashboard)  │
                │   src/app, src/components,      │
                │   src/lib/api.ts (RunEvent)     │
                └───────────────┬─────────────────┘
                                │ REST + SSE (text/event-stream)
                ┌───────────────▼─────────────────┐
                │   FastAPI gateway               │
                │   plato_dashboard/api/server.py │
                │   middleware: CSRF, RequestId,  │
                │     BodySize, CORS              │
                └───┬───────────┬───────────────┬─┘
                    │           │               │
        starts run  │   reads   │   subscribes  │
                    ▼           ▼               ▼
             ┌─────────────┐ ┌──────────┐ ┌─────────┐
             │ run_manager │ │ Project  │ │ Event   │
             │ (subprocess │ │  store   │ │  bus    │
             │ supervisor) │ │ FS-backed│ │ (asyncio│
             └──────┬──────┘ └────┬─────┘ │  Queue) │
                    │             │       └────▲────┘
            spawns  │   reads/    │            │
                    │   writes    │            │ publishes
                    ▼             ▼            │
             ┌─────────────────────────────────┴───┐
             │  worker subprocess (`_child_main`)  │
             │  imports plato + langgraph_agents / │
             │  paper_agents, runs the graph,      │
             │  writes events.jsonl + status.json  │
             └─────────────────────┬───────────────┘
                                   │ writes artifacts
                                   ▼
             ┌─────────────────────────────────────┐
             │  ~/.plato/[users/<uid>/]<pid>/      │
             │   meta.json · input_files/*         │
             │   paper/main.pdf · paper/quarkdown/ │
             │   runs/<rid>/events.jsonl,status    │
             └─────────────────────┬───────────────┘
                                   │ post-stage hook
                                   ▼
             ┌─────────────────────────────────────┐
             │  render/pipeline.render_all_artifacts
             │  → quarkdown CLI → paged|slides|    │
             │     docs|plain (HTML + PDF)         │
             └─────────────────────────────────────┘
```

## 2. Component map

**Plato core (`plato/`).** The library that does the science. Two
LangGraph state machines (`langgraph_agents/agents_graph.py` for the
idea/method/literature/referee flow; `paper_agents/agents_graph.py`
for the paper-writing flow), a `DomainProfile` registry
(`plato/domain/__init__.py`), a sandbox-shaped `Executor` Protocol
(`plato/executor/__init__.py`), a checkpointer factory
(`plato/state/checkpointer.py`) and the legacy `Plato` facade
(`plato/plato.py`). Stays sync; the dashboard adapts around it.

**Paper agents (`plato/paper_agents/`).** A dedicated graph for
paper drafting: section nodes, a citation-validation pipeline, a
claim/evidence matrix, a multi-reviewer panel with revision loop,
and as of Wave 3 a final `slide_outline_node` that produces
`paper/slide_outline.md`. State schema in `parameters.py`.

**Dashboard backend (`dashboard/backend/src/plato_dashboard/`).**
FastAPI app (`api/server.py` ≈ 1.4k LOC) plus subrouters, an
in-memory event bus (`events/bus.py`), a subprocess supervisor
(`worker/run_manager.py`), a filesystem project store
(`storage/project_store.py`), the encrypted key store
(`storage/key_store.py`), the proxy-trusting auth shim (`auth.py`),
ASGI middleware (CSRF, request-id, body-size), Prometheus metrics
(`observability/metrics.py`), and the Quarkdown render pipeline
(`render/{pipeline,quarkdown,transformer}.py`).

**Dashboard frontend (`dashboard/frontend/`).** Next.js 15 + React
19 + Tailwind v4. SSE client + REST wrapper in `src/lib/api.ts`
(`RunEvent` discriminated union). Linear-style stage list, agent
swimlane, plot grid, paper preview, results stage with code pane.
Pages: `/`, `/projects`, `/models`, `/costs`, `/activity`, `/keys`.

**Render pipeline (`dashboard/backend/.../render/`).** Post-paper
hook that fans the published Markdown into four parallel Quarkdown
doctypes (paged, slides, docs, plain). Each doctype is a
sub-process call to the `quarkdown` CLI under
`asyncio.create_subprocess_exec` with an argv list. Outputs
land under `<project>/paper/quarkdown/<doctype>/`. Detailed in
[`features/quarkdown.md`](features/quarkdown.md).

## 3. Run lifecycle

```
User              FastAPI                run_manager       worker subprocess        EventBus       Frontend SSE
 │                   │                        │                  │                     │              │
 │ POST /runs        │                        │                  │                     │              │
 ├──────────────────▶│                        │                  │                     │              │
 │                   │ start_run(...)         │                  │                     │              │
 │                   ├───────────────────────▶│                  │                     │              │
 │                   │                        │ Process(target=  │                     │              │
 │                   │                        │   _child_main)   │                     │              │
 │                   │                        ├─────────────────▶│                     │              │
 │                   │                        │                  │ stage.started       │              │
 │                   │                        │                  ├────▶ events.jsonl   │              │
 │ ◀── 202 Run ──────┤                        │ _supervise()     │                     │              │
 │                   │                        │ + _tail_events() │                     │              │
 │                   │                        │ (reads jsonl,    │                     │              │
 │                   │                        │  publishes)      │                     │              │
 │                   │                        ├────────────────────────────────────────▶│              │
 │ GET /runs/{id}/events (text/event-stream)   │                  │                     │              │
 ├──────────────────▶│                        │                  │                     │              │
 │                   │ bus.subscribe          │                  │                     │              │
 │                   ├────────────────────────────────────────────────────────────────▶│              │
 │                   │                        │                  │ node.entered/...    │              │
 │                   │                        │                  ├────▶ events.jsonl   │              │
 │                   │                        ├────────────────────────────────────────▶│              │
 │ ◀── data: {...}   │                        │                  │                     │              │
 │ ◀── data: {...}   │                        │                  │ stage.finished      │              │
 │                   │                        │                  ├────▶ events.jsonl   │              │
 │                   │                        │ _post_paper_     │                     │              │
 │                   │                        │  render() (paper │                     │              │
 │                   │                        │  stage only)     │                     │              │
 │                   │                        │ render.qd.* events                     │              │
 │                   │                        ├────────────────────────────────────────▶│              │
 │ ◀── data: {...}   │                        │                  │                     │              │
```

The supervisor holds a per-project lock (`_project_locks`) so two
concurrent runs against the same `pid` never share an
`events.jsonl`; the API maps the lock-conflict to HTTP 409. The
post-paper render runs *outside* the lock so the run reports
"completed" before Quarkdown's headless-chrome PDF pipeline starts.

## 4. LangGraph orchestration

### Idea graph — `plato/langgraph_agents/agents_graph.py`

Nodes: `preprocess_node`, `research_question_clarifier`, `maker`
(`idea_maker`), `hater` (`idea_hater`), `methods` (`methods_fast`),
`novelty` (`novelty_decider`), `semantic_scholar`,
`literature_summary`, `counter_evidence_search`, `gap_detector`,
`referee`. Every file-writing node is wrapped in `scoped_node` so a
ScopedWriter rejects out-of-scope writes at runtime.

```
START → preprocess_node ─task_router─┬─▶ research_question_clarifier ─clarifier_router─┬─▶ maker ─router─▶ hater ─▶ maker (loop)
                                     │                                                  └─▶ END
                                     ├─▶ methods ─▶ END
                                     ├─▶ novelty ─literature_router─▶ semantic_scholar ─▶ novelty (loop)
                                     │                                                   └─▶ literature_summary ─▶ counter_evidence_search ─▶ gap_detector ─▶ END
                                     └─▶ referee ─▶ END
```

### Paper graph — `plato/paper_agents/agents_graph.py`

Nodes: `preprocess_node`, `keywords_node`, `abstract_node`,
`introduction_node`, `methods_node`, `results_node`,
`conclusions_node`, `plots_node`, `refine_results`, `citations_node`,
`citation_validator_node`, `claim_evidence_fanout`,
`claim_extractor`, `evidence_matrix_node`, `reviewer_panel_fanout`,
`methodology_reviewer`, `statistics_reviewer`, `novelty_reviewer`,
`writing_reviewer`, `critique_aggregator`, `redraft_node`, and the
**Wave 3 addition `slide_outline_node`**.

```
START → preprocess_node → keywords_node → abstract_node → introduction_node
      → methods_node → results_node → conclusions_node → plots_node
      → refine_results ─citation_router─┬─▶ citations_node → citation_validator_node ─┐
                                        └────────────────────────────────▶            │
                                          claim_evidence_fanout ◀───────────────────  │
                                          → claim_extractor → evidence_matrix_node
                                          → reviewer_panel_fanout
                                            ├─ methodology_reviewer ─┐
                                            ├─ statistics_reviewer  ─┤
                                            ├─ novelty_reviewer     ─┼─▶ critique_aggregator ─revision_router─┐
                                            └─ writing_reviewer     ─┘                                        │
                                                                       redraft_node ◀──────────── (loop) ─────┤
                                                                                                              │
                                                                       slide_outline_node ◀── (revision done) ┘
                                                                            └─▶ END
```

The reviewer panel runs the four reviewer nodes in parallel from
the fan-out hub; LangGraph waits for all four to finish before the
aggregator runs (fan-in semantics). When `revision_router` decides
the loop is done, control routes to `slide_outline_node` rather
than directly to `END`, so every successful paper run produces a
Markdown slide outline as a precondition for the Quarkdown slide
deck.

## 5. State schema

The two `parameters.py` files are the canonical truth — referenced
TypedDicts here, not duplicated. `Project` and `Run` are dashboard
shapes (`dashboard/backend/.../domain/models.py`).

**`plato/langgraph_agents/parameters.py:GraphState`** — `messages`,
`idea` (`IDEA`), `tokens`, `llm`, `files` (`FILES`), `keys`
(`KeyManager`), `data_description`, `task`, `literature`
(`LITERATURE`), `referee` (`REFEREE`), `clarifying_questions`,
`needs_clarification`, `counter_evidence_sources`, `gaps`.

**`plato/paper_agents/parameters.py:GraphState`** — `messages`,
`files` (`FILES`), `idea`, `paper` (`PAPER`, includes
`slide_outline: str`), `tokens`, `llm`, `latex`, `keys`, `time`,
`writer`, `params`, `critiques`, `critique_digest`,
`revision_state` (`REVISION_STATE`), `run_id`, `sources`,
`references`, `validation_report`, `store`, `claims`,
`evidence_links`, `unsupported_claim_rate`.

**Project** (`dashboard/backend/.../domain/models.py:Project`) —
opaque `id` (matches `[A-Za-z0-9_-]{1,64}`), `name`, `user_id`
(optional, set in multi-tenant mode), per-stage `Stage` blocks
with status / journal entries.

**Run** (`dashboard/backend/.../domain/models.py:Run`) — `id`,
`project_id`, `stage`, `mode`, `config`, `status` (`queued` |
`running` | `succeeded` | `failed` | `cancelled`), `pid`, token
counters, started/finished timestamps. Persisted to
`runs/<rid>/status.json`.

## 6. Storage layout

```
<project_root>/
├── (legacy single-user) <pid>/...            ← when auth not required
└── users/
    └── <uid>/
        └── <pid>/
            ├── meta.json                     # dashboard-only project meta
            ├── input_files/
            │   ├── data_description.md
            │   ├── idea.md · methods.md · results.md
            │   ├── literature.md · referee.md
            │   ├── plots/
            │   └── .history/<stage>_<ts>.md
            ├── paper/
            │   ├── main.pdf · main.tex · references.bib
            │   ├── slide_outline.md          # Wave 3
            │   └── quarkdown/
            │       ├── paged/{paper.qd, paper.html, paper.pdf}
            │       ├── slides/{slides.qd, slides.html, slides.pdf}
            │       ├── docs/{paper.qd, paper.html, paper.pdf}
            │       └── plain/{paper.qd, paper.html, paper.pdf}
            ├── idea_generation_output/        # cmbagent logs
            ├── method_generation_output/
            ├── experiment_generation_output/
            └── runs/<rid>/
                ├── events.jsonl              # source of truth for SSE
                ├── status.json               # heartbeat for the API
                └── manifest.json             # carries user_id for tenant guard
```

`<project_root>` is `~/.plato/projects/` by default. Project IDs
match `[A-Za-z0-9_-]{1,64}`; user IDs match the same pattern with
`.` allowed. Both bounds are enforced at the API edge before any
filesystem call.

## 7. Quarkdown render pipeline

When a paper-stage run reaches `stage.finished` with
`status="succeeded"`, the supervisor spawns `_post_paper_render`
*outside* the per-project lock. The pipeline reads
`<project>/paper/paper.md` (falling back to
`input_files/results.md`) and `<project>/paper/slide_outline.md`,
emits four `.qd` files via `render/transformer.py`, and runs the
Quarkdown CLI in parallel under
`asyncio.create_subprocess_exec` with an argv list (never a shell
string). Each doctype produces an HTML and (when headless-chrome
succeeds) a PDF.

Notification: the channel sees `render.qd.started` once,
`render.qd.completed` with the `artifacts` map keyed by doctype,
and `render.qd.skipped` / `render.qd.failed` for the orchestrator-
level failure modes. Per-doctype failures are reported inside the
`completed` event's `returncode` / `stderr` map, not via
`render.qd.failed`. Full payloads in
[`features/quarkdown.md`](features/quarkdown.md) and
[`features/sse-events.md`](features/sse-events.md#render).

## 8. SSE event taxonomy

Channel: `run:{run_id}`. Endpoint:
`GET /api/v1/projects/{pid}/runs/{run_id}/events` as
`text/event-stream`. The frontend's `RunEvent` discriminated
union ends in `RunEventUnknown`, so unknown discriminants degrade
gracefully — additive changes are non-breaking by design.

| Kind | Source |
|---|---|
| `stage.started` | child subprocess, once per run |
| `stage.heartbeat` | `LogTailer` parsing cmbagent step / attempt counters |
| `stage.finished` | child or supervisor (synthesised on hard crash / cancel) |
| `node.entered` | langgraph_bridge `on_chain_start` for `AGENT_NODE_NAMES` |
| `node.exited` | langgraph_bridge `on_chain_end` |
| `tokens.delta` | langgraph_bridge `on_chat_model_end` + manifest callback |
| `code.execute` | child subprocess fanning `Plato.executor_artifacts["cells"]` |
| `plot.created` | supervisor's post-stage diff against the plot snapshot |
| `error` | child catches an exception, or supervisor synthesises one |
| `render.qd.started` | `_post_paper_render`, once |
| `render.qd.completed` | `_post_paper_render` on success (incl. soft-fail) |
| `render.qd.skipped` | `paper_md` empty/whitespace-only |
| `render.qd.failed` | render orchestrator raised |
| `log.line` | `_LogStream` shim, langgraph_bridge buffered output, `LogTailer` |

Every event carries `kind`, `ts`, `run_id`, `project_id`, and
`stage` by default — the bus republisher backfills any IDs the
worker omitted. Per-payload schemas:
[`features/sse-events.md`](features/sse-events.md).

## 9. Multi-tenancy

Driven by `PLATO_DASHBOARD_AUTH_REQUIRED=1` and the `X-Plato-User`
header (ADR 0004). When the env var is set, every request must
carry the header; missing or invalid values short-circuit to 401.
When unset, the dashboard runs in legacy single-user mode and
writes to the un-namespaced `<project_root>/<pid>/` tree.

`extract_user_id` (`auth.py`) validates the value against
`[A-Za-z0-9._-]{1,64}` with no leading/trailing dot, so a user id
is safe to splice into a filesystem path. `_resolve_project_root`
in `api/server.py` returns `<project_root>/users/<user_id>/` when
the id is present; the project store, key store, run manifests,
and per-user keys all hang off that namespace.

`_enforce_project_tenant` and `_enforce_run_tenant` (in
`api/server.py`) are the cross-tenant guards. They cross-check the
project's `user_id` (from `meta.json`) and the run's `user_id`
(from `runs/<rid>/manifest.json`) against the requester's id and
return 403 (required-mode) or 404 (not-required-mode + header
present) on a mismatch — fail-closed, no leaking existence.

## 10. Security model

- **CSRF (Wave 5).** `middleware/csrf.py` is a pure-ASGI
  double-submit-cookie middleware. Every state-mutating request
  (POST/PUT/PATCH/DELETE) needs an `X-CSRF-Token` header that
  matches the readable `plato_csrf` cookie; safe methods
  (GET/HEAD/OPTIONS/TRACE) and exempt paths skip the check but
  still get a token minted on the way out.
- **CSP (Wave 3).** `GET /projects/{pid}/files/{relpath}`
  attaches `Content-Security-Policy` and `X-Frame-Options:
  SAMEORIGIN` when serving HTML, plus `X-Content-Type-Options:
  nosniff` and `Referrer-Policy: no-referrer` for every type.
  The CSP locks `default-src 'self'` and forbids form actions —
  attacker-authored Quarkdown HTML can't exfiltrate parent-window
  data through an iframe.
- **Tenant scoping (Wave 4).** ADR 0004 +
  `_enforce_project_tenant` / `_enforce_run_tenant` (see
  §"Multi-tenancy"). The directory layout already isolates
  `<base>/users/<uid>/<pid>/`; the explicit guards close the
  bypass where an endpoint resolved `project_dir` directly from
  `settings.project_root` instead of `_get_store`.
- **Path-traversal hardening.** `get_file` resolves both
  `project_dir` and `target` and uses `Path.relative_to(root)`
  (rejecting `ValueError` with 403 `path_traversal_blocked`)
  rather than the path-prefix-collision-vulnerable
  `str.startswith` check.
- **Body-size cap.** `BodySizeLimitMiddleware` rejects requests
  with `Content-Length > 10 MiB` (HTTP 413) before the JSON
  parser allocates.
- **Project / user id charsets.** Both validated against tight
  regexes at the API edge so neither can carry `/` or `..` into
  a filesystem path.

## 11. Observability

- **Metrics.** `GET /api/v1/metrics` returns the Prometheus
  scrape (`observability/metrics.py`): `plato_active_runs`,
  `plato_run_completion_total{status,stage}`,
  `plato_run_duration_seconds{stage}`, `plato_sse_subscribers`,
  `plato_error_total{source,kind}`,
  `plato_render_duration_seconds{doctype}`,
  `plato_http_request_seconds{method,path,status}`,
  `plato_dashboard` build info.
- **JSON logs.** `PLATO_OBS_JSON_LOGS=1` flips
  `init_observability` to the JSON formatter
  (`observability/logging.py`); existing single-user installs
  default to text logs at the level set by the framework
  configurator.
- **Request IDs (Wave 5).** `RequestIdMiddleware` reads or mints
  `X-Request-ID`, echoes it back on the response, and stashes it
  in a `ContextVar` (`get_request_id`) so log records and
  exception handlers can correlate.
- **Sentry (optional).** `_init_sentry_if_configured` wires
  `sentry_sdk` when `SENTRY_DSN` is set and the SDK is on the
  path. The SDK is **not** in `pyproject.toml` — operators who
  want it install it themselves.

## 12. ADR inventory

| # | Title | TL;DR |
|---|---|---|
| [0001](adr/0001-langgraph-as-default-backend.md) | LangGraph as the default backend | LangGraph is canonical for idea/method/literature/referee/paper; cmbagent retained only for `get_results` / `get_keywords`. |
| [0002](adr/0002-postgres-checkpointer.md) | Postgres checkpointer | SQLite stays default; Postgres is opt-in via `make_checkpointer("postgres", dsn=...)`; the extra is loaded lazily and not in `pyproject.toml`. |
| [0003](adr/0003-domain-profile-pluggability.md) | Domain profile pluggability | `DomainProfile` registry plus per-capability registries (`SourceAdapter`, `Executor`, `JournalPreset`, etc.); astro is the default. |
| [0004](adr/0004-x-plato-user-multi-tenancy.md) | X-Plato-User multi-tenancy | Dashboard is proxy-trusting; `X-Plato-User` is the trust anchor; `_enforce_run_tenant` cross-checks the run manifest. |
| [0005](adr/0005-sandboxed-executor-protocol.md) | Sandboxed Executor protocol | Executor is a `@runtime_checkable Protocol` with one async `run()`; cmbagent is the only implemented backend; modal/e2b/local_jupyter are stubs. |

**Gaps to flag.** No ADR yet for the Quarkdown integration (Wave
3) — the AGPL-via-subprocess decision and the four-doctype
artifact schema live only in `features/quarkdown.md`. Worth
promoting to an ADR (e.g. 0006) so the licensing rationale and
the post-paper-stage hook contract have a stable anchor.

## 13. Deployment topology

- **Single-container (default for the public demo).** One
  container that runs `plato-dashboard-api` and serves the
  Next.js static export from FastAPI's `StaticFiles` mount. Disk
  is local; SQLite checkpointer; no Redis. See
  `dashboard/spaces/Dockerfile` for the reference image — also
  used by `railway.json` for the one-click Railway deploy. The
  Quarkdown CLI is installed in the same image's build stage.
- **Multi-container (self-hosted lab).** Backend + frontend +
  Postgres (when picking the durable checkpointer per ADR 0002).
  `docker/docker-compose.test.yml` covers the Postgres CI shape;
  a production compose would add a reverse proxy that injects
  `X-Plato-User` per ADR 0004. Frontend can also be deployed as
  a separate Next.js host pointing at the FastAPI domain.
- **Kubernetes.** The graceful-shutdown path (`_lifespan`'s
  finally branch flips `_shutting_down=True` so `/health` 503s,
  then cancels supervisor tasks) is K8s-aware: a liveness/
  readiness probe that follows `/api/v1/health` will drain the
  pod before SIGKILL. Pair with Postgres + an object store for
  `<project_root>` (the local-disk path won't survive a pod
  reschedule). The reverse proxy (Cloudflare Access,
  oauth2-proxy, traefik-forward-auth) handles SSO and stamps
  `X-Plato-User`.
