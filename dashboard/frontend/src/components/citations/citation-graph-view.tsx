"use client";

import * as React from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { GitBranch, List, Network } from "lucide-react";
import { cn } from "@/lib/utils";
import { CitationList } from "./citation-list";
import { CitationStats } from "./citation-stats";

export interface CitationNode {
  id: string;
  title: string;
  doi: string | null;
  openalex_id: string | null;
}

export type CitationEdgeKind = "references" | "cited_by";

export interface CitationEdge {
  from: string;
  to: string;
  kind: CitationEdgeKind;
}

export interface CitationStatsPayload {
  seed_count: number;
  expanded_count: number;
  edge_count: number;
  duplicates_filtered: number;
}

export interface CitationGraphPayload {
  seeds: CitationNode[];
  expanded: CitationNode[];
  edges: CitationEdge[];
  stats: CitationStatsPayload;
}

const TAB_DEFS = [
  { id: "graph", label: "Graph", icon: Network },
  { id: "list", label: "List", icon: List },
  { id: "stats", label: "Stats", icon: GitBranch },
] as const;

type TabId = (typeof TAB_DEFS)[number]["id"];

const COLOR_SEED = "var(--color-status-purple)";
const COLOR_EXPANDED = "var(--color-status-blue)";

/* ---------------------------------------------------------------------------
 * Layout helpers — pure, deterministic, no animation, no DOM measurement.
 * ------------------------------------------------------------------------- */

interface LaidOutNode extends CitationNode {
  x: number;
  y: number;
  side: "seed" | "expanded";
}

interface GraphLayout {
  nodes: LaidOutNode[];
  /** Lookup by id for O(1) edge resolution. */
  byId: Map<string, LaidOutNode>;
  width: number;
  height: number;
}

/**
 * Two-column layout: seeds on the left, expanded on the right, evenly
 * distributed vertically. Trivially scales to any sane (≤50) node count.
 * No collision handling beyond the column gutter — each side just fans out
 * along its own y-axis.
 */
function layoutGraph(payload: CitationGraphPayload): GraphLayout {
  const PADDING_Y = 32;
  const MIN_GAP = 56;
  const ROW_HEIGHT = 44;
  const COL_LEFT_X = 80;
  const COL_RIGHT_X = 460;
  const WIDTH = 540;

  const seedRows = Math.max(1, payload.seeds.length);
  const expandedRows = Math.max(1, payload.expanded.length);
  const tallestSide = Math.max(seedRows, expandedRows);
  const HEIGHT = Math.max(
    240,
    PADDING_Y * 2 + Math.max(MIN_GAP, tallestSide * ROW_HEIGHT),
  );

  const placeColumn = (
    items: CitationNode[],
    x: number,
    side: "seed" | "expanded",
  ): LaidOutNode[] => {
    if (items.length === 0) return [];
    const usable = HEIGHT - PADDING_Y * 2;
    const step = items.length === 1 ? 0 : usable / (items.length - 1);
    return items.map((node, idx) => ({
      ...node,
      x,
      y: items.length === 1 ? HEIGHT / 2 : PADDING_Y + step * idx,
      side,
    }));
  };

  const seeds = placeColumn(payload.seeds, COL_LEFT_X, "seed");
  const expanded = placeColumn(payload.expanded, COL_RIGHT_X, "expanded");
  const nodes = [...seeds, ...expanded];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return { nodes, byId, width: WIDTH, height: HEIGHT };
}

