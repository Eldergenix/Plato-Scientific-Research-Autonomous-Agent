"use client";

import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  AlertTriangle,
  ChevronDown,
  Download,
  Settings2,
  Wallet,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusIcon } from "@/components/views/status-icon";
import { MODELS_BY_ID } from "@/lib/models";
import type { Project, Provider, Stage, StageId } from "@/lib/types";
import { cn, formatCost, formatTokens } from "@/lib/utils";

/* -----------------------------------------------------------------------------
 * Types
 * ---------------------------------------------------------------------------*/

export interface CostMeterPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: Project;
}

/* -----------------------------------------------------------------------------
 * Constants
 * ---------------------------------------------------------------------------*/

const STAGE_ORDER: StageId[] = [
  "data",
  "idea",
  "literature",
  "method",
  "results",
  "paper",
  "referee",
];

const PROVIDER_DOT: Record<Provider, string> = {
  anthropic: "var(--color-status-orange)",
  openai: "var(--color-status-green-spec)",
  gemini: "var(--color-status-blue)",
  perplexity: "var(--color-status-purple)",
  semantic_scholar: "var(--color-status-teal)",
};

const BUDGET_KEY_PREFIX = "plato:budget:";
const STOP_KEY_PREFIX = "plato:budget-stop:";

/* -----------------------------------------------------------------------------
 * Cost derivation helpers
 * ---------------------------------------------------------------------------*/

/**
 * Estimate per-stage tokens and cost from the project. Real per-stage telemetry
 * is a Phase 4 deliverable; for now we deterministically distribute the
 * project's `totalTokens` and `totalCostCents` across stages in proportion to
 * each stage's `durationMs`. Stages with no duration get zero. If every stage
 * lacks a duration we fall back to even distribution across done stages.
 */
function deriveStageCosts(project: Project): Record<StageId, { tokens: number; costCents: number }> {
  const stages = project.stages;
  const durations = STAGE_ORDER.map((id) => stages[id]?.durationMs ?? 0);
  const totalDuration = durations.reduce((a, b) => a + b, 0);

  const out = {} as Record<StageId, { tokens: number; costCents: number }>;

  if (totalDuration > 0) {
    STAGE_ORDER.forEach((id, idx) => {
      const ratio = durations[idx] / totalDuration;
      out[id] = {
        tokens: Math.round(project.totalTokens * ratio),
        costCents: Math.round(project.totalCostCents * ratio),
      };
    });
    return out;
  }

  // Fallback: split evenly across stages that have a model assigned.
  const eligible = STAGE_ORDER.filter((id) => Boolean(stages[id]?.model));
  const denom = eligible.length || 1;
  STAGE_ORDER.forEach((id) => {
    const isEligible = eligible.includes(id);
    out[id] = {
      tokens: isEligible ? Math.round(project.totalTokens / denom) : 0,
      costCents: isEligible ? Math.round(project.totalCostCents / denom) : 0,
    };
  });
  return out;
}

/**
 * Build a 12-point sparkline series from stage durations, scaled into the
 * project's totalTokens. Stages with no duration contribute zero. Real
 * time-series aggregation is Phase 4.
 */
function buildSparklineSeries(project: Project): number[] {
  const series = new Array<number>(12).fill(0);
  const durations = STAGE_ORDER.map(
    (id) => project.stages[id]?.durationMs ?? 0,
  );
  const totalDuration = durations.reduce((a, b) => a + b, 0) || 1;

  let cursor = 0;
  STAGE_ORDER.forEach((_, stageIdx) => {
    const ratio = durations[stageIdx] / totalDuration;
    const span = Math.max(1, Math.round(ratio * 12));
    const stageTokens = project.totalTokens * ratio;
    for (let i = 0; i < span && cursor < 12; i += 1) {
      // Slight smoothing curve so the sparkline reads as ramped, not stepped.
      const smooth = 0.6 + 0.4 * Math.sin((i / Math.max(1, span - 1)) * Math.PI);
      series[cursor] = (stageTokens / span) * smooth;
      cursor += 1;
    }
  });
  return series;
}

