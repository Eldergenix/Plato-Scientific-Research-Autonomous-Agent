"use client";

import * as React from "react";
import { Award, BarChart3, Layers, Network, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  CitationGraphPayload,
  CitationNode,
} from "./citation-graph-view";

interface MetricCardProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  testId: string;
}

function MetricCard({ label, value, icon, testId }: MetricCardProps) {
  return (
    <div
      className="surface-linear-card flex items-center gap-3 px-4 py-3"
      data-testid={testId}
    >
      <span
        aria-hidden
        className="flex size-9 items-center justify-center rounded-full bg-(--color-bg-pill-inactive) text-(--color-text-tertiary-spec)"
      >
        {icon}
      </span>
      <div className="flex flex-col">
        <span className="font-label">{label}</span>
        <span
          className="font-mono text-(--color-text-primary-strong) tabular-nums"
          style={{ fontSize: 22, fontWeight: 510, lineHeight: 1.1 }}
        >
          {value}
        </span>
      </div>
    </div>
  );
}

interface RankedNode {
  node: CitationNode;
  count: number;
}

function rankByInDegree(payload: CitationGraphPayload): RankedNode[] {
  const inDegree = new Map<string, number>();
  for (const e of payload.edges) {
    inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + 1);
  }
  return payload.expanded
    .map((node) => ({ node, count: inDegree.get(node.id) ?? 0 }))
    .filter((r) => r.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
}

function densestSeed(payload: CitationGraphPayload): RankedNode | null {
  const outDegree = new Map<string, number>();
  for (const e of payload.edges) {
    outDegree.set(e.from, (outDegree.get(e.from) ?? 0) + 1);
  }
  let best: RankedNode | null = null;
  for (const seed of payload.seeds) {
    const c = outDegree.get(seed.id) ?? 0;
    if (c === 0) continue;
    if (!best || c > best.count) best = { node: seed, count: c };
  }
  return best;
}

function RankedRow({
  rank,
  ranked,
  unit,
}: {
  rank: number;
  ranked: RankedNode;
  unit: string;
}) {
  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5"
      style={{ borderBottom: "1px solid var(--color-border-standard)" }}
    >
      <span
        className={cn(
          "flex size-6 flex-none items-center justify-center rounded-full",
          "bg-(--color-bg-pill-inactive) font-mono text-[11px] text-(--color-text-row-meta)",
        )}
        aria-label={`rank ${rank}`}
      >
        {rank}
      </span>
      <span
        className="flex-1 truncate text-[13px] text-(--color-text-row-title)"
        title={ranked.node.title}
      >
        {ranked.node.title}
      </span>
      <span className="font-mono text-[12px] tabular-nums text-(--color-text-primary-strong)">
        {ranked.count} {unit}
      </span>
    </div>
  );
}

export function CitationStats({ payload }: { payload: CitationGraphPayload }) {
  const topCited = React.useMemo(() => rankByInDegree(payload), [payload]);
  const densest = React.useMemo(() => densestSeed(payload), [payload]);

  return (
    <div className="flex flex-col gap-4" data-testid="citation-stats">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <MetricCard
          label="Seeds"
          value={payload.stats.seed_count}
          icon={<Layers size={16} strokeWidth={1.5} />}
          testId="stat-seed-count"
        />
        <MetricCard
          label="Expanded"
          value={payload.stats.expanded_count}
          icon={<Network size={16} strokeWidth={1.5} />}
          testId="stat-expanded-count"
        />
        <MetricCard
          label="Edges"
          value={payload.stats.edge_count}
          icon={<BarChart3 size={16} strokeWidth={1.5} />}
          testId="stat-edge-count"
        />
        <MetricCard
          label="Duplicates filtered"
          value={payload.stats.duplicates_filtered}
          icon={<Trash2 size={16} strokeWidth={1.5} />}
          testId="stat-duplicates-filtered"
        />
        <MetricCard
          label="Densest seed (out-deg)"
          value={densest?.count ?? 0}
          icon={<Award size={16} strokeWidth={1.5} />}
          testId="stat-densest-seed"
        />
      </div>

      <section
        className="surface-linear-card overflow-hidden"
        data-testid="top-cited-section"
      >
        <header
          className="flex items-center gap-2 px-4 py-2.5"
          style={{
            borderBottom: "1px solid var(--color-border-standard)",
            background: "rgba(255,255,255,0.02)",
          }}
        >
          <Award size={14} strokeWidth={1.5} className="text-(--color-status-amber-spec)" />
          <span className="font-label">Most-cited expanded works</span>
        </header>
        {topCited.length === 0 ? (
          <div className="px-4 py-6 text-[12px] text-(--color-text-row-meta)">
            No incoming edges in the expansion set.
          </div>
        ) : (
          topCited.map((r, idx) => (
            <RankedRow
              key={r.node.id}
              rank={idx + 1}
              ranked={r}
              unit="incoming"
            />
          ))
        )}
      </section>

      {densest ? (
        <section
          className="surface-linear-card overflow-hidden"
          data-testid="densest-seed-section"
        >
          <header
            className="flex items-center gap-2 px-4 py-2.5"
            style={{
              borderBottom: "1px solid var(--color-border-standard)",
              background: "rgba(255,255,255,0.02)",
            }}
          >
            <Network size={14} strokeWidth={1.5} className="text-(--color-status-purple)" />
            <span className="font-label">Densest seed</span>
          </header>
          <RankedRow rank={1} ranked={densest} unit="outgoing" />
        </section>
      ) : null}
    </div>
  );
}