function bezierPath(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): string {
  const cx1 = x1 + (x2 - x1) * 0.45;
  const cx2 = x1 + (x2 - x1) * 0.55;
  return `M ${x1} ${y1} C ${cx1} ${y1}, ${cx2} ${y2}, ${x2} ${y2}`;
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1).trimEnd()}…`;
}

/* ---------------------------------------------------------------------------
 * Subcomponents
 * ------------------------------------------------------------------------- */

interface GraphProps {
  payload: CitationGraphPayload;
}

function GraphCanvas({ payload }: GraphProps) {
  const layout = React.useMemo(() => layoutGraph(payload), [payload]);
  const [hoverId, setHoverId] = React.useState<string | null>(null);

  const connectedIds = React.useMemo(() => {
    if (!hoverId) return null;
    const ids = new Set<string>([hoverId]);
    for (const e of payload.edges) {
      if (e.from === hoverId) ids.add(e.to);
      else if (e.to === hoverId) ids.add(e.from);
    }
    return ids;
  }, [hoverId, payload.edges]);

  const isEdgeActive = (e: CitationEdge): boolean =>
    !hoverId || e.from === hoverId || e.to === hoverId;

  if (layout.nodes.length === 0) {
    return null;
  }

  return (
    <div className="surface-linear-card p-4" data-testid="citation-graph-svg">
      <div
        className="flex items-center gap-4 pb-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <span className="font-label">Citation graph</span>
        <span className="flex items-center gap-1.5 text-[11px] text-(--color-text-row-meta)">
          <span
            aria-hidden
            className="rounded-full"
            style={{ width: 8, height: 8, background: COLOR_SEED }}
          />
          seeds
        </span>
        <span className="flex items-center gap-1.5 text-[11px] text-(--color-text-row-meta)">
          <span
            aria-hidden
            className="rounded-full"
            style={{ width: 8, height: 8, background: COLOR_EXPANDED }}
          />
          expanded
        </span>
        <span className="flex items-center gap-1.5 text-[11px] text-(--color-text-row-meta)">
          <span aria-hidden className="inline-block h-px w-6 bg-(--color-text-row-meta)" />
          references
        </span>
        <span className="flex items-center gap-1.5 text-[11px] text-(--color-text-row-meta)">
          <span
            aria-hidden
            className="inline-block h-px w-6"
            style={{
              background:
                "repeating-linear-gradient(90deg, var(--color-text-row-meta) 0 3px, transparent 3px 6px)",
            }}
          />
          cited by
        </span>
      </div>
      <div className="overflow-x-auto pt-3">
        <svg
          width="100%"
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          role="img"
          aria-label="Citation graph 1-hop expansion"
          className="block"
          style={{ maxWidth: "100%", height: "auto" }}
        >
          <g data-testid="citation-graph-edges">
            {payload.edges.map((edge, idx) => {
              const from = layout.byId.get(edge.from);
              const to = layout.byId.get(edge.to);
              if (!from || !to) return null;
              const active = isEdgeActive(edge);
              return (
                <path
                  key={`${edge.from}-${edge.to}-${idx}`}
                  d={bezierPath(from.x, from.y, to.x, to.y)}
                  fill="none"
                  stroke="var(--color-text-row-meta)"
                  strokeWidth={active ? 1.5 : 0.75}
                  strokeDasharray={edge.kind === "cited_by" ? "4 3" : undefined}
                  opacity={active ? 0.85 : 0.25}
                  data-testid={`edge-${edge.from}-${edge.to}`}
                  data-kind={edge.kind}
                />
              );
            })}
          </g>
          <g data-testid="citation-graph-nodes">
            {layout.nodes.map((node) => {
              const isFocused = !connectedIds || connectedIds.has(node.id);
              const fill = node.side === "seed" ? COLOR_SEED : COLOR_EXPANDED;
              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x}, ${node.y})`}
                  onMouseEnter={() => setHoverId(node.id)}
                  onMouseLeave={() => setHoverId(null)}
                  onFocus={() => setHoverId(node.id)}
                  onBlur={() => setHoverId(null)}
                  tabIndex={0}
                  className="cursor-pointer"
                  data-testid={`node-${node.id}`}
                  data-side={node.side}
                  style={{ outline: "none" }}
                >
                  <title>{node.title}</title>
                  <circle
                    r={9}
                    fill={fill}
                    opacity={isFocused ? 1 : 0.35}
                    stroke="var(--color-bg-page)"
                    strokeWidth={2}
                  />
                  <text
                    x={node.side === "seed" ? -14 : 14}
                    y={4}
                    fill="var(--color-text-row-title)"
                    fontSize={11}
                    textAnchor={node.side === "seed" ? "end" : "start"}
                    opacity={isFocused ? 1 : 0.5}
                    style={{ pointerEvents: "none", fontFamily: "var(--font-sans)" }}
                  >
                    {truncate(node.title, 30)}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
}

function EmptyGraphState() {
  return (
    <div
      className="surface-linear-card flex flex-col items-center justify-center gap-3 py-16 px-6 text-center"
      data-testid="citation-graph-empty"
    >
      <span
        aria-hidden
        className="flex size-12 items-center justify-center rounded-full bg-(--color-bg-pill-inactive) text-(--color-text-tertiary-spec)"
      >
        <Network size={20} strokeWidth={1.5} />
      </span>
      <p className="text-[13px] text-(--color-text-row-meta) max-w-sm">
        No citation graph computed for this run yet.
      </p>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * CitationGraphView
 * ------------------------------------------------------------------------- */

export function CitationGraphView({ payload }: { payload: CitationGraphPayload }) {
  const [tab, setTab] = React.useState<TabId>("graph");

  const isEmpty =
    payload.seeds.length === 0 &&
    payload.expanded.length === 0 &&
    payload.edges.length === 0;

  if (isEmpty) {
    return <EmptyGraphState />;
  }

  return (
    <Tabs.Root
      value={tab}
      onValueChange={(v) => setTab(v as TabId)}
      data-testid="citation-graph-view"
    >
      <Tabs.List
        className="flex items-center gap-1 rounded-full border border-(--color-border-pill) bg-(--color-bg-pill-inactive) p-1 self-start"
        aria-label="Citation graph view"
      >
        {TAB_DEFS.map(({ id, label, icon: Icon }) => (
          <Tabs.Trigger
            key={id}
            value={id}
            data-testid={`citation-tab-${id}`}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-[12px] transition-colors",
              "text-(--color-text-row-meta) hover:text-white",
              "data-[state=active]:bg-(--color-bg-pill-active)",
              "data-[state=active]:text-(--color-text-primary-strong)",
              "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-interactive)",
            )}
          >
            <Icon size={12} strokeWidth={1.75} />
            {label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>

      <Tabs.Content value="graph" className="mt-4">
        <GraphCanvas payload={payload} />
      </Tabs.Content>
      <Tabs.Content value="list" className="mt-4">
        <CitationList payload={payload} />
      </Tabs.Content>
      <Tabs.Content value="stats" className="mt-4">
        <CitationStats payload={payload} />
      </Tabs.Content>
    </Tabs.Root>
  );
}
