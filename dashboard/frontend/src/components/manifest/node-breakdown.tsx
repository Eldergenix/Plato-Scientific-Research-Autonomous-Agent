"use client";

import * as React from "react";
import { Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import type { NodeTelemetry, RunManifest } from "./manifest-panel";

type SortKey = "node" | "calls" | "ti" | "to" | "cost_usd" | "pct";
type SortDir = "asc" | "desc";

interface NodeRow {
  node: string;
  calls: number;
  ti: number;
  to: number;
  cost_usd: number;
  pct: number;
}

function buildRows(manifest: RunManifest): NodeRow[] {
  const perNode = manifest.tokens_per_node ?? {};
  const promptHashes = manifest.prompt_hashes ?? {};

  // Union node names from both fields so legacy runs (prompt_hashes only)
  // still surface a row, even without telemetry numbers.
  const names = new Set<string>([
    ...Object.keys(perNode),
    ...Object.keys(promptHashes),
  ]);

  const totalCost = Object.values(perNode).reduce(
    (acc, n) => acc + (n.cost_usd ?? 0),
    0,
  );

  return Array.from(names).map((node) => {
    const t: NodeTelemetry | undefined = perNode[node];
    const cost = t?.cost_usd ?? 0;
    return {
      node,
      calls: t?.calls ?? 0,
      ti: t?.ti ?? 0,
      to: t?.to ?? 0,
      cost_usd: cost,
      pct: totalCost > 0 ? (cost / totalCost) * 100 : 0,
    };
  });
}

function formatTokens(n: number): string {
  if (n === 0) return "—";
  if (n < 1000) return `${n}`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

function formatCost(usd: number): string {
  if (usd === 0) return "—";
  return `$${usd.toFixed(4)}`;
}

function formatPct(pct: number): string {
  if (pct === 0) return "—";
  return `${pct.toFixed(1)}%`;
}

function compareRows(a: NodeRow, b: NodeRow, key: SortKey, dir: SortDir): number {
  const sign = dir === "asc" ? 1 : -1;
  if (key === "node") return sign * a.node.localeCompare(b.node);
  return sign * ((a[key] as number) - (b[key] as number));
}

export function NodeBreakdown({ manifest }: { manifest: RunManifest }) {
  const [sortKey, setSortKey] = React.useState<SortKey>("cost_usd");
  const [sortDir, setSortDir] = React.useState<SortDir>("desc");

  const rows = React.useMemo(() => {
    const all = buildRows(manifest);
    return [...all].sort((a, b) => compareRows(a, b, sortKey, sortDir));
  }, [manifest, sortKey, sortDir]);

  const hasTelemetry =
    manifest.tokens_per_node !== undefined &&
    Object.keys(manifest.tokens_per_node).length > 0;

  const onSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      // Cost / token columns default to desc (biggest offender first); the
      // node-name column defaults to asc (alphabetical).
      setSortDir(key === "node" ? "asc" : "desc");
    }
  };

  if (rows.length === 0) {
    return (
      <section
        className="surface-linear-card px-4 py-4"
        data-testid="node-breakdown-empty"
        style={{ border: "1px solid var(--color-border-card)" }}
      >
        <div className="font-label" style={{ marginBottom: 6 }}>
          Per-node breakdown
        </div>
        <p className="text-[12px] text-(--color-text-row-meta)">
          No per-node telemetry recorded for this run.
        </p>
      </section>
    );
  }

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="node-breakdown"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="flex items-center gap-3">
          <Layers size={16} className="text-(--color-text-tertiary)" />
          <h2
            className="text-(--color-text-primary-strong) text-[15px]"
            style={{ fontWeight: 510 }}
          >
            Per-node breakdown
          </h2>
        </div>
        <span className="text-[11px] text-(--color-text-row-meta)">
          {rows.length} {rows.length === 1 ? "node" : "nodes"}
        </span>
      </header>

      {!hasTelemetry ? (
        <div
          className="px-4 py-2 text-[12px] text-(--color-text-row-meta)"
          style={{ borderBottom: "1px solid var(--color-border-standard)" }}
        >
          Tokens per node not recorded for this run — node names sourced from
          prompt hashes.
        </div>
      ) : null}

      <div className="px-4 py-3">
        <table className="w-full text-[12px]" data-testid="node-breakdown-table">
          <thead>
            <tr className="text-left text-(--color-text-tertiary)">
              <SortHeader
                label="Node"
                sortKey="node"
                activeKey={sortKey}
                dir={sortDir}
                onSort={onSort}
                align="left"
              />
              <SortHeader
                label="Calls"
                sortKey="calls"
                activeKey={sortKey}
                dir={sortDir}
                onSort={onSort}
                align="right"
              />
              <SortHeader
                label="Tokens in"
                sortKey="ti"
                activeKey={sortKey}
                dir={sortDir}
                onSort={onSort}
                align="right"
              />
              <SortHeader
                label="Tokens out"
                sortKey="to"
                activeKey={sortKey}
                dir={sortDir}
                onSort={onSort}
                align="right"
              />
              <SortHeader
                label="Cost ($)"
                sortKey="cost_usd"
                activeKey={sortKey}
                dir={sortDir}
                onSort={onSort}
                align="right"
              />
              <SortHeader
                label="% of total"
                sortKey="pct"
                activeKey={sortKey}
                dir={sortDir}
                onSort={onSort}
                align="right"
              />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.node}
                className="text-(--color-text-row-title)"
                style={{ borderTop: "1px solid var(--color-border-standard)" }}
              >
                <td className="py-1.5 pr-3 font-mono">{row.node}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">
                  {row.calls === 0 ? "—" : row.calls}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums">
                  {formatTokens(row.ti)}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums">
                  {formatTokens(row.to)}
                </td>
                <td className="py-1.5 pr-3 text-right font-mono tabular-nums">
                  {formatCost(row.cost_usd)}
                </td>
                <td className="py-1.5 text-right tabular-nums text-(--color-text-row-meta)">
                  {formatPct(row.pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SortHeader({
  label,
  sortKey,
  activeKey,
  dir,
  onSort,
  align,
}: {
  label: string;
  sortKey: SortKey;
  activeKey: SortKey;
  dir: SortDir;
  onSort: (key: SortKey) => void;
  align: "left" | "right";
}) {
  const active = sortKey === activeKey;
  return (
    <th
      className={cn(
        "font-medium pb-1.5",
        align === "right" ? "text-right pl-3" : "pr-3",
      )}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "inline-flex items-center gap-1 hover:text-(--color-text-primary-strong)",
          active ? "text-(--color-text-primary-strong)" : "",
        )}
      >
        {label}
        {active ? (
          <span aria-hidden className="text-[10px]">
            {dir === "asc" ? "▲" : "▼"}
          </span>
        ) : null}
      </button>
    </th>
  );
}
