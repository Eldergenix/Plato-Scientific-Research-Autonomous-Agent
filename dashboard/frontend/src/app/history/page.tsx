"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CalendarClock,
  ChevronDown,
  History,
  RefreshCw,
  Search,
} from "lucide-react";
import { DashboardShell } from "@/components/shell/dashboard-shell";
import { Button } from "@/components/ui/button";
import { api, type RunRecord, type RunStatus } from "@/lib/api";
import type { Project, StageId } from "@/lib/types";
import {
  cn,
  formatDuration,
  formatRelativeTime,
  formatTokens,
} from "@/lib/utils";

type StageFilter = "all" | StageId;
type StatusFilter = "all" | RunStatus;

interface ProjectRun extends RunRecord {
  projectName: string;
}

const STAGE_LABELS: Record<StageId, string> = {
  data: "Data",
  idea: "Idea",
  literature: "Literature",
  method: "Method",
  results: "Results",
  paper: "Paper",
  referee: "Referee",
};

const STATUS_LABELS: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
};

const STATUS_FILTERS: Array<{ id: StatusFilter; label: string }> = [
  { id: "all", label: "All statuses" },
  { id: "queued", label: STATUS_LABELS.queued },
  { id: "running", label: STATUS_LABELS.running },
  { id: "succeeded", label: STATUS_LABELS.succeeded },
  { id: "failed", label: STATUS_LABELS.failed },
  { id: "cancelled", label: STATUS_LABELS.cancelled },
];

const STAGE_FILTERS: Array<{ id: StageFilter; label: string }> = [
  { id: "all", label: "All stages" },
  ...Object.entries(STAGE_LABELS).map(([id, label]) => ({
    id: id as StageId,
    label,
  })),
];

