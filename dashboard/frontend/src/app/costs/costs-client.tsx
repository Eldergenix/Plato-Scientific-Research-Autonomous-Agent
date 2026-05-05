"use client";

import * as React from "react";
import {
  Wallet,
  TrendingUp,
  Download,
  ArrowUpDown,
  ChevronUp,
  ChevronDown,
  Plus,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { formatCost, formatTokens, cn } from "@/lib/utils";

type SortKey = "name" | "createdAt" | "stagesRun" | "tokens" | "cost";
type SortDir = "asc" | "desc";
type TabId = "project" | "model" | "day";

interface BudgetCap {
  projectId: string;
  projectName: string;
  capUsd: number;
}

// Legacy localStorage key. Kept only for one-time migration: any cap a user
// wrote before the server-side caps API landed gets pushed to the backend on
// first mount, then the localStorage entry is cleared. New writes go straight
// through api.setCostCaps so caps are actually enforced server-side at
// run_stage (server.py:414-463).
const LEGACY_CAPS_KEY = "plato.budgetCaps.v1";
const GRID_COLS = "minmax(0,2.4fr) 1fr 1fr 1fr 1fr 36px";

async function fetchCapsFromBackend(projects: Project[]): Promise<BudgetCap[]> {
  // Fan out api.getCostCaps per project; backend is one tiny meta.json read
  // each, projects are typically <50 per user, so a single Promise.all stays
  // well under one second.
  const results = await Promise.all(
    projects.map(async (p) => {
      try {
        const state = await api.getCostCaps(p.id);
        if (state?.budget_cents != null && state.budget_cents > 0) {
          return {
            projectId: p.id,
            projectName: p.name,
            capUsd: state.budget_cents / 100,
          } satisfies BudgetCap;
        }
      } catch {
        // 404 / not configured — treat as no cap.
      }
      return null;
    }),
  );
  return results.filter((c): c is BudgetCap => c !== null);
}

async function migrateLegacyCaps(): Promise<void> {
  if (typeof window === "undefined") return;
  const raw = window.localStorage.getItem(LEGACY_CAPS_KEY);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      window.localStorage.removeItem(LEGACY_CAPS_KEY);
      return;
    }
    await Promise.all(
      parsed
        .filter(
          (c: unknown): c is BudgetCap =>
            typeof (c as BudgetCap)?.projectId === "string" &&
            typeof (c as BudgetCap)?.capUsd === "number" &&
            (c as BudgetCap).capUsd > 0,
        )
        .map((c) =>
          api
            .setCostCaps(c.projectId, {
              budget_cents: Math.round(c.capUsd * 100),
              stop_on_exceed: true,
            })
            .catch(() => {
              // Best-effort migration; surface failures via console for debug
              // but don't block the page load.
            }),
        ),
    );
  } catch {
    // Malformed cache — drop it.
  } finally {
    window.localStorage.removeItem(LEGACY_CAPS_KEY);
  }
}

