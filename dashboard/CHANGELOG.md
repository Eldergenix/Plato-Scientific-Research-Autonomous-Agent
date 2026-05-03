# Changelog

All notable changes to the Plato Dashboard are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Real-time markdown editing with collaborative cursors in the stage detail
  panel (currently read-only with auto-snapshot on save).
- Sandboxed `Executor` implementations (Modal / e2b / local-jupyter) with
  real out-of-process isolation; the protocols and stubs already ship.
- Public deployment artifacts: a turn-key Vercel template plus a curated
  HuggingFace Space pinned to a fixed Plato release tag.

## [0.2.0] - 2026-05-02

Phase 5 — production hardening — plus the 13 frontend feature streams that
ship the Phase 2 / 3 / 5 backend work to the dashboard. ADRs 0002–0005
document the design choices behind this release.

### Added

- **Multi-tenant dashboard** via the `X-Plato-User` header. When
  `PLATO_DASHBOARD_AUTH_REQUIRED=1`, every project, key store, run
  manifest, evidence-matrix, and validation-report read is scoped to
  the requester's user id (`auth.py:extract_user_id`,
  `_resolve_project_root`, `_enforce_run_tenant`). 15 adversarial
  bypass tests in `tests/safety/test_dashboard_auth_bypass.py`.
  See ADR 0004.
- **Header-value validation** (`auth.py:_USER_ID_RE`) rejects user
  ids that don't match `[A-Za-z0-9._-]{1,64}` so the value can be
  used directly as a path segment without traversal risk.
- **Pluggable Executor protocol** (`plato/executor/__init__.py`) with
  four registered backends — `cmbagent` (default), `local_jupyter`,
  `modal`, `e2b`. The latter three are stubs today; the protocol is
  the long-term answer to the in-process code-execution gap that
  `SECURITY.md` calls out. See ADR 0005.
- **DomainProfile registry** (`plato/domain/__init__.py`) bundles
  retrieval sources / keyword extractor / journal presets / executor
  / novelty corpus into a single resolved object. Astro is the
  default; `biology` is registered out-of-the-box. See ADR 0003.
- **Multi-source retrieval** with six adapters (`arxiv`, `openalex`,
  `ads`, `crossref`, `pubmed`, `semantic_scholar`), an orchestrator
  with DOI/arxiv-id dedup, and a middleware stack covering rate-limit
  backoff, ETag caching, and per-host circuit breaking.
- **Citation validation** (`plato/tools/citation_validator.py`)
  resolves DOIs against Crossref, checks Retraction Watch (when a
  CSV is supplied), and verifies arXiv-only refs. Wired as a paper
  graph node; emits `validation_report.json` with
  `validation_rate`, `passed`, `unverified_count`, and
  per-reference `failures`.
- **Claim → Evidence Matrix** (`plato/state/models.py` + the
  `claim_extractor` and `evidence_matrix_node` graph nodes) writes
  an `evidence_matrix.jsonl` sidecar per run.
- **Reviewer panel + revision loop (R6)** — four parallel reviewer
  axes (methodology / statistics / novelty / writing) feed a
  critique aggregator that drives a redraft loop bounded by
  `max_revision_iters` (now exposed via `Plato.get_paper(...)`).
- **Autonomous research loop (R10)** — `plato loop` CLI runs
  iteratively under a wall-clock + cost budget, scoring each
  iteration via a composite acceptance score, committing wins to a
  `plato-runs/<timestamp>` branch, and discarding regressions with
  `git reset --hard HEAD`. Per-iteration TSV log.
- **Reproducibility manifest (R9)** — every workflow entry point
  emits `manifest.json` with run id, git sha, project sha-256, model
  versions, source ids, tokens, and cost.
- **Langfuse observability (R8)** integration. Set the three
  `LANGFUSE_*` env vars (or store them in the dashboard `/keys` UI)
  to opt in. Callbacks are wired into every LangGraph invocation.