function runTime(run: RunRecord): number {
  const raw = run.finishedAt ?? run.startedAt ?? "";
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function runDuration(run: RunRecord): string {
  if (!run.startedAt || !run.finishedAt) return "n/a";
  const start = Date.parse(run.startedAt);
  const end = Date.parse(run.finishedAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return "n/a";
  }
  return formatDuration(end - start);
}

function matchesRun(run: ProjectRun, query: string, stage: StageFilter, status: StatusFilter): boolean {
  const q = query.trim().toLowerCase();
  if (stage !== "all" && run.stage !== stage) return false;
  if (status !== "all" && run.status !== status) return false;
  if (!q) return true;
  return (
    run.id.toLowerCase().includes(q) ||
    run.projectName.toLowerCase().includes(q) ||
    STAGE_LABELS[run.stage].toLowerCase().includes(q) ||
    run.mode.toLowerCase().includes(q) ||
    run.status.toLowerCase().includes(q)
  );
}

async function loadProjectRuns(projects: Project[]): Promise<{
  runs: ProjectRun[];
  partialFailures: number;
}> {
  const settled = await Promise.allSettled(
    projects.map(async (project) => {
      const runs = await api.listRuns(project.id);
      return runs.map((run) => ({
        ...run,
        projectName: project.name,
      }));
    }),
  );

  const runs = settled.flatMap((entry) =>
    entry.status === "fulfilled" ? entry.value : [],
  );
  const partialFailures = settled.filter((entry) => entry.status === "rejected").length;
  runs.sort((a, b) => runTime(b) - runTime(a));
  return { runs, partialFailures };
}

export default function HistoryPage() {
  return (
    <DashboardShell>
      <HistoryContent />
    </DashboardShell>
  );
}

function HistoryContent() {
  const [runs, setRuns] = React.useState<ProjectRun[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [query, setQuery] = React.useState("");
  const [stageFilter, setStageFilter] = React.useState<StageFilter>("all");
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all");
  const [visible, setVisible] = React.useState(50);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const projects = await api.listProjects();
      const { runs: nextRuns, partialFailures } = await loadProjectRuns(projects);
      setRuns(nextRuns);
      if (partialFailures > 0) {
        setError(
          `${partialFailures} project run ${
            partialFailures === 1 ? "ledger" : "ledgers"
          } could not be loaded.`,
        );
      }
    } catch (err) {
      setRuns([]);
      setError(err instanceof Error ? err.message : "Failed to load history.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  React.useEffect(() => {
    setVisible(50);
  }, [query, stageFilter, statusFilter]);

  const filtered = React.useMemo(
    () => runs.filter((run) => matchesRun(run, query, stageFilter, statusFilter)),
    [runs, query, stageFilter, statusFilter],
  );
  const shown = filtered.slice(0, visible);
  const totals = React.useMemo(() => buildTotals(runs), [runs]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <header className="hairline-b flex flex-none items-center justify-between gap-3 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <History size={17} strokeWidth={1.75} className="text-(--color-brand-hover)" />
          <div className="min-w-0">
            <h1 className="text-[18px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
              History
            </h1>
            <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
              Persisted stage runs across every Plato project.
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void refresh()}
          disabled={loading}
        >
          <RefreshCw size={13} className={cn(loading && "animate-spin")} />
          Refresh
        </Button>
      </header>

      <section className="grid flex-none grid-cols-2 gap-2 px-4 py-3 lg:grid-cols-4">
        <Metric label="Runs" value={totals.total.toLocaleString()} />
        <Metric label="Succeeded" value={totals.succeeded.toLocaleString()} />
        <Metric label="Failed" value={totals.failed.toLocaleString()} tone={totals.failed > 0 ? "danger" : "default"} />
        <Metric label="Tokens" value={formatTokens(totals.tokens)} />
      </section>

      <section className="hairline-y flex flex-none flex-col gap-2 px-4 py-2 lg:flex-row lg:items-center lg:justify-between">
        <label className="flex h-8 min-w-0 flex-1 items-center gap-2 rounded-[6px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2.5 lg:max-w-md">
          <Search size={13} className="text-(--color-text-tertiary)" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search run, project, stage, status"
            className="min-w-0 flex-1 bg-transparent font-mono text-[12px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary) focus:outline-none"
          />
        </label>
        <div className="flex gap-2">
          <FilterSelect
            label="Stage"
            value={stageFilter}
            options={STAGE_FILTERS}
            onChange={(value) => setStageFilter(value as StageFilter)}
          />
          <FilterSelect
            label="Status"
            value={statusFilter}
            options={STATUS_FILTERS}
            onChange={(value) => setStatusFilter(value as StatusFilter)}
          />
        </div>
      </section>

      {error ? (
        <div className="mx-4 mt-3 flex flex-none items-center gap-2 rounded-[8px] border border-(--color-status-amber-spec) px-3 py-2 text-[12px] text-(--color-status-amber-spec)">
          <AlertTriangle size={13} />
          <span>{error}</span>
        </div>
      ) : null}

      <section className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        <div className="surface-linear-card overflow-x-auto">
          {loading ? (
            <HistorySkeleton />
          ) : shown.length === 0 ? (
            <EmptyHistory />
          ) : (
            <>
              <div className="grid h-9 min-w-[720px] grid-cols-[minmax(190px,1.5fr)_110px_105px_110px_110px_80px] items-center gap-3 border-b border-(--color-border-card) px-3 text-[11px] font-medium uppercase tracking-[0.04em] text-(--color-text-quaternary)">
                <span>Run</span>
                <span>Stage</span>
                <span>Status</span>
                <span>Started</span>
                <span>Duration</span>
                <span className="text-right">Tokens</span>
              </div>
              {shown.map((run) => (
                <RunRow key={`${run.projectId}:${run.id}`} run={run} />
              ))}
              {filtered.length > shown.length ? (
                <div className="flex justify-center border-t border-(--color-border-card) px-4 py-3">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setVisible((current) => current + 50)}
                  >
                    Show more
                    <ChevronDown size={12} />
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </div>
      </section>
    </div>
  );
}

function buildTotals(runs: ProjectRun[]) {
  return runs.reduce(
    (acc, run) => {
      acc.total += 1;
      acc.tokens += run.tokenInput + run.tokenOutput;
      if (run.status === "succeeded") acc.succeeded += 1;
      if (run.status === "failed") acc.failed += 1;
      return acc;
    },
    { total: 0, succeeded: 0, failed: 0, tokens: 0 },
  );
}

function Metric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "danger";
}) {
  return (
    <div className="rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) px-3 py-2">
      <div className="text-[11px] font-medium uppercase tracking-[0.04em] text-(--color-text-quaternary)">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 font-mono text-[18px] text-(--color-text-primary-strong)",
          tone === "danger" && "text-(--color-status-red-spec)",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ id: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex h-8 items-center gap-2 rounded-[6px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2 text-[12px] text-(--color-text-tertiary)">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="bg-transparent text-[12px] text-(--color-text-primary) focus:outline-none"
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function RunRow({ run }: { run: ProjectRun }) {
  const tokens = run.tokenInput + run.tokenOutput;
  return (
    <div className="grid min-h-12 min-w-[720px] grid-cols-[minmax(190px,1.5fr)_110px_105px_110px_110px_80px] items-center gap-3 border-b border-(--color-border-card) px-3 py-2 text-[12px] last:border-b-0">
      <div className="min-w-0">
        <Link
          href={`/runs/${encodeURIComponent(run.id)}`}
          className="block truncate font-mono text-[12px] text-(--color-text-primary-strong) hover:text-(--color-brand-hover)"
        >
          {run.id}
        </Link>
        <div className="mt-0.5 truncate text-[11px] text-(--color-text-tertiary)">
          {run.projectName}
        </div>
      </div>
      <span className="text-(--color-text-secondary-spec)">{STAGE_LABELS[run.stage]}</span>
      <StatusPill status={run.status} />
      <span className="text-(--color-text-tertiary)">
        {run.startedAt ? formatRelativeTime(run.startedAt) : "n/a"}
      </span>
      <span className="text-(--color-text-tertiary)">{runDuration(run)}</span>
      <span className="text-right font-mono text-(--color-text-secondary-spec)">
        {tokens > 0 ? formatTokens(tokens) : "-"}
      </span>
    </div>
  );
}

function StatusPill({ status }: { status: RunStatus }) {
  return (
    <span
      className={cn(
        "inline-flex w-fit rounded-full px-2 py-0.5 font-mono text-[11px]",
        status === "failed"
          ? "bg-(--color-status-red)/10 text-(--color-status-red-spec)"
          : status === "succeeded"
            ? "bg-(--color-status-green)/10 text-(--color-status-green)"
            : status === "running"
              ? "bg-(--color-status-blue)/10 text-(--color-status-blue)"
              : "bg-(--color-ghost-bg) text-(--color-text-tertiary)",
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

function EmptyHistory() {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
      <div className="flex size-10 items-center justify-center rounded-full bg-(--color-bg-pill-inactive) text-(--color-text-tertiary)">
        <CalendarClock size={18} />
      </div>
      <p className="max-w-sm text-[13px] text-(--color-text-row-meta)">
        No matching runs are recorded yet.
      </p>
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div className="p-3">
      {Array.from({ length: 6 }).map((_, index) => (
        <div
          key={index}
          className="mb-2 h-10 animate-shimmer rounded-[6px] last:mb-0"
        />
      ))}
    </div>
  );
}
