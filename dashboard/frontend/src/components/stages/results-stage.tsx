"use client";

import * as React from "react";
import { FlaskConical, AlertTriangle, Square, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { StatusDot } from "@/components/ui/status-dot";
import { PlotGrid, type PlotItem } from "@/components/stages/plot-grid";
import { cn, formatDuration } from "@/lib/utils";
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
          {tab === "Summary" && <SummaryPane />}
          {tab === "Code & execution" && <CodePane />}
        </div>
      </main>
      <ResultsSidePanel />
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
  const lanes = [
    { name: "engineer", color: "bg-(--color-status-emerald)", marks: [10, 22, 34, 41, 55, 68, 81] },
    { name: "researcher", color: "bg-(--color-brand-lavender)", marks: [18, 27, 39, 47, 60, 72, 88] },
    { name: "planner", color: "bg-(--color-text-secondary)", marks: [5, 30, 50, 75, 92] },
  ];
  return (
    <div className="space-y-1.5">
      {lanes.map((lane) => (
        <div key={lane.name} className="flex items-center gap-3">
          <span className="w-20 text-[11px] font-mono text-(--color-text-tertiary)">
            {lane.name}
          </span>
          <div className="flex-1 h-3 rounded-[3px] bg-(--color-ghost-bg) relative">
            {lane.marks.map((m, i) => (
              <span
                key={i}
                className={cn("absolute top-0 bottom-0 w-1 rounded-full opacity-80", lane.color)}
                style={{ left: `${m}%` }}
              />
            ))}
          </div>
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

function SummaryPane() {
  return (
    <article className="prose prose-invert max-w-none text-[13.5px] leading-[1.7] text-(--color-text-primary)">
      <h3 className="text-[15px] font-medium tracking-[-0.01em]">Preliminary results — step 3 of 6</h3>
      <p className="text-(--color-text-secondary)">
        Spectrogram analysis of GW231123 strain data confirms a dominant ringdown mode at{" "}
        <code className="font-mono">f ≈ 270 Hz</code> with decay time{" "}
        <code className="font-mono">τ ≈ 4.1 ms</code>, consistent with a final-mass estimate{" "}
        <code className="font-mono">M_f ≈ 110 M_⊙</code>.
      </p>
      <p className="text-(--color-text-secondary)">
        Subsequent steps will fit a two-mode QNM template and quantify the (3,3,0) detection
        significance with PSD-marginalised likelihood.
      </p>
    </article>
  );
}

function CodePane() {
  return (
    <div className="space-y-3">
      <div className="surface-card">
        <div className="px-3 py-2 hairline-b flex items-center gap-2">
          <span className="text-[11px] font-mono text-(--color-text-tertiary)">step 3 · attempt 1</span>
          <Pill tone="green" className="ml-auto">success</Pill>
        </div>
        <pre className="px-3 py-3 font-mono text-[12px] leading-[1.6] text-(--color-text-secondary) overflow-auto">
          <code>{`import scipy.signal as sp
import h5py, numpy as np

with h5py.File('data/h1_strain.h5', 'r') as f:
    strain = f['strain'][:]
fs = 4096
freq, t, Sxx = sp.spectrogram(
    strain, fs=fs, nperseg=256, noverlap=224
)
plt.pcolormesh(t, freq, np.log10(Sxx), shading='gouraud')
plt.savefig('plots/ringdown_spectrogram.png', dpi=160)`}</code>
        </pre>
      </div>
    </div>
  );
}

function ResultsSidePanel() {
  return (
    <aside className="w-[320px] hairline-l bg-(--color-bg-marketing) p-4 overflow-auto">
      <h3 className="font-label">Active run</h3>
      <div className="mt-2 surface-card p-3 text-[12px]">
        <div className="flex items-center justify-between">
          <span className="text-(--color-text-tertiary)">run_id</span>
          <span className="font-mono text-(--color-text-primary)">run_8a2f1c</span>
        </div>
        <div className="flex items-center justify-between mt-1">
          <span className="text-(--color-text-tertiary)">started</span>
          <span className="font-mono text-(--color-text-primary)">1h 24m ago</span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-1.5">
        <Button variant="ghost" size="md">
          <RefreshCw size={12} strokeWidth={1.5} />
          Resume
        </Button>
        <Button variant="danger" size="md">
          <Square size={12} strokeWidth={1.5} />
          Cancel
        </Button>
      </div>

      <h3 className="font-label mt-6">Run config</h3>
      <div className="mt-2 space-y-2">
        <Field label="Engineer" value="gpt-5" />
        <Field label="Researcher" value="claude-4.1-opus" />
        <Field label="Planner" value="gpt-4.1" />
        <Field label="Plan reviewer" value="o3-mini" />
        <Field label="max_n_steps" value="6" />
        <Field label="max_n_attempts" value="5" />
      </div>

      <h3 className="font-label mt-6 flex items-center gap-2">
        <AlertTriangle size={11} strokeWidth={1.5} className="text-(--color-status-amber)" />
        On failure
      </h3>
      <p className="text-[12px] text-(--color-text-tertiary) mt-1.5 leading-[1.55]">
        If a step fails after retries, you can{" "}
        <em className="not-italic text-(--color-text-secondary)">restart from step k</em> with a
        different model — typically claude-4.1-opus for stuck runs.
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