- **Scoped writers (R11)** for the `abstract`, `methods`, and
  `conclusions` paper nodes — each declares its own write-scope and
  raises `ScopeError` on out-of-scope writes.
- **Sanitization layer (R12)** — every retrieved abstract is wrapped
  in `<external>...</external>` markers and scanned for injection
  signals before entering the prompt. FutureHouse responses now
  receive the same treatment.
- **13 frontend feature streams** (F1–F13):
  - F1 — counter-evidence + research-gaps panels (`/runs/[runId]/research`).
  - F2 — clarifying-questions modal (`/runs/[runId]/clarify`).
  - F3 — retrieval source breakdown (`/runs/[runId]/literature`).
  - F4 — novelty score card (`/runs/[runId]/literature`).
  - F5 — citation graph view (`/runs/[runId]/citations`).
  - F6 — critique panel + revision counter (`/runs/[runId]/reviews`).
  - F7 — domain selector + profile cards (`/settings/domains`).
  - F7b — executor selector + cards (`/settings/executors`).
  - F8 — license audit table + CycloneDX SBOM download
    (`/settings/licenses`).
  - F9 — manifest panel + evidence matrix table + validation report
    card (`/runs/[runId]`).
  - F10 — auth context + login form (`/login`) + UserMenu in topbar.
  - F11 — autonomous loop start form + history + active monitor
    (`/loop`, `/loop/[loopId]`).
  - F12 — validation drilldown (search / group-by / copy CSV) inside
    `ValidationReportCard`.
  - F13 — `ApprovalCard` / `ApprovalCheckpoints` integration on the
    workspace shell.
- **Settings hub** (`/settings`) with tile navigation to Domains,
  Executors, and Licenses subpages plus the legacy theme / approvals
  / reset surfaces. Settings is also reachable from the sidebar nav.
- **Run-detail tab nav** (`RunDetailNav`) with Overview / Reviews /
  Research / Clarify / Literature / Citations and `aria-current`
  active-state.
- **Evals harness** (`evals/`) with five golden tasks, an LLM-judge
  with three-model majority, and a nightly GitHub Actions workflow
  capped at `PLATO_EVAL_MAX_USD`.
- **Postgres checkpointer** opt-in (`plato/state/checkpointer.py`,
  `langgraph-checkpoint-postgres` extra). SQLite remains the default
  for single-user installs. See ADR 0002.
- **License audit + SBOM** routes (`/api/v1/license_audit`,
  `/api/v1/sbom`) producing a CycloneDX SBOM via `cyclonedx-bom`.
- **Citation graph view** API + frontend rendering 1-hop OpenAlex
  citation expansion.

### Changed

- `Plato.get_paper(...)` accepts `max_revision_iters: int = 2`.
- The `/keys` UI exposes `LANGFUSE_PUBLIC` / `LANGFUSE_SECRET` /
  `LANGFUSE_HOST` alongside the LLM-provider keys.
- `manifests.py` enforces tenant isolation on every read (previously
  the `_user_id` lookup happened but the value was discarded).
- `create_project` and `write_stage` now use Pydantic-validated
  request bodies (`CreateProjectRequest`, `WriteStageRequest`) with
  length caps.
- `executor_preferences` storage path co-locates with
  `user_preferences` under `<project_root>/users/<user_id>/`.
- `RunDetailNav` shipped with the integration commit so the five
  per-run subroutes are reachable from each other.
- `dashboard/frontend/src/app/layout.tsx` adds
  `suppressHydrationWarning` on `<html>` so the inline theme
  bootstrap script no longer flags a hydration mismatch.

### Fixed

- **Critical**: `dashboard/backend/.../api/__init__.py` previously
  monkey-patched `create_app` *after* `server.py` had already created
  the module-level `app`. uvicorn's `server:app` import target got
  the un-patched app and silently dropped the citation_graph route.
  The patch is removed; the citation_graph router now mounts directly
  inside `create_app`.
- The `domain-selector` Radix Select no longer flips its hidden
  native `<select>` from uncontrolled to controlled when the default
  resolves after first render.