function stagesDoneCount(p: Project): number {
  return Object.values(p.stages).filter((s) => s.status === "done").length;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

// Mock 7-point sparkline for the "this week" card. Real time-series
// aggregation lands in Phase 4 via /api/v1/projects/{pid}/usage.
function buildSparklinePath(points: number[], w = 60, h = 16): string {
  if (points.length === 0) return "";
  const max = Math.max(...points, 1);
  const step = w / Math.max(points.length - 1, 1);
  return points
    .map((v, i) => {
      const x = i * step;
      const y = h - (v / max) * (h - 2) - 1;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export default function CostsPage() {
  const [projects, setProjects] = React.useState<Project[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState<TabId>("project");
  const [sortKey, setSortKey] = React.useState<SortKey>("cost");
  const [sortDir, setSortDir] = React.useState<SortDir>("desc");
  const [caps, setCaps] = React.useState<BudgetCap[]>([]);
  const [capProjectId, setCapProjectId] = React.useState("");
  const [capValue, setCapValue] = React.useState("");

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await api.listProjects();
        if (cancelled) return;
        setProjects(list);
        // One-time migration of any pre-iter-26 localStorage caps to the
        // server, then load the canonical state from the backend.
        await migrateLegacyCaps();
        if (cancelled) return;
        const serverCaps = await fetchCapsFromBackend(list);
        if (!cancelled) setCaps(serverCaps);
      } catch (e: unknown) {
        if (cancelled) return;
        console.error("listProjects failed", e);
        setError(e instanceof Error ? e.message : "Failed to load projects");
        setProjects([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const totalCents = (projects ?? []).reduce((s, p) => s + p.totalCostCents, 0);
  const totalTokensThisMonth = (projects ?? []).reduce((s, p) => s + p.totalTokens, 0);
  // Mock weekly/monthly slices — backend usage aggregation is Phase 4.
  const monthCents = Math.round(totalCents * 0.6);
  const weekCents = Math.round(totalCents * 0.2);
  const sparklinePoints = React.useMemo(() => {
    const seed = Math.max(weekCents, 1);
    return [0.4, 0.7, 0.55, 0.85, 0.6, 0.95, 1.0].map((f) => f * seed);
  }, [weekCents]);

  const sorted = React.useMemo(() => {
    if (!projects) return null;
    const dir = sortDir === "asc" ? 1 : -1;
    return [...projects].sort((a, b) => {
      switch (sortKey) {
        case "name":
          return a.name.localeCompare(b.name) * dir;
        case "createdAt":
          return (new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()) * dir;
        case "stagesRun":
          return (stagesDoneCount(a) - stagesDoneCount(b)) * dir;
        case "tokens":
          return (a.totalTokens - b.totalTokens) * dir;
        case "cost":
        default:
          return (a.totalCostCents - b.totalCostCents) * dir;
      }
    });
  }, [projects, sortKey, sortDir]);

  const onSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir(key === "name" || key === "createdAt" ? "asc" : "desc");
    }
  };

  const onAddCap = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const dollars = parseFloat(capValue);
    if (!capProjectId || !Number.isFinite(dollars) || dollars <= 0) return;
    const proj = (projects ?? []).find((p) => p.id === capProjectId);
    if (!proj) return;
    // Optimistic update; server-side persistence is the source of truth.
    const next = [
      ...caps.filter((c) => c.projectId !== capProjectId),
      { projectId: proj.id, projectName: proj.name, capUsd: dollars },
    ];
    setCaps(next);
    setCapValue("");
    setCapProjectId("");
    try {
      await api.setCostCaps(proj.id, {
        budget_cents: Math.round(dollars * 100),
        stop_on_exceed: true,
      });
    } catch (err) {
      console.error("setCostCaps failed", err);
      // Roll back on failure so the UI doesn't lie.
      setCaps((prev) => prev.filter((c) => c.projectId !== proj.id));
      setError(err instanceof Error ? err.message : "Failed to save cap");
    }
  };

  const onRemoveCap = async (projectId: string) => {
    const before = caps;
    setCaps(caps.filter((c) => c.projectId !== projectId));
    try {
      await api.setCostCaps(projectId, {
        budget_cents: null,
        stop_on_exceed: false,
      });
    } catch (err) {
      console.error("setCostCaps remove failed", err);
      setCaps(before);
      setError(err instanceof Error ? err.message : "Failed to remove cap");
    }
  };

  const onExport = (p: Project) => {
    const csv = [
      "id,name,created_at,stages_done,total_tokens,total_cost_cents",
      [p.id, JSON.stringify(p.name), p.createdAt, stagesDoneCount(p), p.totalTokens, p.totalCostCents].join(","),
    ].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${p.id}-usage.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const isLoading = projects === null;
  const isEmpty = !isLoading && (projects?.length ?? 0) === 0;

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="surface-linear-card flex items-center justify-between gap-4 px-4" style={{ height: 64 }}>
          <h1
            className="text-(--color-text-primary-strong)"
            style={{ fontFamily: "Inter, var(--font-sans)", fontWeight: 510, fontSize: 24, letterSpacing: "-0.5px" }}
          >
            Costs
          </h1>
          <div className="flex items-stretch gap-3">
            <MetricCard label="This week" value={formatCost(weekCents)} sparkline={sparklinePoints} />
            <MetricCard label="This month" value={formatCost(monthCents)} />
            <MetricCard label="All-time" value={formatCost(totalCents)} />
            <MetricCard
              label="Tokens this month"
              value={formatTokens(totalTokensThisMonth)}
              icon={<TrendingUp className="size-3" />}
            />
          </div>
        </header>

        <div className="flex items-center gap-1">
          {(["project", "model", "day"] as const).map((t) => (
            <button
              key={t}
              className="tab-pill"
              data-state={tab === t ? "active" : undefined}
              onClick={() => setTab(t)}
            >
              {t === "project" ? "By project" : t === "model" ? "By model" : "By day"}
            </button>
          ))}
        </div>

        {error && (
          <div className="surface-linear-card px-4 py-3 text-[13px] text-(--color-status-red)">{error}</div>
        )}

        {tab !== "project" ? (
          <section className="surface-linear-card flex items-center justify-between gap-3 p-6">
            <div className="text-[13px] text-(--color-text-tertiary-spec)">
              Coming soon — {tab === "model" ? "per-model" : "per-day"} aggregation ships in Phase 4.
            </div>
            <Pill tone="amber">TODO</Pill>
          </section>
        ) : isEmpty ? (
          <EmptyState />
        ) : (
          <section className="surface-linear-card overflow-hidden">
            <div
              className="grid items-center gap-3 border-b border-(--color-border-card) px-4"
              style={{ height: 36, gridTemplateColumns: GRID_COLS }}
            >
              <SortHeader label="Project" active={sortKey === "name"} dir={sortDir} onClick={() => onSort("name")} />
              <SortHeader label="Created" active={sortKey === "createdAt"} dir={sortDir} onClick={() => onSort("createdAt")} />
              <SortHeader label="Stages run" active={sortKey === "stagesRun"} dir={sortDir} onClick={() => onSort("stagesRun")} />
              <SortHeader label="Tokens" active={sortKey === "tokens"} dir={sortDir} onClick={() => onSort("tokens")} />
              <SortHeader label="Cost" active={sortKey === "cost"} dir={sortDir} onClick={() => onSort("cost")} align="right" />
              <span />
            </div>

            {isLoading
              ? [0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="grid items-center gap-3 border-b border-(--color-border-card) px-4 last:border-b-0"
                    style={{ height: 48, gridTemplateColumns: GRID_COLS }}
                  >
                    <SkeletonBar w="60%" />
                    <SkeletonBar w="40%" />
                    <SkeletonBar w="30%" />
                    <SkeletonBar w="40%" />
                    <SkeletonBar w="30%" align="right" />
                    <span />
                  </div>
                ))
              : (sorted ?? []).map((p) => (
                  <div
                    key={p.id}
                    className="grid items-center gap-3 border-b border-(--color-border-card) px-4 last:border-b-0 hover:bg-(--color-ghost-bg-hover)"
                    style={{ height: 48, gridTemplateColumns: GRID_COLS }}
                  >
                    <div className="min-w-0">
                      <div className="truncate text-[13px] text-(--color-text-row-title)">{p.name}</div>
                      <div className="truncate font-mono text-[12px] text-[#949496]">{p.id}</div>
                    </div>
                    <div className="text-[12px] text-[#949496]">{formatDate(p.createdAt)}</div>
                    <div className="text-[13px] text-(--color-text-secondary-spec)">{stagesDoneCount(p)} / 7</div>
                    <div className="text-[13px] text-(--color-text-secondary-spec)">{formatTokens(p.totalTokens)}</div>
                    <div className="text-right font-mono text-[13px] tabular-nums text-(--color-text-primary-strong)">
                      {formatCost(p.totalCostCents)}
                    </div>
                    <div className="flex justify-end">
                      <Button
                        variant="subtle"
                        size="sm"
                        aria-label={`Export ${p.name} usage`}
                        onClick={() => onExport(p)}
                      >
                        <Download className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
          </section>
        )}

        {!isEmpty && (
          <section className="surface-linear-card flex flex-col gap-4 p-5">
            <div>
              <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">Project budget caps</h2>
              <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
                Caps are persisted server-side per project; the dashboard worker stops a stage that would exceed the cap.
              </p>
            </div>

            <form className="flex flex-wrap items-center gap-2 text-[13px]" onSubmit={onAddCap}>
              <span className="text-(--color-text-tertiary-spec)">Cap each project at</span>
              <select
                id="cap-project-select"
                name="cap-project"
                aria-label="Project to cap"
                value={capProjectId}
                onChange={(e) => setCapProjectId(e.target.value)}
                className="rounded-[6px] border border-[#262628] bg-[#141415] px-2 py-1.5 text-[12px] text-(--color-text-primary) focus:border-(--color-brand-indigo) focus:outline-none"
              >
                <option value="">Select project…</option>
                {(projects ?? []).map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <input
                id="cap-value-input"
                name="cap-value"
                aria-label="Cap value in USD"
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={capValue}
                onChange={(e) => setCapValue(e.target.value)}
                placeholder="0.00"
                className={cn(
                  "w-24 rounded-[6px] border border-[#262628] bg-[#141415] px-2 py-1.5 font-mono text-[12px]",
                  "text-(--color-text-primary) placeholder:text-(--color-text-quaternary-spec)",
                  "focus:border-(--color-brand-indigo) focus:outline-none",
                )}
              />
              <span className="text-(--color-text-tertiary-spec)">USD</span>
              <span className="text-(--color-text-quaternary-spec)">(optional)</span>
              <Button type="submit" variant="primary" size="sm" disabled={!capProjectId || !capValue}>
                <Plus className="size-3" /> Save
              </Button>
            </form>

            {caps.length > 0 && (
              <div className="flex flex-col gap-1">
                {caps.map((c) => (
                  <div
                    key={c.projectId}
                    className="flex items-center justify-between rounded-[6px] border border-(--color-border-card) bg-(--color-bg-pill-inactive) px-3 py-2"
                  >
                    <div className="flex flex-col">
                      <span className="text-[13px] text-(--color-text-row-title)">{c.projectName}</span>
                      <span className="font-mono text-[11px] text-[#949496]">{c.projectId}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-[13px] tabular-nums text-(--color-text-primary-strong)">
                        ${c.capUsd.toFixed(2)}
                      </span>
                      <Button
                        variant="subtle"
                        size="sm"
                        aria-label={`Remove cap for ${c.projectName}`}
                        onClick={() => onRemoveCap(c.projectId)}
                      >
                        <X className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  sparkline,
  icon,
}: {
  label: string;
  value: string;
  sparkline?: number[];
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col justify-center rounded-[8px] border border-(--color-border-card) bg-(--color-bg-pill-inactive) px-3 py-1.5">
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-(--color-text-tertiary-spec)">
        {icon}
        {label}
      </div>
      <div className="flex items-center gap-2">
        <span className="font-mono text-[14px] tabular-nums text-(--color-text-primary-strong)">{value}</span>
        {sparkline && sparkline.length > 0 && (
          <svg width={60} height={16} viewBox="0 0 60 16" className="text-(--color-brand-interactive)" aria-hidden>
            <path
              d={buildSparklinePath(sparkline)}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.25}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </div>
    </div>
  );
}

function SortHeader({
  label,
  active,
  dir,
  onClick,
  align = "left",
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: "left" | "right";
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center gap-1 text-[11px] font-[510] uppercase tracking-wider",
        "hover:text-(--color-text-primary-strong)",
        active ? "text-(--color-text-primary-strong)" : "text-(--color-text-tertiary-spec)",
        align === "right" && "justify-end",
      )}
      onClick={onClick}
    >
      <span>{label}</span>
      {active ? (
        dir === "asc" ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />
      ) : (
        <ArrowUpDown className="size-3 opacity-50" />
      )}
    </button>
  );
}

function SkeletonBar({ w, align = "left" }: { w: string; align?: "left" | "right" }) {
  return (
    <div className={cn("flex", align === "right" && "justify-end")}>
      <div className="animate-shimmer h-3 rounded-[4px]" style={{ width: w }} />
    </div>
  );
}

function EmptyState() {
  return (
    <section className="surface-linear-card flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <Wallet className="size-10" style={{ color: "#62666d" }} />
      <p className="max-w-md text-[13px] text-(--color-text-tertiary-spec)">
        No projects yet — costs will appear here when you create your first run.
      </p>
      <a href="/">
        <Button variant="primary" size="md">
          <Plus className="size-3.5" /> Create project
        </Button>
      </a>
    </section>
  );
}