/* -----------------------------------------------------------------------------
 * Subcomponents
 * ---------------------------------------------------------------------------*/

function MetricCard({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="flex-1 rounded-[8px] px-3 py-2"
      style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--color-border-card)",
      }}
    >
      <div className="font-label" style={{ marginBottom: 4 }}>
        {label}
      </div>
      {children}
    </div>
  );
}

function Sparkline({ series }: { series: number[] }) {
  const max = Math.max(...series, 1);
  const W = 60;
  const H = 40;
  const stepX = W / Math.max(1, series.length - 1);
  const points = series
    .map((v, i) => {
      const x = i * stepX;
      const y = H - (v / max) * (H - 4) - 2;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Token spend sparkline"
      className="block"
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--color-brand-interactive)"
        strokeWidth={1.25}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function StageRow({
  stage,
  costCents,
  tokens,
  totalCostCents,
}: {
  stage: Stage;
  costCents: number;
  tokens: number;
  totalCostCents: number;
}) {
  const pct =
    totalCostCents > 0 ? Math.min(100, (costCents / totalCostCents) * 100) : 0;
  const modelLabel = stage.model
    ? MODELS_BY_ID[stage.model]?.label ?? stage.model
    : "—";

  return (
    <div
      className="flex flex-col gap-1.5 py-2"
      style={{ borderBottom: "1px solid var(--color-border-standard)" }}
    >
      <div className="flex items-center gap-2 h-[28px]">
        <StatusIcon status={stage.status} size={14} />
        <span
          className="capitalize text-[13px] font-medium text-(--color-text-row-title)"
          style={{ flex: "0 0 auto" }}
        >
          {stage.label}
        </span>
        <div aria-hidden className="flex-1" />
        <span
          className="font-mono text-[12px] text-(--color-text-row-meta) truncate"
          style={{ maxWidth: 120 }}
          title={modelLabel}
        >
          {modelLabel}
        </span>
        <span className="font-mono text-[12px] text-(--color-text-row-meta) tabular-nums">
          {formatTokens(tokens)}
        </span>
        <span className="font-mono text-[13px] text-(--color-text-primary-strong) tabular-nums">
          {formatCost(costCents)}
        </span>
      </div>
      <div
        className="h-[3px] rounded-full overflow-hidden"
        style={{ background: "rgba(255,255,255,0.04)" }}
        aria-hidden
      >
        <div
          className="h-full rounded-full"
          style={{
            width: `${pct}%`,
            background: "var(--color-brand-interactive)",
            transition: "width 200ms ease-out",
          }}
        />
      </div>
    </div>
  );
}

function ModelBreakdown({
  rows,
}: {
  rows: Array<{ id: string; label: string; provider: Provider; costCents: number }>;
}) {
  return (
    <details
      className="rounded-[8px]"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <summary
        className="flex items-center gap-2 h-[36px] px-3 cursor-pointer list-none select-none"
        style={{ outline: "none" }}
      >
        <span className="font-label">By model</span>
        <span className="text-[12px] text-(--color-text-row-meta)">
          {rows.length} {rows.length === 1 ? "model" : "models"}
        </span>
        <div aria-hidden className="flex-1" />
        <ChevronDown
          size={14}
          strokeWidth={1.5}
          className="text-(--color-text-tertiary-spec) transition-transform"
        />
      </summary>
      <div
        className="flex flex-col"
        style={{ borderTop: "1px solid var(--color-border-standard)" }}
      >
        {rows.length === 0 ? (
          <div className="px-3 py-3 text-[12px] text-(--color-text-row-meta)">
            No model usage recorded yet.
          </div>
        ) : (
          rows.map((row) => (
            <div
              key={row.id}
              className="flex items-center gap-2 h-[32px] px-3"
              style={{ borderTop: "1px solid var(--color-border-standard)" }}
            >
              <span
                aria-hidden
                className="rounded-full"
                style={{
                  width: 8,
                  height: 8,
                  background: PROVIDER_DOT[row.provider],
                  flex: "none",
                }}
              />
              <span className="text-[12px] text-(--color-text-row-title) truncate">
                {row.label}
              </span>
              <div aria-hidden className="flex-1" />
              <span className="font-mono text-[12px] text-(--color-text-row-meta) tabular-nums">
                {formatCost(row.costCents)}
              </span>
            </div>
          ))
        )}
      </div>
    </details>
  );
}

function BudgetCard({
  projectId,
  spentCents,
}: {
  projectId: string;
  spentCents: number;
}) {
  const [capCents, setCapCents] = React.useState<number | null>(null);
  const [stopOnOverrun, setStopOnOverrun] = React.useState(false);

  // Hydrate from localStorage on mount / project change.
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(`${BUDGET_KEY_PREFIX}${projectId}`);
      setCapCents(raw ? Number.parseInt(raw, 10) || null : null);
      const stop = window.localStorage.getItem(`${STOP_KEY_PREFIX}${projectId}`);
      setStopOnOverrun(stop === "1");
    } catch {
      /* ignore quota / SSR */
    }
  }, [projectId]);

  const persistCap = (next: number | null) => {
    setCapCents(next);
    if (typeof window === "undefined") return;
    try {
      const key = `${BUDGET_KEY_PREFIX}${projectId}`;
      if (next == null) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, String(next));
    } catch {
      /* ignore */
    }
  };

  const persistStop = (next: boolean) => {
    setStopOnOverrun(next);
    if (typeof window === "undefined") return;
    try {
      const key = `${STOP_KEY_PREFIX}${projectId}`;
      if (next) window.localStorage.setItem(key, "1");
      else window.localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  };

  const handleSetCap = () => {
    if (typeof window === "undefined") return;
    const current = capCents != null ? (capCents / 100).toFixed(2) : "";
    const input = window.prompt("Budget cap in USD", current);
    if (input == null) return;
    const trimmed = input.trim();
    if (trimmed === "") {
      persistCap(null);
      return;
    }
    const parsed = Number.parseFloat(trimmed);
    if (!Number.isFinite(parsed) || parsed < 0) return;
    persistCap(Math.round(parsed * 100));
  };

  const pct =
    capCents && capCents > 0 ? Math.min(100, (spentCents / capCents) * 100) : 0;
  const barColor =
    pct >= 95
      ? "var(--color-status-red-spec)"
      : pct >= 80
        ? "var(--color-status-amber-spec)"
        : "var(--color-brand-interactive)";

  return (
    <div className="surface-card" style={{ padding: 12 }}>
      <div className="flex items-center gap-2" style={{ marginBottom: 8 }}>
        <Wallet size={14} strokeWidth={1.5} className="text-(--color-text-row-meta)" />
        <span className="font-label">Budget</span>
        <div aria-hidden className="flex-1" />
        {pct >= 80 && capCents ? (
          <AlertTriangle
            size={13}
            strokeWidth={1.75}
            className={pct >= 95 ? "text-(--color-status-red-spec)" : "text-(--color-status-amber-spec)"}
          />
        ) : null}
      </div>

      <div className="flex items-baseline gap-2" style={{ marginBottom: 10 }}>
        <span className="font-mono text-[16px] tabular-nums text-(--color-text-primary-strong)">
          {capCents != null ? formatCost(capCents) : "No cap set"}
        </span>
        {capCents != null ? (
          <span className="font-mono text-[12px] text-(--color-text-row-meta) tabular-nums">
            ({formatCost(spentCents)} spent · {pct.toFixed(0)}%)
          </span>
        ) : null}
      </div>

      {capCents != null ? (
        <div
          className="h-[4px] rounded-full overflow-hidden"
          style={{
            background: "rgba(255,255,255,0.04)",
            marginBottom: 10,
          }}
          aria-hidden
        >
          <div
            className="h-full rounded-full"
            style={{
              width: `${pct}%`,
              background: barColor,
              transition: "width 200ms ease-out",
            }}
          />
        </div>
      ) : null}

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={handleSetCap}>
          <Settings2 size={12} strokeWidth={1.5} />
          {capCents != null ? "Edit cap" : "Set cap"}
        </Button>
        {capCents != null ? (
          <Button
            variant="subtle"
            size="sm"
            onClick={() => persistCap(null)}
          >
            Remove cap
          </Button>
        ) : null}
      </div>

      {capCents != null ? (
        <label
          className="flex items-center gap-2 cursor-pointer text-[12px] text-(--color-text-row-meta)"
          style={{ marginTop: 10 }}
        >
          <input
            type="checkbox"
            checked={stopOnOverrun}
            onChange={(e) => persistStop(e.target.checked)}
            className="accent-(--color-brand-interactive)"
          />
          Stop on overrun
        </label>
      ) : null}
    </div>
  );
}

