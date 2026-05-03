"use client";

import * as React from "react";
import { Activity, Edit3, Sparkles, AlertTriangle, TimerReset, Search, Filter, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import type { Project, Stage, StageStatus } from "@/lib/types";
import { StatusIcon } from "@/components/views/status-icon";
import { Button } from "@/components/ui/button";
import { cn, formatRelativeTime, formatDuration, formatTokens, formatCost } from "@/lib/utils";

type EventKind = "stage.run" | "stage.edit" | "stage.failed";
type RangeId = "today" | "week" | "month" | "all";
type FilterId = "all" | "runs" | "edits" | "errors";

interface ActivityEvent {
  id: string;
  ts: string;
  kind: EventKind;
  project: { id: string; name: string };
  stage: Stage;
  status: StageStatus;
  model?: string;
  durationMs?: number;
  tokens?: number;
  costCents?: number;
  errorMessage?: string;
}

const PAGE_SIZE = 50;
const DAY_MS = 86_400_000;
const RANGES: { id: RangeId; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "week", label: "This week" },
  { id: "month", label: "This month" },
  { id: "all", label: "All time" },
];
const FILTERS: { id: FilterId; label: string }[] = [
  { id: "all", label: "All events" },
  { id: "runs", label: "Stage runs" },
  { id: "edits", label: "Edits" },
  { id: "errors", label: "Errors" },
];

// Flatten Project[] -> ActivityEvent[]: walk stages with `lastRunAt`, classify
// by origin/status (edited=>edit, failed=>failed, else run). Token & cost are
// pro-rated across done stages since per-event metering isn't on the API yet.
function extractEvents(projects: Project[]): ActivityEvent[] {
  const out: ActivityEvent[] = [];
  for (const p of projects) {
    const stages = Object.values(p.stages);
    const doneCount = stages.filter((s) => s.status === "done").length || 1;
    const tokensPer = Math.round(p.totalTokens / doneCount);
    const costPer = Math.round(p.totalCostCents / doneCount);
    for (const s of stages) {
      if (!s.lastRunAt) continue;
      const kind: EventKind =
        s.status === "failed" ? "stage.failed" : s.origin === "edited" ? "stage.edit" : "stage.run";
      out.push({
        id: `${p.id}:${s.id}:${s.lastRunAt}`,
        ts: s.lastRunAt,
        kind,
        project: { id: p.id, name: p.name },
        stage: s,
        status: s.status,
        model: s.model,
        durationMs: s.durationMs,
        tokens: s.status === "done" ? tokensPer : undefined,
        costCents: s.status === "done" ? costPer : undefined,
        errorMessage: s.status === "failed" ? (s.progressLabel ?? "stage run failed") : undefined,
      });
    }
  }
  out.sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());
  return out;
}

function inRange(ts: string, range: RangeId): boolean {
  if (range === "all") return true;
  const delta = Date.now() - new Date(ts).getTime();
  if (range === "today") return delta <= DAY_MS;
  if (range === "week") return delta <= 7 * DAY_MS;
  return delta <= 30 * DAY_MS;
}

function matchesFilter(e: ActivityEvent, f: FilterId): boolean {
  if (f === "all") return true;
  if (f === "runs") return e.kind === "stage.run";
  if (f === "edits") return e.kind === "stage.edit";
  return e.kind === "stage.failed";
}

function matchesQuery(e: ActivityEvent, q: string): boolean {
  if (!q) return true;
  const n = q.toLowerCase();
  return (
    e.project.name.toLowerCase().includes(n) ||
    e.stage.label.toLowerCase().includes(n) ||
    (e.model ?? "").toLowerCase().includes(n)
  );
}

const DATE_FMT = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });

function dateBucket(ts: string): { key: string; label: string } {
  const d = new Date(ts);
  const local = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const t = new Date();
  const todayKey = new Date(t.getFullYear(), t.getMonth(), t.getDate());
  const diff = Math.round((todayKey.getTime() - local.getTime()) / DAY_MS);
  const key = local.toISOString().slice(0, 10);
  if (diff === 0) return { key, label: "Today" };
  if (diff === 1) return { key, label: "Yesterday" };
  return { key, label: DATE_FMT.format(local) };
}

