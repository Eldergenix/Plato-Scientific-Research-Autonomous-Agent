"use client";

import * as React from "react";
import Link from "next/link";
import { Activity, Search, TimerReset } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Run, RunStatus } from "@/lib/types";
import { cn, formatRelativeTime, formatTokens } from "@/lib/utils";

type StatusFilter = "all" | RunStatus;

// Backend exposes runs only per-project (`GET /api/v1/projects/{pid}/runs`),
// so the discovery page fans out: list projects → fetch runs in parallel →
// flatten into one timeline. Same approach the activity page uses.
interface RunRow extends Run {
  projectName: string;
}

const STATUS_TABS: ReadonlyArray<{ id: StatusFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "running", label: "Running" },
  { id: "queued", label: "Queued" },
  { id: "succeeded", label: "Succeeded" },
  { id: "failed", label: "Failed" },
  { id: "cancelled", label: "Cancelled" },
];

// Status colors live as CSS custom properties in globals.css so light mode
// can override them in one place. Each entry resolves to two variables:
// foreground text + tinted background.
const STATUS_TONE: Record<RunStatus, { bg: string; fg: string }> = {
  running: { bg: "var(--color-status-running-bg)", fg: "var(--color-status-running)" },
  queued: { bg: "var(--color-status-queued-bg)", fg: "var(--color-status-queued)" },
  succeeded: { bg: "var(--color-status-succeeded-bg)", fg: "var(--color-status-succeeded)" },
  failed: { bg: "var(--color-status-failed-bg)", fg: "var(--color-status-failed)" },
  cancelled: { bg: "var(--color-status-cancelled-bg)", fg: "var(--color-status-cancelled)" },
};

const GRID_COLS = "minmax(0,1.4fr) 1fr 110px 0.9fr 80px 96px";

function StatusPill({ status }: { status: RunStatus }) {
  const tone = STATUS_TONE[status];
  return (
    <span
      className="inline-flex h-[20px] items-center rounded-full px-2 text-[11px] font-medium capitalize"
      style={{ backgroundColor: tone.bg, color: tone.fg }}
    >
      {status}
    </span>
  );
}

// Token totals come back as input + output split — surface the sum so users
// can compare runs at a glance without doing the math themselves.
function totalTokens(r: Run): number {
  return (r.tokenInput ?? 0) + (r.tokenOutput ?? 0);
}

function startedAtMs(r: Run): number {
  return r.startedAt ? new Date(r.startedAt).getTime() : 0;
}

