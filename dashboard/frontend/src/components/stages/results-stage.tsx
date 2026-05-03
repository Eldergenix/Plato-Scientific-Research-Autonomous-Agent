"use client";

import * as React from "react";
import { FlaskConical, AlertTriangle, Square, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { StatusDot } from "@/components/ui/status-dot";
import { PlotGrid, type PlotItem } from "@/components/stages/plot-grid";
import { cn, formatDuration, formatRelativeTime } from "@/lib/utils";
import type { Project } from "@/lib/types";

const TABS = ["Summary", "Plots", "Code & execution"] as const;
type Tab = (typeof TABS)[number];

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
}

export function ResultsStage({ project, plots }: ResultsStageProps) {
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
          <RunMonitor project={project} />
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
          {tab === "Code & execution" && <CodePane project={project} />}
        </div>
      </main>
      <ResultsSidePanel project={project} />
    </div>
  );
}

function RunMonitor({ project }: { project: Project }) {
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

      <AgentSwimlane />
    </div>
  );
}

function AgentSwimlane() {
  // Iter-25: deleted the three hardcoded lane mark arrays
  // ([10,22,34,41,55,68,81] / [18,27,39,47,60,72,88] / [5,30,50,75,92])
  // that used to render decorative "agent activity" bars regardless of
  // run state — pure UI noise that suggested live telemetry where there
  // was none. Now: render an empty rail for each agent so the layout
  // shape is preserved (the run-monitor strip below keeps the same
  // height) until a future iter wires the bars to the SSE event stream
  // (``run.event.subscribe``).
  const lanes = [
    { name: "engineer", color: "bg-(--color-status-emerald)" },
    { name: "researcher", color: "bg-(--color-brand-lavender)" },
    { name: "planner", color: "bg-(--color-text-secondary)" },
  ];
  return (
    <div
      className="space-y-1.5"
      data-testid="agent-swimlane"
      title="Live agent activity will populate when wired to the event stream"
    >
      {lanes.map((lane) => (
        <div key={lane.name} className="flex items-center gap-3">
          <span className="w-20 text-[11px] font-mono text-(--color-text-tertiary)">
            {lane.name}
          </span>
          <div className="flex-1 h-3 rounded-[3px] bg-(--color-ghost-bg) relative" />
        </div>
      ))}
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
  // Iter-25: deleted the hardcoded GW231123 ringdown narrative
  // ("f ≈ 270 Hz / τ ≈ 4.1 ms / M_f ≈ 110 M_⊙") that used to render
  // for every project regardless of domain or run state. Until a real
  // results-summary endpoint is wired (planned: read
  // ``input_files/results.md`` via ``store.read_stage(pid, 'results')``),
  // we render either a "no summary yet" empty state or — when the
  // active run is past step 1 — a status line with the actual project
  // name so users see SOMETHING grounded in their own data.
  const run = project.activeRun;
  return (
    <article
      className="prose prose-invert max-w-none text-[13.5px] leading-[1.7] text-(--color-text-primary)"
      data-testid="results-summary-pane"
    >
      {run ? (
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

function CodePane({ project }: { project: Project }) {
  // Iter-25: deleted the hardcoded scipy.signal spectrogram + h1_strain.h5
  // snippet that posed as "step 3 · attempt 1" for every run. The real
  // code+execution surface should read from
  // ``runs/<run_id>/events.jsonl`` (where the worker emits ``code.execute``
  // events) — that's a follow-up. For now render an honest empty state.
  const run = project.activeRun;
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
        <div className="px-3 py-6 text-[12px] text-(--color-text-tertiary) leading-[1.55] text-center">
          {run ? (
            <p>
              Live code execution will appear here once the worker emits{" "}
              <code className="font-mono">code.execute</code> events. Streaming
              wire-up is a follow-up.
            </p>
          ) : (
            <p>
              No code executions yet. Start a run to populate this view —
              every <code className="font-mono">cmbagent</code> /{" "}
              <code className="font-mono">local_jupyter</code> /{" "}
              <code className="font-mono">modal</code> /{" "}
              <code className="font-mono">e2b</code> step writes a record that
              shows up here.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultsSidePanel({ project }: { project: Project }) {
  // Iter-25: replaced the hardcoded run_id="run_8a2f1c" / "1h 24m ago"
  // / fixed engineer/researcher/planner config with values pulled from
  // ``project.activeRun`` (or an honest "no active run" state when the
  // project is idle). Resume / Cancel buttons are stub — wiring them
  // to ``api.cancelRun`` happens in a follow-up.
  const run = project.activeRun;
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
            <Button variant="ghost" size="md" disabled>
              <RefreshCw size={12} strokeWidth={1.5} />
              Resume
            </Button>
            <Button variant="danger" size="md" disabled>
              <Square size={12} strokeWidth={1.5} />
              Cancel
            </Button>
          </div>

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