/* -----------------------------------------------------------------------------
 * CostMeterPanel
 * ---------------------------------------------------------------------------*/

export function CostMeterPanel({ open, onOpenChange, project }: CostMeterPanelProps) {
  const stageCosts = React.useMemo(() => deriveStageCosts(project), [project]);
  const sparkline = React.useMemo(() => buildSparklineSeries(project), [project]);

  const stages = STAGE_ORDER.map((id) => project.stages[id]).filter(
    (s): s is Stage => Boolean(s),
  );

  const activeModelIds = React.useMemo(() => {
    const ids = new Set<string>();
    stages.forEach((s) => {
      if (s.model) ids.add(s.model);
    });
    return Array.from(ids);
  }, [stages]);

  const modelRows = React.useMemo(() => {
    const totals = new Map<string, number>();
    STAGE_ORDER.forEach((id) => {
      const stage = project.stages[id];
      if (!stage?.model) return;
      const prev = totals.get(stage.model) ?? 0;
      totals.set(stage.model, prev + stageCosts[id].costCents);
    });
    return Array.from(totals.entries())
      .map(([id, costCents]) => {
        const def = MODELS_BY_ID[id];
        return {
          id,
          label: def?.label ?? id,
          provider: (def?.provider ?? "openai") as Provider,
          costCents,
        };
      })
      .sort((a, b) => b.costCents - a.costCents);
  }, [project.stages, stageCosts]);

  const handleExport = () => {
    if (typeof window === "undefined") return;
    const header = "stage,model,tokens,cost_usd\n";
    const lines = STAGE_ORDER.map((id) => {
      const s = project.stages[id];
      const c = stageCosts[id];
      const cost = (c.costCents / 100).toFixed(4);
      const model = s?.model ?? "";
      return `${id},${model},${c.tokens},${cost}`;
    });
    const csv = header + lines.join("\n") + "\n";
    const url = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${project.id}-cost-breakdown.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0"
          style={{ background: "rgba(0,0,0,0.4)" }}
        />
        <Dialog.Content
          aria-describedby={undefined}
          className={cn(
            "fixed top-0 right-0 bottom-0 z-50 flex flex-col",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right",
            "duration-200",
          )}
          style={{
            width: 480,
            maxWidth: "100vw",
            background: "var(--color-bg-card)",
            borderLeft: "1px solid var(--color-border-card)",
            boxShadow: "var(--shadow-card)",
          }}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between"
            style={{
              height: 44,
              padding: "0 16px",
              borderBottom: "1px solid var(--color-border-standard)",
              flex: "none",
            }}
          >
            <div className="flex items-baseline gap-2 min-w-0">
              <Dialog.Title
                className="text-[14px] text-(--color-text-primary-strong) truncate"
                style={{ fontWeight: 510 }}
              >
                Cost meter
              </Dialog.Title>
              <span
                className="text-[12px] truncate"
                style={{ color: "#949496" }}
                title={project.name}
              >
                {project.name}
              </span>
            </div>
            <Dialog.Close asChild>
              <Button variant="subtle" size="iconSm" aria-label="Close cost meter">
                <X size={14} strokeWidth={1.5} />
              </Button>
            </Dialog.Close>
          </div>

          {/* Scrollable body */}
          <div className="flex-1 overflow-y-auto">
            {/* Top metrics row */}
            <div
              style={{
                padding: 16,
                borderBottom: "1px solid var(--color-border-standard)",
              }}
            >
              <div className="flex items-stretch gap-2">
                <MetricCard label="Total">
                  <div
                    className="font-mono tabular-nums text-(--color-text-primary-strong)"
                    style={{ fontSize: 24, fontWeight: 500, lineHeight: 1.1 }}
                  >
                    {formatCost(project.totalCostCents)}
                  </div>
                </MetricCard>
                <MetricCard label="Tokens">
                  <div
                    className="font-mono tabular-nums text-(--color-text-primary-strong)"
                    style={{ fontSize: 18, fontWeight: 500, lineHeight: 1.2 }}
                  >
                    {formatTokens(project.totalTokens)}
                  </div>
                </MetricCard>
                <MetricCard label="Active models">
                  <div
                    className="font-mono tabular-nums text-(--color-text-primary-strong)"
                    style={{ fontSize: 18, fontWeight: 500, lineHeight: 1.2 }}
                  >
                    {activeModelIds.length}
                  </div>
                  <div className="flex flex-wrap gap-1" style={{ marginTop: 6 }}>
                    {activeModelIds.length === 0 ? (
                      <span className="text-[11px] text-(--color-text-row-meta)">
                        none
                      </span>
                    ) : (
                      activeModelIds.map((id) => (
                        <span
                          key={id}
                          className="font-mono text-[10px] px-1.5 py-0.5 rounded-full"
                          style={{
                            background: "var(--color-bg-pill-inactive)",
                            color: "var(--color-text-row-meta)",
                            border: "1px solid var(--color-border-pill)",
                          }}
                          title={MODELS_BY_ID[id]?.label ?? id}
                        >
                          {id}
                        </span>
                      ))
                    )}
                  </div>
                </MetricCard>
              </div>
              <div
                className="flex items-end justify-between"
                style={{ marginTop: 12, height: 60 }}
              >
                <span className="font-label">Tokens over time</span>
                <Sparkline series={sparkline} />
              </div>
            </div>

            {/* By stage */}
            <div style={{ padding: 16 }}>
              <div
                className="flex items-center"
                style={{ marginBottom: 8, height: 20 }}
              >
                <span className="font-label">By stage</span>
              </div>
              <div className="flex flex-col">
                {stages.map((stage) => (
                  <StageRow
                    key={stage.id}
                    stage={stage}
                    costCents={stageCosts[stage.id]?.costCents ?? 0}
                    tokens={stageCosts[stage.id]?.tokens ?? 0}
                    totalCostCents={project.totalCostCents}
                  />
                ))}
              </div>
            </div>

            {/* By model */}
            <div style={{ padding: "0 16px 16px" }}>
              <ModelBreakdown rows={modelRows} />
            </div>

            {/* Budget cap */}
            <div style={{ padding: "0 16px 16px" }}>
              <BudgetCard
                projectId={project.id}
                spentCents={project.totalCostCents}
              />
            </div>
          </div>

          {/* Footer */}
          <div
            className="flex items-center gap-1.5"
            style={{
              padding: "12px 16px",
              borderTop: "1px solid var(--color-border-standard)",
              flex: "none",
            }}
          >
            <Button variant="subtle" size="sm" onClick={handleExport}>
              <Download size={12} strokeWidth={1.5} />
              Export breakdown CSV
            </Button>
            <div aria-hidden className="flex-1" />
            <Dialog.Close asChild>
              <Button variant="subtle" size="sm">
                Close
              </Button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/* -----------------------------------------------------------------------------
 * Hook
 * ---------------------------------------------------------------------------*/

export function useCostMeter() {
  const [open, setOpen] = React.useState(false);
  return {
    open,
    openMeter: () => setOpen(true),
    closeMeter: () => setOpen(false),
    onOpenChange: setOpen,
  };
}
