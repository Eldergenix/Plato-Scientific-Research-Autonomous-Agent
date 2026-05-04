"use client";

import * as React from "react";
import { FlaskConical, AlertTriangle, Square, RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { StatusDot } from "@/components/ui/status-dot";
import { PlotGrid, type PlotItem } from "@/components/stages/plot-grid";
import { api } from "@/lib/api";
import { cn, formatDuration, formatRelativeTime } from "@/lib/utils";
import type { Project } from "@/lib/types";

const TABS = ["Summary", "Plots", "Code & execution"] as const;
type Tab = (typeof TABS)[number];

// Iter-28: backend already publishes node.entered/node.exited events
// over the run:{run_id} SSE channel (see langgraph_bridge.py). The
// AgentSwimlane consumes them via a parent-supplied prop so the
// component stays presentational and the parent owns the event
// subscription lifecycle.
export interface NodeActivityEvent {
  /** Node name from AGENT_NODE_NAMES (idea_maker, methods_node, etc.). */
  name: string;
  /** Backend stage that owns the run (idea / method / results / paper / referee). */
  stage?: string;
  /** ms timestamp the event landed in the panel — used for sort + diff. */
  ts: number;
  /** node.entered or node.exited. */
  kind: "entered" | "exited";
  /** Only set on node.exited; ms the node spent active. */
  durationMs?: number;
}

// Iter-30: per-cell code.execute event the dashboard worker emits after
// the results-stage executor returns. CodePane renders one card per
// entry with the executor's source / stdout / error. Parent supplies
// the array; component stays presentational.
export interface CodeExecuteEvent {
  index?: number;
  source?: string;
  stdout?: string | null;
  stderr?: string | null;
  executor?: string | null;
  ts: number;
  error?: {
    ename?: string;
    evalue?: string;
  } | null;
}

// Iter-22: dropped the SAMPLE_PLOTS fallback (4 hardcoded astro plots —
// ringdown_spectrogram / qnm_fit_2_2_0 / qnm_fit_3_3_0 / psd_band). The
// fallback fired whenever the live ``plots`` prop was empty, which meant
// brand-new projects (and every non-astro domain) rendered fake astro
// plot tiles with broken ``url=""`` thumbnails. ResultsStage now renders
// the empty-plots state via PlotGrid's existing empty-state branch, so
// what users see matches what's actually on disk.


export interface ResultsStageProps {
  project: Project;
  /** Live plot list — passed in from useProject().plots and refreshed on plot.created SSE events. */
  plots?: { name: string; url: string }[];
  /** Iter-28: live agent-activity events streamed from useProject().nodeEvents. */
  nodeEvents?: NodeActivityEvent[];
  /** Iter-30: per-cell code-execute events streamed from useProject().codeEvents. */
  codeEvents?: CodeExecuteEvent[];
  /** Iter-28: parent's cancel-run callback. When omitted, the cancel button stays disabled. */
  onCancelRun?: () => void | Promise<void>;
}

export function ResultsStage({
  project,
  plots,
  nodeEvents,
  codeEvents,
  onCancelRun,
}: ResultsStageProps) {
  const [tab, setTab] = React.useState<Tab>("Plots");
  const run = project.activeRun;
  const elapsedMs = run ? Date.now() - new Date(run.startedAt).getTime() : 0;

  // Promote backend plots → PlotItem[]. Iter-22: removed the SAMPLE_PLOTS
  // fallback that rendered fake astro plots whenever the live list was
  // empty — empty now stays empty, and PlotGrid is responsible for the
  // empty-state UI.
  const liveItems: PlotItem[] = React.useMemo(() => {
    if (!plots || plots.length === 0) return [];
    return plots.map((p) => ({
      name: p.name,
      url: p.url,
      caption: p.name.replace(/\.png$/, "").replace(/_/g, " "),
    }));
  }, [plots]);

  return (
    <div className="flex h-full">
      <main className="flex-1 overflow-auto">
        <div className="px-6 pt-6 pb-4 hairline-b">
          <div className="flex items-baseline gap-3">
            <FlaskConical size={20} strokeWidth={1.5} className="text-(--color-status-emerald)" />
            <h2 className="font-h1 tracking-[-0.704px]">Results</h2>
            <Pill tone="indigo" className="gap-2">
              <StatusDot status="running" size={6} />
              Step {run?.step}/{run?.totalSteps} · attempt {run?.attempt}/{run?.totalAttempts}
              <span className="font-mono text-(--color-text-quaternary) ml-1">
                {formatDuration(elapsedMs)}
              </span>
            </Pill>
          </div>
          <RunMonitor project={project} nodeEvents={nodeEvents} />
        </div>

        <div className="px-6 pt-3 hairline-b">
          <div role="tablist" className="flex gap-1">
            {TABS.map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={cn(
                  "h-8 px-3 text-[13px] rounded-t-[4px] -mb-px border-b-2 transition-colors",
                  tab === t
                    ? "text-(--color-text-primary) border-(--color-brand-interactive)"
                    : "text-(--color-text-tertiary) border-transparent hover:text-(--color-text-primary)",
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="px-6 py-4">
          {tab === "Plots" && <PlotsPane initial={liveItems} />}
          {tab === "Summary" && <SummaryPane project={project} />}
          {tab === "Code & execution" && (
            <CodePane project={project} codeEvents={codeEvents} />
          )}
        </div>
      </main>
      <ResultsSidePanel project={project} onCancelRun={onCancelRun} />
    </div>
  );
}

function RunMonitor({
  project,
  nodeEvents,
}: {
  project: Project;
  nodeEvents?: NodeActivityEvent[];
}) {
  const run = project.activeRun;
  if (!run) return null;
  const pct = run.step && run.totalSteps ? (run.step / run.totalSteps) * 100 : 0;
  return (
    <div className="mt-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-[11px] uppercase tracking-wider text-(--color-text-quaternary) font-medium">
          Progress
        </span>
        <div className="flex-1 h-1.5 rounded-full bg-(--color-ghost-bg) overflow-hidden">
          <div
            className="h-full bg-(--color-brand-interactive)"
            style={{ width: `${pct}%`, transition: "width 200ms ease-out" }}
          />
        </div>
        <span className="font-mono text-[11.5px] text-(--color-text-tertiary) tabular-nums">
          {Math.round(pct)}%
        </span>
      </div>

      <AgentSwimlane nodeEvents={nodeEvents} runStartedAt={run.startedAt} />
    </div>
  );
}

/**
 * Iter-28 SSE wire-up: AgentSwimlane consumes node.entered / node.exited
 * events and renders one lane per node name, with a tick mark per
 * event positioned on the timeline by relative offset from
 * ``runStartedAt``. Active nodes (entered without a matching exited)
 * are highlighted; finished nodes show a ghost mark.
 *
 * Empty state preserved: when no events yet (or the prop is undefined),
 * we render the same empty rails the iter-25 placeholder used so the
 * layout shape doesn't jump on first event arrival.
 */
function AgentSwimlane({
  nodeEvents,
  runStartedAt,
}: {
  nodeEvents?: NodeActivityEvent[];
  runStartedAt: string;
}) {
  const events = nodeEvents ?? [];
  const startMs = React.useMemo(
    () => new Date(runStartedAt).getTime(),
    [runStartedAt],
  );

  // Group events by node name. For each name, count active = entered
  // count - exited count. The most-recent event ts is used to clamp
  // the lane width.
  const lanes = React.useMemo(() => {
    const byName = new Map<
      string,
      { name: string; events: NodeActivityEvent[]; activeCount: number }
    >();
    for (const e of events) {
      const slot = byName.get(e.name) ?? {
        name: e.name,
        events: [],
        activeCount: 0,
      };
      slot.events.push(e);
      slot.activeCount += e.kind === "entered" ? 1 : -1;
      byName.set(e.name, slot);
    }
    return Array.from(byName.values()).sort((a, b) =>
      a.name.localeCompare(b.name),
    );
  }, [events]);

  const maxOffsetMs = React.useMemo(() => {
    const now = Date.now();
    const lastTs = events.length > 0 ? events[events.length - 1].ts : now;
    // Track width = whichever is larger — current elapsed or "last event was X ago".
    return Math.max(now - startMs, lastTs - startMs, 1000);
  }, [events, startMs]);

  if (lanes.length === 0) {
    // Empty state: same shape as iter-25 placeholder so first-event
    // arrival doesn't pop the layout.
    const placeholders = ["engineer", "researcher", "planner"];
    return (
      <div
        className="space-y-1.5"
        data-testid="agent-swimlane"
        title="Live agent activity will populate when the worker emits node.entered events"
      >
        {placeholders.map((name) => (
          <div key={name} className="flex items-center gap-3">
            <span className="w-20 text-[11px] font-mono text-(--color-text-quaternary)">
              {name}
            </span>
            <div className="flex-1 h-3 rounded-[3px] bg-(--color-ghost-bg) relative" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      className="space-y-1.5"
      data-testid="agent-swimlane"
      data-lane-count={lanes.length}
    >
      {lanes.map((lane) => {
        const isActive = lane.activeCount > 0;
        return (
          <div
            key={lane.name}
            className="flex items-center gap-3"
            data-lane-name={lane.name}
            data-lane-active={isActive ? "true" : "false"}
          >
            <span
              className={cn(
                "w-20 text-[11px] font-mono truncate",
                isActive
                  ? "text-(--color-status-emerald)"
                  : "text-(--color-text-tertiary)",
              )}
              title={lane.name}
            >
              {lane.name}
            </span>
            <div className="flex-1 h-3 rounded-[3px] bg-(--color-ghost-bg) relative">
              {lane.events.map((e, i) => {
                const offset = Math.max(0, e.ts - startMs);
                const left = (offset / maxOffsetMs) * 100;
                return (
                  <span
                    key={i}
                    className={cn(
                      "absolute top-0 bottom-0 w-1 rounded-full opacity-80",
                      e.kind === "entered"
                        ? "bg-(--color-status-emerald)"
                        : "bg-(--color-brand-lavender)",
                    )}
                    style={{ left: `${left}%` }}
                    title={`${e.kind} · ${e.name}${
                      e.durationMs ? ` · ${e.durationMs}ms` : ""
                    }`}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PlotsPane({ initial }: { initial: PlotItem[] }) {
  const [plots, setPlots] = React.useState<PlotItem[]>(initial);
  // Sync local state when the parent's plot list changes (e.g., plot.created SSE event).
  React.useEffect(() => {
    setPlots(initial);
  }, [initial]);
  return (
    <PlotGrid
      plots={plots}
      onReorder={(names) => {
        const byName = new Map(plots.map((p) => [p.name, p]));
        setPlots(names.map((n) => byName.get(n)!).filter(Boolean));
      }}
      onCaptionEdit={(name, caption) =>
        setPlots((prev) => prev.map((p) => (p.name === name ? { ...p, caption } : p)))
      }
      onDelete={(name) => setPlots((prev) => prev.filter((p) => p.name !== name))}
    />
  );
}

function SummaryPane({ project }: { project: Project }) {
  // Iter-29: SummaryPane reads the real ``input_files/results.md`` via
  // the existing ``GET /api/v1/projects/{pid}/state/results`` endpoint
  // (no new endpoint needed — this one has been here since iter-6).
  // When the file exists we render the markdown body verbatim inside
  // a <pre> so the worker's formatting (which is already markdown) is
  // preserved without pulling in a markdown renderer dep. When it
  // doesn't exist yet, fall back to the iter-25 honest empty state.
  const run = project.activeRun;
  const [summary, setSummary] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Refetch on:
  //   - project change (switching projects)
  //   - active-run id change (a new run started → previous summary is stale)
  //   - active run finishes (run.stage transitions on stage.finished)
  // The startedAt key includes runId so the same run staying mid-flight
  // doesn't trigger a refetch on every parent render.
  const refetchKey = `${project.id}|${run?.runId ?? "idle"}|${run?.startedAt ?? ""}`;
  React.useEffect(() => {
    if (!project.id) {
      setSummary(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const r = await api.readStage(project.id, "results");
        if (cancelled) return;
        setSummary(r?.markdown?.trim() ? r.markdown : null);
      } catch (e: unknown) {
        if (cancelled) return;
        // 404 = file not on disk yet (worker hasn't finished). Treat
        // as "no summary" so we render the empty state, not an error.
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("404")) {
          setSummary(null);
        } else {
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refetchKey, project.id]);

  return (
    <article
      className="prose prose-invert max-w-none text-[13.5px] leading-[1.7] text-(--color-text-primary)"
      data-testid="results-summary-pane"
    >
      {loading && summary === null ? (
        <p
          className="text-(--color-text-tertiary)"
          data-testid="results-summary-loading"
        >
          Loading <code className="font-mono">input_files/results.md</code>…
        </p>
      ) : error ? (
        <div data-testid="results-summary-error">
          <h3 className="text-[15px] font-medium tracking-[-0.01em] text-(--color-status-red)">
            Failed to load results summary
          </h3>
          <p className="text-(--color-text-tertiary)">{error}</p>
        </div>
      ) : summary !== null ? (
        <>
          <pre
            className="whitespace-pre-wrap font-sans text-[13.5px] leading-[1.7] text-(--color-text-primary)"
            data-testid="results-summary-content"
          >
            {summary}
          </pre>
          {run ? (
            <p className="text-[11.5px] text-(--color-text-quaternary) mt-3">
              Auto-refreshes when the active run finishes (run id{" "}
              <code className="font-mono">{run.runId}</code>).
            </p>
          ) : null}
        </>
      ) : run ? (
        <>
          <h3 className="text-[15px] font-medium tracking-[-0.01em]">
            Run in progress — step {run.step ?? "—"} of {run.totalSteps ?? "—"}
          </h3>
          <p className="text-(--color-text-secondary)">
            <code className="font-mono">{project.name || "Untitled project"}</code> is
            executing the {run.stage} stage. Live progress streams via SSE
            (see the agent transcript above); the rendered summary will
            populate once the worker writes
            <code className="font-mono"> input_files/results.md</code>.
          </p>
        </>
      ) : (
        <>
          <h3 className="text-[15px] font-medium tracking-[-0.01em]">No summary yet</h3>
          <p className="text-(--color-text-secondary)">
            Start a run from the Methods stage (or use the side panel
            below) to populate this view. Plato writes the per-run
            results summary to{" "}
            <code className="font-mono">input_files/results.md</code> when the
            stage finishes.
          </p>
        </>
      )}
    </article>
  );
}

function CodePane({
  project,
  codeEvents,
}: {
  project: Project;
  codeEvents?: CodeExecuteEvent[];
}) {
  // Iter-30: real per-cell render. The dashboard worker emits one
  // ``code.execute`` event per cell after the results-stage executor
  // returns (using ExecutorResult.artifacts.cells which iter-18
  // LocalJupyterExecutor + iter-20 Modal/E2B all populate). Parent
  // collects them in useProject().codeEvents and passes here.
  //
  // When no events have arrived (idle project, or results stage
  // running but pre-executor), fall back to the iter-29 honest
  // empty state pointing at the other surfaces. This preserves the
  // iter-29 contract for fresh projects.
  const run = project.activeRun;
  const events = codeEvents ?? [];
  const sorted = React.useMemo(() => {
    return [...events].sort(
      (a, b) => (a.index ?? a.ts) - (b.index ?? b.ts),
    );
  }, [events]);

  return (
    <div className="space-y-3" data-testid="results-code-pane">
      <div className="surface-card">
        <div className="px-3 py-2 hairline-b flex items-center gap-2">
          <span className="text-[11px] font-mono text-(--color-text-tertiary)">
            {run
              ? `step ${run.step ?? "—"} · attempt ${run.attempt ?? "—"}`
              : "no active run"}
          </span>
          <Pill tone={run ? "indigo" : "neutral"} className="ml-auto">
            {run ? "running" : "idle"}
          </Pill>
        </div>
        {sorted.length > 0 ? (
          <ul
            className="divide-y divide-(--color-border-standard)"
            data-testid="results-code-list"
            data-cell-count={sorted.length}
          >
            {sorted.map((cell, i) => (
              <CodeCell key={cell.index ?? i} cell={cell} />
            ))}
          </ul>
        ) : (
          <div className="px-3 py-6 text-[12px] text-(--color-text-tertiary) leading-[1.55] text-center">
            <p>
              No code executions yet. The Results stage emits one card
              here per cell after the executor returns. For live agent
              reasoning see the transcript above; for the run's markdown
              summary switch to the <strong>Summary</strong> tab; for
              generated figures the <strong>Plots</strong> tab.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Iter-30 — single cell card. Shows the executor source as a
 * monospace code block, then optional stdout / stderr / error. Indexed
 * by ``cell.index`` for stable keys across re-renders.
 */
function CodeCell({ cell }: { cell: CodeExecuteEvent }) {
  const hasError = cell.error != null && cell.error.ename != null;
  const indexLabel =
    cell.index != null ? `cell ${cell.index + 1}` : "cell";
  return (
    <li
      className="px-3 py-3"
      data-testid={
        cell.index != null
          ? `results-code-cell-${cell.index}`
          : "results-code-cell"
      }
      data-cell-error={hasError ? "true" : "false"}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[11px] font-mono text-(--color-text-tertiary)">
          {indexLabel}
        </span>
        {cell.executor ? (
          <Pill tone="neutral" className="text-[10.5px]">
            {cell.executor}
          </Pill>
        ) : null}
        {hasError ? (
          <Pill tone="red" className="ml-auto text-[10.5px]">
            error
          </Pill>
        ) : (
          <Pill tone="green" className="ml-auto text-[10.5px]">
            ran
          </Pill>
        )}
      </div>
      {cell.source ? (
        <pre className="font-mono text-[12px] leading-[1.55] text-(--color-text-secondary) bg-(--color-bg-pill-inactive) rounded-[4px] px-2.5 py-2 overflow-x-auto whitespace-pre">
          {cell.source}
        </pre>
      ) : null}
      {cell.stdout ? (
        <details className="mt-2 text-[11.5px]">
          <summary className="cursor-pointer text-(--color-text-tertiary) hover:text-(--color-text-secondary)">
            stdout ({cell.stdout.split("\n").length} lines)
          </summary>
          <pre className="mt-1 font-mono text-(--color-text-tertiary) bg-(--color-bg-pill-inactive) rounded-[4px] px-2.5 py-2 overflow-x-auto whitespace-pre">
            {cell.stdout}
          </pre>
        </details>
      ) : null}
      {cell.stderr ? (
        <details className="mt-2 text-[11.5px]">
          <summary className="cursor-pointer text-(--color-status-amber) hover:text-(--color-text-primary)">
            stderr ({cell.stderr.split("\n").length} lines)
          </summary>
          <pre className="mt-1 font-mono text-(--color-status-amber) bg-(--color-bg-pill-inactive) rounded-[4px] px-2.5 py-2 overflow-x-auto whitespace-pre">
            {cell.stderr}
          </pre>
        </details>
      ) : null}
      {hasError ? (
        <p className="mt-2 text-[11.5px] text-(--color-status-red) font-mono">
          {cell.error?.ename}: {cell.error?.evalue}
        </p>
      ) : null}
    </li>
  );
}

function ResultsSidePanel({
  project,
  onCancelRun,
}: {
  project: Project;
  onCancelRun?: () => void | Promise<void>;
}) {
  // Iter-28: Cancel button now wired through to ``api.cancelRun`` via
  // the parent's onCancelRun callback (passed down from page.tsx →
  // useProject().cancelRun). Resume is still disabled — the backend
  // ``/runs/{run_id}/resume`` endpoint doesn't exist yet, and silently
  // pretending to support resume would be worse than the disabled
  // affordance.
  const run = project.activeRun;
  const [cancelling, setCancelling] = React.useState(false);
  const [cancelError, setCancelError] = React.useState<string | null>(null);

  const handleCancel = React.useCallback(async () => {
    if (!onCancelRun || cancelling) return;
    setCancelError(null);
    setCancelling(true);
    try {
      await onCancelRun();
    } catch (e: unknown) {
      setCancelError(e instanceof Error ? e.message : "Failed to cancel run");
    } finally {
      setCancelling(false);
    }
  }, [onCancelRun, cancelling]);
  return (
    <aside
      className="w-[320px] hairline-l bg-(--color-bg-marketing) p-4 overflow-auto"
      data-testid="results-side-panel"
    >
      <h3 className="font-label">Active run</h3>
      {run ? (
        <>
          <div className="mt-2 surface-card p-3 text-[12px]">
            <div className="flex items-center justify-between">
              <span className="text-(--color-text-tertiary)">run_id</span>
              <span
                className="font-mono text-(--color-text-primary) truncate ml-2"
                title={run.runId}
              >
                {run.runId}
              </span>
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-(--color-text-tertiary)">stage</span>
              <span className="font-mono text-(--color-text-primary)">
                {run.stage}
              </span>
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-(--color-text-tertiary)">started</span>
              <span className="font-mono text-(--color-text-primary)">
                {run.startedAt ? formatRelativeTime(run.startedAt) : "—"}
              </span>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-1.5">
            <Button
              variant="ghost"
              size="md"
              disabled
              title="Resume requires a /runs/{id}/resume endpoint that doesn't exist yet"
            >
              <RefreshCw size={12} strokeWidth={1.5} />
              Resume
            </Button>
            <Button
              variant="danger"
              size="md"
              disabled={!onCancelRun || cancelling}
              onClick={handleCancel}
              data-testid="results-side-cancel"
            >
              {cancelling ? (
                <Loader2 size={12} strokeWidth={1.5} className="animate-spin" />
              ) : (
                <Square size={12} strokeWidth={1.5} />
              )}
              {cancelling ? "Cancelling…" : "Cancel"}
            </Button>
          </div>
          {cancelError ? (
            <p
              className="mt-2 text-[11px] text-(--color-status-red)"
              data-testid="results-side-cancel-error"
            >
              {cancelError}
            </p>
          ) : null}

          <h3 className="font-label mt-6">Run config</h3>
          <div className="mt-2 space-y-2">
            <Field
              label="step"
              value={
                run.step != null && run.totalSteps != null
                  ? `${run.step} / ${run.totalSteps}`
                  : "—"
              }
            />
            <Field
              label="attempt"
              value={
                run.attempt != null && run.totalAttempts != null
                  ? `${run.attempt} / ${run.totalAttempts}`
                  : "—"
              }
            />
          </div>
        </>
      ) : (
        <div
          className="mt-2 surface-card border-dashed border-(--color-border-standard) px-3 py-4 text-center"
          data-testid="results-side-panel-empty"
        >
          <p className="text-[12px] text-(--color-text-tertiary) leading-[1.55]">
            No active run. Trigger one from the Methods stage to see live
            run state, model config, and cancel controls here.
          </p>
        </div>
      )}

      <h3 className="font-label mt-6 flex items-center gap-2">
        <AlertTriangle size={11} strokeWidth={1.5} className="text-(--color-status-amber)" />
        On failure
      </h3>
      <p className="text-[12px] text-(--color-text-tertiary) mt-1.5 leading-[1.55]">
        If a step fails after retries, restart from a specific step with
        a different model. Plato persists step-level checkpoints to
        <code className="font-mono"> runs/&lt;run_id&gt;/status.json</code> so a
        retry resumes where the previous attempt errored.
      </p>
    </aside>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] uppercase tracking-wider text-(--color-text-quaternary) font-medium">
        {label}
      </span>
      <span className="font-mono text-[12px] text-(--color-text-primary) tabular-nums">{value}</span>
    </div>
  );
}