type Group = { key: string; label: string; items: ActivityEvent[] };
function groupByDate(events: ActivityEvent[]): Group[] {
  const map = new Map<string, Group>();
  for (const e of events) {
    const b = dateBucket(e.ts);
    const cur = map.get(b.key);
    if (cur) cur.items.push(e);
    else map.set(b.key, { ...b, items: [e] });
  }
  return Array.from(map.values());
}

function KindIcon({ kind }: { kind: EventKind }) {
  if (kind === "stage.failed") return <AlertTriangle size={11} className="text-(--color-status-red-spec)" />;
  if (kind === "stage.edit") return <Edit3 size={11} className="text-(--color-text-row-meta)" />;
  return <Sparkles size={11} className="text-(--color-status-purple)" />;
}

export default function ActivityPage() {
  const [projects, setProjects] = React.useState<Project[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [range, setRange] = React.useState<RangeId>("all");
  const [filter, setFilter] = React.useState<FilterId>("all");
  const [query, setQuery] = React.useState("");
  const [visible, setVisible] = React.useState(PAGE_SIZE);

  React.useEffect(() => {
    let cancelled = false;
    api.listProjects()
      .then((p) => { if (!cancelled) setProjects(p); })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : "failed to load"); });
    return () => { cancelled = true; };
  }, []);

  const allEvents = React.useMemo(() => (projects ? extractEvents(projects) : []), [projects]);
  const filtered = React.useMemo(
    () => allEvents.filter((e) => inRange(e.ts, range) && matchesFilter(e, filter) && matchesQuery(e, query)),
    [allEvents, range, filter, query],
  );
  // Memoized so unrelated state changes (e.g. typing in the search box
  // before a debounce settles) don't re-bucket the visible slice.
  const groups = React.useMemo(
    () => groupByDate(filtered.slice(0, visible)),
    [filtered, visible],
  );
  const hasMore = filtered.length > visible;
  const loading = projects === null && !error;

  return (
    <div className="min-h-screen bg-(--color-bg-page) text-(--color-text-primary)">
      {/* Page header */}
      <div className="surface-linear-card mx-4 mt-4 flex h-16 items-center px-4">
        <div className="flex flex-1 items-center gap-3">
          <Activity size={18} className="text-(--color-text-tertiary)" />
          <div className="flex flex-col leading-tight">
            <h1 className="text-white" style={{ fontFamily: "var(--font-sans)", fontSize: 24, fontWeight: 510, letterSpacing: "-0.5px" }}>
              Activity
            </h1>
            <p className="text-[12px] text-(--color-text-row-meta)">
              Reproducibility audit log — every stage event across every project.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {RANGES.map((r) => (
            <button key={r.id} type="button" data-state={range === r.id ? "active" : undefined} onClick={() => setRange(r.id)} className="tab-pill">
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Filter bar */}
      <div className="hairline-b mx-4 mt-4 flex h-10 items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <Filter size={12} className="text-(--color-text-tertiary)" />
          {FILTERS.map((f) => (
            <button key={f.id} type="button" onClick={() => setFilter(f.id)}
              className={cn(
                "h-6 rounded-[6px] border px-2 text-[12px] transition-colors",
                filter === f.id
                  ? "border-(--color-border-pill) bg-(--color-bg-pill-active) text-white"
                  : "border-(--color-border-solid) bg-(--color-bg-pill-inactive) text-(--color-text-row-meta) hover:text-white",
              )}>
              {f.label}
            </button>
          ))}
        </div>
        <label className="flex h-6 items-center gap-1.5 rounded-[6px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2">
          <Search size={11} className="text-(--color-text-tertiary)" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search project, stage, model"
            className="w-56 bg-transparent font-mono text-[12px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary) focus:outline-none" />
        </label>
      </div>

      {/* Feed */}
      <div className="surface-linear-card mx-4 mt-4 mb-12 overflow-hidden">
        {error ? (
          <div className="flex h-40 items-center justify-center text-[13px] text-(--color-status-red-spec)">
            Failed to load activity: {error}
          </div>
        ) : loading ? (
          <SkeletonRows />
        ) : filtered.length === 0 ? (
          <EmptyState />
        ) : (
          <>
            {groups.map((g) => (
              <div key={g.key}>
                <div className="hairline-b sticky top-0 z-10 flex h-8 items-center bg-(--color-bg-page) px-4">
                  <span className="font-label">{g.label}</span>
                  <span className="ml-2 text-[11px] text-(--color-text-quaternary)">
                    {g.items.length} {g.items.length === 1 ? "event" : "events"}
                  </span>
                </div>
                {g.items.map((e, i) => (
                  <EventRow key={e.id} event={e} isLastInGroup={i === g.items.length - 1} />
                ))}
              </div>
            ))}
            {hasMore && (
              <div className="hairline-t flex justify-center px-4 py-3">
                <Button variant="ghost" size="sm" onClick={() => setVisible((v) => v + PAGE_SIZE)}>
                  Show more
                  <ChevronDown size={12} />
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function EventRow({ event, isLastInGroup }: { event: ActivityEvent; isLastInGroup: boolean }) {
  return (
    <div className={cn("relative flex min-h-[52px]", !isLastInGroup && "hairline-b")}>
      <div className="relative w-14 flex-none">
        <span aria-hidden className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-(--color-border-pill)" />
        <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-(--color-bg-card) p-0.5">
          <StatusIcon status={event.status} size={14} />
        </span>
      </div>
      <div className="flex min-w-0 flex-1 items-center gap-3 px-4 py-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex items-center gap-1.5 text-[15px] leading-tight text-white">
            <KindIcon kind={event.kind} />
            <EventTitle event={event} />
          </div>
          <div className="flex items-center gap-2 text-[12px] text-(--color-text-row-meta)">
            {event.model && <span className="font-mono">{event.model}</span>}
            {event.durationMs !== undefined && (<><span aria-hidden>·</span><span>{formatDuration(event.durationMs)}</span></>)}
            {event.tokens !== undefined && (<><span aria-hidden>·</span><span>{formatTokens(event.tokens)} tok</span></>)}
            {event.costCents !== undefined && (<><span aria-hidden>·</span><span>{formatCost(event.costCents)}</span></>)}
          </div>
        </div>
        <span className="ml-auto flex-none whitespace-nowrap text-[12px] text-(--color-text-quaternary)">
          {formatRelativeTime(event.ts)}
        </span>
      </div>
    </div>
  );
}

function EventTitle({ event }: { event: ActivityEvent }) {
  const project = <span className="font-medium text-white">{event.project.name}</span>;
  const stage = <span className="font-medium text-white">{event.stage.label}</span>;
  if (event.kind === "stage.failed")
    return (
      <span className="truncate text-(--color-text-secondary-spec)">
        {project} <span className="text-(--color-text-row-meta)">— failed </span>{stage}
        <span className="text-(--color-status-red-spec)">: {event.errorMessage}</span>
      </span>
    );
  if (event.kind === "stage.edit")
    return (
      <span className="truncate text-(--color-text-secondary-spec)">
        {project} <span className="text-(--color-text-row-meta)">— edited </span>{stage}{" "}
        <span className="text-(--color-text-row-meta)">markdown</span>
      </span>
    );
  return (
    <span className="truncate text-(--color-text-secondary-spec)">
      {project} <span className="text-(--color-text-row-meta)">— generated </span>{stage}
    </span>
  );
}

function EmptyState() {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3">
      <div className="flex size-10 items-center justify-center rounded-full bg-(--color-bg-pill-inactive) text-(--color-text-tertiary)">
        <TimerReset size={18} />
      </div>
      <p className="text-[13px] text-(--color-text-row-meta)">
        No activity yet — start a run to see events here.
      </p>
    </div>
  );
}

function SkeletonRows() {
  return (
    <div>
      <div className="hairline-b flex h-8 items-center px-4">
        <span className="font-label opacity-60">Loading</span>
      </div>
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className={cn("relative flex min-h-[52px]", i < 4 && "hairline-b")}>
          <div className="relative w-14 flex-none">
            <span aria-hidden className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-(--color-border-pill)" />
            <span className="absolute left-1/2 top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-(--color-bg-pill-inactive)" />
          </div>
          <div className="flex flex-1 flex-col justify-center gap-2 px-4 py-3">
            <div className="h-3.5 w-1/2 animate-shimmer rounded" />
            <div className="h-2.5 w-1/3 animate-shimmer rounded opacity-70" />
          </div>
        </div>
      ))}
    </div>
  );
}
