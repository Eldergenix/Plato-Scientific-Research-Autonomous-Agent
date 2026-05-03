# Changelog

All notable changes to the Plato library are documented in this file.
The dashboard maintains its own log at `dashboard/CHANGELOG.md`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Post-iter-17 hardening across three waves on top of the 0.2 baseline.

### Added

- **Wave 5 — `LocalJupyterExecutor`** (`plato/executor/local_jupyter.py`).
  Local Jupyter kernel backend via `jupyter_client` with subprocess fallback
  when `jupyter_client` / `ipykernel` aren't importable. Module-level state
  persists across cells, matching notebook semantics.
- **Wave 5 — Modal / E2B executor skeletons** (`plato/executor/modal_backend.py`,
  `plato/executor/e2b_backend.py`). Class skeletons + registry hooks land on
  `main` so domain profiles can declare `executor="modal"` / `executor="e2b"`
  today. `run()` raises `NotImplementedError` until SDK credentials and the
  real run/cancel paths land.
- **Wave 7 — Telemetry collector** (`plato/state/telemetry.py`). Opt-in
  local-only JSONL sink at `~/.plato/telemetry.jsonl`, three-way gated
  (`PLATO_TELEMETRY_DISABLED=1`, `telemetry_enabled` user pref, IO failure).
  Eight-field stable schema + six optional fields for the dashboard collector.
- **Wave 7 — Run-config presets** (dashboard
  `api/run_presets.py` + Settings → Run Presets page). Per-user named bundles
  of run knobs, persisted at `<project>/users/<uid>/run_presets.json`.
- **Wave 3 — R11 paper-agents** (`plato/paper_agents/`). Reviewer-panel rewrite
  consolidating methodology / statistics / novelty / writing critics behind
  one aggregator.
- **Wave 3 — Run list page** (`dashboard/frontend/src/app/page.tsx`).
  Surfaces all runs with active-run highlighting and direct links into stages.
- **Wave 3 — Vitest + ESLint** in the frontend with strict unit tests and
  lint gates.
- **ADR 0007** — running register of intentionally-deferred work.

### Changed

- Multi-tenant auth: `X-Plato-User` is now checked on every protected dashboard
  route, not just project-list reads (Wave 3 security audit).
- ADR 0007 marks telemetry collector and run-config presets as SHIPPED,
  modal/e2b executors as "skeleton ready; awaits credentials".

## [0.2.0] - 2026-05-02

Phase 5 hardening — multi-source retrieval, citation validation, evidence
matrix, reviewer panel, autonomous loop, reproducibility manifest,
observability, pluggable domains, multi-tenant dashboard. See
`dashboard/CHANGELOG.md` for the dashboard-specific surface area and
`docs/adr/0001-…0006-` for the design decisions.