- `WorkspaceList` now renders an empty-state with a Run-pipeline CTA
  when every group is empty (previously a blank canvas).

## [0.1.0] - 2026-04-29

First public release of the dashboard. Phases 1 through 4 of the build plan
shipped (`~/.claude/plans/ultrathink-review-the-codebase-groovy-brook.md`).

### Added

- Real-time, IDE-style workspace replacing the legacy Streamlit `PlatoApp` for
  new workflows.
- Linear theme wired via [Super Design](https://github.com/Eldergenix/SUPER-DESIGN)
  tokens — Tailwind v4 `@theme` block in `frontend/src/app/globals.css` mirrors
  every entry in `dashboard/DESIGN.md`.
- Six top-level routes: `/` (workspace), `/projects`, `/models`, `/costs`,
  `/activity`, `/keys`, plus `/settings`.
- Real `multiprocessing.Process`-based Plato executor with first-class
  cancellation. `worker/run_manager.py` kills the entire process group so
  cmbagent's grandchild code-execution subprocess is cleaned up reliably.
- cmbagent log-tail bridge — `watchfiles` streams `*_generation_output/`
  directories into the SSE event bus as the worker writes them.
- LangGraph `astream_events` bridge for fast-mode stages, surfacing typed
  agent reasoning events to the frontend instead of raw stdout.
- Token + cost tracker reading `LLM_calls.txt` per run, aggregated into the
  cross-project ledger at `/costs`.
- Capabilities middleware (`api/capabilities.py`) gating on
  `PLATO_DEMO_MODE` and `PLATO_AUTH`. Demo mode locks code-executing stages
  with a friendly 403 and enforces a per-session $-budget cap.
- `POST /api/v1/keys/test/{provider}` endpoint that round-trips a stored API
  key against its provider so the user can verify before a paid run.
- React error boundary wrapping the workspace shell so a crashing stage view
  cannot take the whole app down.
- Command palette (`Cmd+K` / `Ctrl+K`) with project switching, route jumps,
  and stage actions.
- Docker Compose target plus a HuggingFace Spaces shim under
  `dashboard/spaces/` for one-click public demo deployment.
- GitHub Actions CI: `dashboard-backend.yml`, `dashboard-frontend.yml`,
  `dashboard-build.yml` — pytest, `tsc --noEmit`, Playwright smoke.
- 32 pytest tests covering project CRUD, stage IO, run lifecycle, capability
  enforcement, key store crypto, and the SSE bridge.
- 6 Playwright end-to-end specs covering smoke, navigation, command palette,
  stage flow, keys, and projects list filtering.

### Components

- Five primitives: `StageCard`, `AgentLogStream`, `PlotGrid`, `PaperPreview`,
  `CitationChip`.
- Power components: `ModelPicker`, `RunMonitor`, `CostMeterPanel`,
  `ApprovalCard`, `BottomBar`, `CapabilitiesBanner`.

### Known issues

- A real LLM run requires the user's own API keys. Either export
  `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` in the shell that
  launches the backend, or `PUT /api/v1/keys` per provider — the keys are
  encrypted to `~/.plato/keys.json` (mode `0600`).
- `arq` and `redis` are declared dependencies in `backend/pyproject.toml`,
  but the v0.1 executor uses an in-memory event bus
  (`events/bus.py`). Single-user local runs work end-to-end; multi-user and
  restart-survival are gated on the Redis swap-in (planned).

## Pre-0.1 — Design phase

- Initial product brief, Linear-theme exploration, capabilities matrix, and
  four-phase build plan recorded at
  `~/.claude/plans/ultrathink-review-the-codebase-groovy-brook.md`.
- No tagged release; tracked in commits prior to `v0.1.0`.

[Unreleased]: https://github.com/AstroPilot-AI/Plato/compare/dashboard-v0.1.0...HEAD
[0.1.0]: https://github.com/AstroPilot-AI/Plato/releases/tag/dashboard-v0.1.0
