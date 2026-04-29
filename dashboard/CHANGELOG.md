# Changelog

All notable changes to the Plato Dashboard are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Real-time markdown editing with collaborative cursors in the stage detail
  panel (currently read-only with auto-snapshot on save).
- Multi-user authentication beyond the single-tenant `PLATO_AUTH=enabled`
  bearer-cookie flow (OIDC / Clerk integration).
- Public deployment artifacts: a turn-key Vercel template plus a curated
  HuggingFace Space pinned to a fixed Plato release tag.

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
