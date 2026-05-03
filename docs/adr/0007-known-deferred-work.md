# ADR 0007 — Known deferred work and incompleteness register

- **Status**: Accepted (informational)
- **Date**: 2026-05-02
- **Deciders**: Plato maintainers
- **Phase**: cross-cutting

## Context

A recent code audit surfaced several pieces of Plato that are intentionally
shipped as stubs, partial implementations, or "Phase N+1" placeholders.
Each of them has a sound reason to exist in its current shape, but until
now that reasoning lived only in code comments and inline docstrings.

**Wave 7 update (2026-05-03).** Two of the original entries shipped:
the telemetry collector (`plato/state/telemetry.py`) and the run-config
presets surface (dashboard `api/run_presets.py` + Settings page). Both
are marked "(SHIPPED)" below and retained for one release cycle so PRs
that referenced them by id resolve, then they will be removed. The
`modal` and `e2b` executors still raise `NotImplementedError` but the
class skeletons + registry hooks now land in `main`, awaiting only SDK
credentials and the real run/cancel paths.

This ADR exists so that:

- Contributors can see in one place which surfaces are deliberately
  incomplete, instead of mistaking a stub for a bug.
- Each item carries the file/line that holds the placeholder, why it was
  deferred, and what unblocks the real implementation.
- Existing ADRs (0003 domain pluggability, 0005 executor protocol) are
  not amended in-place — they describe accepted decisions and stay
  append-only. This ADR is the running log of "decided to ship a stub".

This ADR is **a register, not a roadmap**. It deliberately does not
commit to timelines. Picking up any of these items is its own scoped PR
and may warrant its own ADR if the implementation introduces design
choices.

## Deferred items

### 1. `modal` executor backend — stub

- **File:** `plato/executor/modal_backend.py:34`
- **Why deferred:** ADR 0005 elects to ship the `Executor` Protocol and
  registry first so the dashboard, domain profiles, and tests can wire
  through a real choice end-to-end before any sandboxed backend lands.
- **Blocker:** Modal SDK integration — needs a Modal Function definition
  for the project mount, secrets plumbing for `KeyManager`, and a
  cancellation path that maps `cancel_event` onto Modal's task lifecycle.
- **Tracking:** `TBD-modal-executor` (placeholder issue id; replace when
  the project issue tracker is wired up).
- **See also:** ADR 0005.

### 2. `e2b` executor backend — stub

- **File:** `plato/executor/e2b_backend.py:33`
- **Why deferred:** Same reasoning as #1 — the Protocol shipped before
  the implementations so we could iterate on the contract under tests.
- **Blocker:** E2B SDK integration — needs a sandbox provisioning step,
  file-system upload of `project_dir`, and result extraction back to the
  caller's `ExecutorResult` shape.
- **Tracking:** `TBD-e2b-executor`.
- **See also:** ADR 0005.

### 3. Biology domain — uses `cmbagent` executor as a placeholder

- **File:** `plato/domain/__init__.py:93`
- **Why deferred:** The biology profile (ADR 0003) ships with PubMed
  retrieval, MeSH keyword extraction, and biology-shaped journal presets
  so a non-astro user has something useful out of the box. The executor
  field, however, points at the in-process `cmbagent` backend because no
  biology-specific code-execution environment exists yet (e.g. one that
  pre-stages bio data tooling).
- **Blocker:** A real biology executor — most likely a flavour of the
  `modal` or `e2b` backend with a curated dependency manifest. Depends
  on items #1 / #2.
- **Tracking:** `TBD-biology-executor`.
- **See also:** ADR 0003 (the domain registry), ADR 0005 (the executor
  Protocol this field satisfies).

### 4. Telemetry settings panel — UI stub

- **File:** `dashboard/frontend/src/app/settings/page.tsx:332`
  ("Telemetry: not yet implemented", `disabled` pill).
- **Why deferred:** The toggle is rendered behind a disabled pill so
  the settings layout is stable for when the collector lands. Shipping
  the UI without the collector would silently send nothing and confuse
  users about whether their preference took effect.
- **Blocker:** Backend telemetry collector — needs an opt-in transport
  (almost certainly OpenTelemetry over HTTPS), a redaction policy that
  matches `SECURITY.md`, and a settings persistence path that survives
  CLI and dashboard config sources.
- **Tracking:** `TBD-telemetry-collector`.

### 5. Per-node breakdown manifest field — partial

- **File:** `plato/state/manifest.py:11-12, 47-51`
- **Why deferred:** The schema field (`tokens_per_node`) and the
  recorder-side accumulator already ship in Phase 1 because changing the
  manifest schema after the fact is painful. The dashboard cost
  attribution that consumes it lands in Phase 3 with the eval harness.
- **Blocker:** Eval harness wiring — the manifest already accepts
  per-node entries; the remaining work is consistent population from
  every workflow node and a dashboard view that surfaces the breakdown.
- **Tracking:** `TBD-per-node-cost`.

### 6. Events bus — single-process today, Redis swap-in deferred

- **File:** `dashboard/backend/src/plato_dashboard/events/bus.py:1-5`
- **Why deferred:** The Phase 1 dashboard runs in a single backend
  process, so an `asyncio.Queue` fan-out is sufficient and avoids
  forcing a Redis dependency on `plato dashboard` users. The interface
  was deliberately written to match Redis Streams so the swap-in is
  contained.
- **Blocker:** Multi-process / multi-replica deployment story —
  whichever lands first (horizontal scaling of the dashboard backend or
  cross-process workers publishing events) will pull this in.
- **Tracking:** `TBD-events-redis-swap`.

### 7. Run-config presets UI — missing

- **File:** none yet (no UI surface for saving/loading run configs as
  named presets; flagged in the audit as missing rather than stubbed).
- **Why deferred:** The run-config schema and the dashboard form for
  configuring a run are stable, but there is no "save this as a preset"
  affordance. Users today re-enter the same configuration each run. The
  data model and persistence layer for presets has not been designed.
- **Blocker:** Design decision — whether presets are scoped per-user,
  per-domain, or global; whether they live in the dashboard backend
  database or as on-disk YAML next to the project; how they interact
  with `DomainProfile` defaults.
- **Tracking:** `TBD-run-config-presets`.

## Decision

Adopt this register as the canonical, file-pointed list of intentionally
deferred work. New stubs / placeholders added to the codebase **must**
either (a) update this ADR with a row, or (b) be filed as a real bug
fix instead. Removing a row when an item lands is part of the PR that
implements it.

## Consequences

**Positive.**

- Contributors triaging "is this a bug or is it intentional?" can grep
  this ADR first and stop reading.
- Each item names its blocker, so picking up the work has an obvious
  starting point.
- ADRs 0003 and 0005 stay focused on their original decisions instead of
  drifting into status pages.

**Negative.**

- This file will go stale if PRs forget to update it. Mitigated by
  treating it as part of the same review checklist as the changelog.

**Neutral.**

- The `TBD-…` tracking ids are placeholders. Once a real issue tracker
  is wired up, replace each placeholder with a real link in the same PR
  that opens the issue.

## See also

- ADR 0003 — Domain profile pluggability (items #3, partially #5).
- ADR 0005 — Sandboxed Executor protocol (items #1, #2, and the reason
  #3 is parked behind `cmbagent`).
- `SECURITY.md` §"LLM-generated code execution" — the long-term reason
  the executor stubs need real implementations.