export default function RunsPage() {
  const [runs, setRuns] = React.useState<RunRow[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState<StatusFilter>("all");
  const [query, setQuery] = React.useState("");

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const projects = await api.listProjects();
        if (cancelled) return;
        const lists = await Promise.all(
          projects.map(async (p) => {
            try {
              const list = await api.listRuns(p.id);
              return list.map<RunRow>((r) => ({ ...r, projectName: p.name }));
            } catch (err) {
              // One project's runs failing shouldn't blank the whole page.
              // Log silently and yield an empty slice for that project.
              console.warn(`listRuns(${p.id}) failed`, err);
              return [] as RunRow[];
            }
          }),
        );
        if (cancelled) return;
        const flat = lists.flat();
        flat.sort((a, b) => startedAtMs(b) - startedAtMs(a));
        setRuns(flat);
      } catch (err: unknown) {
        if (cancelled) return;
        if (err instanceof ApiError) {
          setError(`API error ${err.status}`);
        } else {
          setError(err instanceof Error ? err.message : "Failed to load runs");
        }
        setRuns([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = React.useMemo(() => {
    const list = runs ?? [];
    const q = query.trim().toLowerCase();
    return list.filter((r) => {
      if (tab !== "all" && r.status !== tab) return false;
      if (!q) return true;
      return (
        r.id.toLowerCase().includes(q) ||
        r.projectName.toLowerCase().includes(q) ||
        r.stage.toLowerCase().includes(q)
      );
    });
  }, [runs, tab, query]);

  const isLoading = runs === null;
  const isEmpty = !isLoading && (runs?.length ?? 0) === 0;

  return (
    <div className="min-h-screen bg-(--color-bg-page) text-(--color-text-primary)">
      {/* Header */}
      <div className="surface-linear-card mx-4 mt-4 flex h-16 items-center px-4">
        <div className="flex flex-1 items-center gap-3">
          <Activity size={18} className="text-(--color-text-tertiary)" />
          <div className="flex flex-col leading-tight">
            <h1
              className="text-white"
              style={{
                fontFamily: "var(--font-sans)",
                fontSize: 24,
                fontWeight: 510,
                letterSpacing: "-0.5px",
              }}
            >
              Runs
            </h1>
            <p className="text-[12px] text-(--color-text-row-meta)">
              Every active and historical Plato run, across all projects.
            </p>
          </div>
        </div>
      </div>

      {/* Filter bar */}
      <div className="hairline-b mx-4 mt-4 flex h-10 items-center justify-between px-4">
        <div className="flex items-center gap-1.5">
          {STATUS_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                "h-6 rounded-[6px] border px-2 text-[12px] transition-colors",
                tab === t.id
                  ? "border-(--color-border-pill) bg-(--color-bg-pill-active) text-white"
                  : "border-(--color-border-solid) bg-(--color-bg-pill-inactive) text-(--color-text-row-meta) hover:text-white",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <label className="flex h-6 items-center gap-1.5 rounded-[6px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2">
          <Search size={11} className="text-(--color-text-tertiary)" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search run id, project, stage"
            className="w-64 bg-transparent font-mono text-[12px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary) focus:outline-none"
          />
        </label>
      </div>

      {/* Table */}
      <div className="surface-linear-card mx-4 mt-4 mb-12 overflow-hidden">
        {error ? (
          <div className="flex h-40 items-center justify-center text-[13px] text-(--color-status-red-spec)">
            Failed to load runs: {error}
          </div>
        ) : isLoading ? (
          <SkeletonTable />
        ) : isEmpty ? (
          <EmptyState />
        ) : filtered.length === 0 ? (
          <div className="flex h-40 items-center justify-center text-[13px] text-(--color-text-row-meta)">
            No runs match your filters.
          </div>
        ) : (
          <>
            <HeaderRow />
            {filtered.map((r) => (
              <RunRowView key={`${r.projectId}:${r.id}`} run={r} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function HeaderRow() {
  // Header is grid-only; mobile cards don't need a header since each card
  // labels its own fields visually.
  return (
    <div
      className="hairline-b hidden md:grid items-center gap-3 px-4 text-[11px] font-[510] uppercase tracking-wider text-(--color-text-tertiary-spec)"
      style={{ height: 32, gridTemplateColumns: GRID_COLS }}
    >
      <span>Run</span>
      <span>Project</span>
      <span>Status</span>
      <span>Started</span>
      <span className="text-right">Tokens</span>
      <span className="text-right">Stage</span>
    </div>
  );
}

function RunRowView({ run }: { run: RunRow }) {
  // Two layouts share a row: a tight grid on md+ and a stacked card on
  // narrow viewports. Both wrap the same Link target so behaviour matches.
  return (
    <Link
      href={`/runs/${run.id}`}
      className="block border-b border-(--color-border-card) transition-colors last:border-b-0 hover:bg-(--color-ghost-bg-hover)"
    >
      {/* md+ table row */}
      <div
        className="hidden md:grid items-center gap-3 px-4"
        style={{ height: 48, gridTemplateColumns: GRID_COLS }}
      >
        <div className="min-w-0">
          <div className="truncate font-mono text-[12.5px] text-(--color-text-row-title)">
            {run.id}
          </div>
          {run.error ? (
            <div className="truncate text-[11px] text-(--color-status-red-spec)">
              {run.error}
            </div>
          ) : null}
        </div>
        <div className="min-w-0 truncate text-[13px] text-(--color-text-secondary-spec)">
          {run.projectName}
        </div>
        <div>
          <StatusPill status={run.status} />
        </div>
        <div
          className="text-[12px] text-(--color-text-row-meta)"
          title={run.startedAt ?? "not started"}
        >
          {run.startedAt ? formatRelativeTime(run.startedAt) : "—"}
        </div>
        <div className="text-right font-mono text-[12.5px] tabular-nums text-(--color-text-secondary-spec)">
          {formatTokens(totalTokens(run))}
        </div>
        <div className="text-right text-[12px] capitalize text-(--color-text-row-meta)">
          {run.stage}
        </div>
      </div>

      {/* sub-md stacked card */}
      <div className="md:hidden flex flex-col gap-1.5 px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="truncate font-mono text-[13px] text-(--color-text-row-title)">
              {run.id}
            </div>
            <div className="truncate text-[12px] text-(--color-text-secondary-spec)">
              {run.projectName}
            </div>
          </div>
          <StatusPill status={run.status} />
        </div>
        {run.error ? (
          <div className="truncate text-[11px] text-(--color-status-red-spec)">
            {run.error}
          </div>
        ) : null}
        <div className="flex items-center justify-between gap-3 text-[11px] text-(--color-text-row-meta)">
          <span title={run.startedAt ?? "not started"}>
            {run.startedAt ? formatRelativeTime(run.startedAt) : "—"}
          </span>
          <span className="flex items-center gap-3">
            <span className="capitalize">{run.stage}</span>
            <span className="font-mono tabular-nums text-(--color-text-secondary-spec)">
              {formatTokens(totalTokens(run))}
            </span>
          </span>
        </div>
      </div>
    </Link>
  );
}

function SkeletonTable() {
  return (
    <>
      <HeaderRow />
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="border-b border-(--color-border-card) last:border-b-0"
        >
          <div
            className="hidden md:grid items-center gap-3 px-4"
            style={{ height: 48, gridTemplateColumns: GRID_COLS }}
          >
            <div className="h-3 w-3/4 animate-shimmer rounded-[4px]" />
            <div className="h-3 w-1/2 animate-shimmer rounded-[4px]" />
            <div className="h-4 w-16 animate-shimmer rounded-full" />
            <div className="h-3 w-20 animate-shimmer rounded-[4px]" />
            <div className="ml-auto h-3 w-12 animate-shimmer rounded-[4px]" />
            <div className="ml-auto h-3 w-12 animate-shimmer rounded-[4px]" />
          </div>
          <div className="md:hidden flex flex-col gap-2 px-4 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 space-y-1.5">
                <div className="h-3 w-2/3 animate-shimmer rounded-[4px]" />
                <div className="h-3 w-1/3 animate-shimmer rounded-[4px]" />
              </div>
              <div className="h-5 w-16 animate-shimmer rounded-full" />
            </div>
            <div className="flex items-center justify-between">
              <div className="h-3 w-16 animate-shimmer rounded-[4px]" />
              <div className="h-3 w-20 animate-shimmer rounded-[4px]" />
            </div>
          </div>
        </div>
      ))}
    </>
  );
}

function EmptyState() {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3">
      <div className="flex size-10 items-center justify-center rounded-full bg-(--color-bg-pill-inactive) text-(--color-text-tertiary)">
        <TimerReset size={18} />
      </div>
      <p className="max-w-md text-center text-[13px] text-(--color-text-row-meta)">
        No runs yet. Start a stage from a project to see it appear here.
      </p>
    </div>
  );
}
