"use client";

import * as React from "react";
import { Library, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

export interface RetrievalAdapterRow {
  adapter: string;
  count: number;
  deduped: number;
}

export interface RetrievalSampleSource {
  source_id: string;
  title: string;
  adapter: string;
}

export interface RetrievalSummaryPayload {
  by_adapter: RetrievalAdapterRow[];
  total_unique: number;
  total_returned: number;
  queries: string[];
  samples: RetrievalSampleSource[];
}

/**
 * Adapter colour map. Sticks to the seven ``--color-status-*`` vars that
 * exist in globals.css. R4 currently has six adapters; if a new one
 * lands without a colour we fall back to the neutral border.
 */
const ADAPTER_COLOR: Record<string, string> = {
  arxiv: "var(--color-status-orange)",
  openalex: "var(--color-status-blue)",
  crossref: "var(--color-status-purple)",
  ads: "var(--color-status-teal)",
  pubmed: "var(--color-status-green-spec)",
  semantic_scholar: "var(--color-status-amber-spec)",
};

const ADAPTER_LABEL: Record<string, string> = {
  arxiv: "arXiv",
  openalex: "OpenAlex",
  crossref: "Crossref",
  ads: "ADS",
  pubmed: "PubMed",
  semantic_scholar: "Semantic Scholar",
};

function adapterColor(adapter: string): string {
  return ADAPTER_COLOR[adapter] ?? "var(--color-border-strong)";
}

function adapterLabel(adapter: string): string {
  return ADAPTER_LABEL[adapter] ?? adapter;
}

/**
 * Render an external-link URL for a source identifier — copied from
 * ``manifest-panel.tsx`` so the literature panel has the same DOI/arxiv
 * resolution behaviour without a circular import.
 */
function sourceUrl(id: string): string | null {
  const trimmed = id.trim();
  if (!trimmed) return null;
  if (/^10\.\d{4,9}\//.test(trimmed)) return `https://doi.org/${trimmed}`;
  if (/^arxiv:/i.test(trimmed)) {
    return `https://arxiv.org/abs/${trimmed.slice(6)}`;
  }
  if (/^\d{4}\.\d{4,5}(v\d+)?$/.test(trimmed)) {
    return `https://arxiv.org/abs/${trimmed}`;
  }
  return null;
}

/**
 * Horizontal bar chart by adapter. We hand-roll the SVG instead of
 * pulling in a charting lib — the data shape is small (≤6 rows) and we
 * already get the spec colours via CSS vars.
 */
function AdapterBars({ rows }: { rows: RetrievalAdapterRow[] }) {
  const max = Math.max(...rows.map((r) => r.count), 1);
  const ROW_H = 22;
  const ROW_GAP = 8;
  const LABEL_W = 130;
  const COUNT_W = 64;
  const BAR_AREA = 240;
  const W = LABEL_W + BAR_AREA + COUNT_W;
  const H = rows.length * (ROW_H + ROW_GAP) - ROW_GAP;

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Retrieval source breakdown by adapter"
      className="block"
      data-testid="source-breakdown-bars"
    >
      {rows.map((row, idx) => {
        const y = idx * (ROW_H + ROW_GAP);
        const barW = Math.max(2, (row.count / max) * BAR_AREA);
        const color = adapterColor(row.adapter);
        const label = adapterLabel(row.adapter);
        return (
          <g key={row.adapter} data-testid="source-breakdown-bar">
            <text
              x={0}
              y={y + ROW_H / 2}
              dominantBaseline="middle"
              fontSize={12}
              fill="var(--color-text-row-title)"
              style={{ fontFamily: "Inter, var(--font-sans)" }}
            >
              {label}
            </text>
            <rect
              x={LABEL_W}
              y={y + 2}
              width={BAR_AREA}
              height={ROW_H - 4}
              fill="rgba(255,255,255,0.04)"
              rx={3}
            />
            <rect
              x={LABEL_W}
              y={y + 2}
              width={barW}
              height={ROW_H - 4}
              fill={color}
              opacity={0.9}
              rx={3}
              data-adapter={row.adapter}
            />
            <text
              x={LABEL_W + BAR_AREA + 8}
              y={y + ROW_H / 2}
              dominantBaseline="middle"
              fontSize={12}
              fill="var(--color-text-row-meta)"
              style={{
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {row.count}
              {row.deduped > 0 ? ` (-${row.deduped})` : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function SampleRow({ sample }: { sample: RetrievalSampleSource }) {
  const url = sourceUrl(sample.source_id);
  const color = adapterColor(sample.adapter);
  const label = adapterLabel(sample.adapter);

  return (
    <li
      className="flex items-center gap-2 py-1.5"
      style={{ borderTop: "1px solid var(--color-border-standard)" }}
    >
      <span
        aria-hidden
        className="rounded-full"
        style={{
          width: 8,
          height: 8,
          background: color,
          flex: "none",
        }}
      />
      <span
        className="font-mono text-[10px] uppercase tracking-wide text-(--color-text-row-meta)"
        style={{ minWidth: 88 }}
        title={label}
      >
        {label}
      </span>
      <div className="flex min-w-0 flex-col">
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noreferrer noopener"
            className={cn(
              "inline-flex items-center gap-1 font-mono text-[12px] truncate",
              "text-(--color-brand-interactive) hover:underline",
            )}
            title={sample.source_id}
          >
            {sample.source_id}
            <ExternalLink size={10} />
          </a>
        ) : (
          <span
            className="font-mono text-[12px] text-(--color-text-row-title) truncate"
            title={sample.source_id}
          >
            {sample.source_id}
          </span>
        )}
        {sample.title ? (
          <span
            className="text-[11px] text-(--color-text-row-meta) truncate"
            title={sample.title}
          >
            {sample.title}
          </span>
        ) : null}
      </div>
    </li>
  );
}

export function SourceBreakdown({ payload }: { payload: RetrievalSummaryPayload }) {
  const rows = payload.by_adapter;
  const adapterCount = rows.length;

  if (rows.length === 0 && payload.total_returned === 0) {
    return (
      <section
        className="surface-linear-card flex flex-col items-center justify-center gap-3 py-12 px-6 text-center"
        data-testid="source-breakdown-empty"
        style={{ border: "1px solid var(--color-border-card)" }}
      >
        <div className="flex size-10 items-center justify-center rounded-full bg-(--color-bg-pill-inactive) text-(--color-text-tertiary)">
          <Library size={18} />
        </div>
        <p className="text-[13px] text-(--color-text-row-meta) max-w-md">
          No retrieval has run yet.
        </p>
      </section>
    );
  }

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="source-breakdown"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <Library size={16} className="text-(--color-text-tertiary)" />
        <h2
          className="text-(--color-text-primary-strong) text-[15px]"
          style={{ fontWeight: 510 }}
        >
          Retrieval sources
        </h2>
        <div aria-hidden className="flex-1" />
        <span className="font-mono text-[12px] text-(--color-text-row-meta) tabular-nums">
          {payload.total_unique} unique
        </span>
      </header>

      <div className="px-4 py-4">
        {rows.length > 0 ? (
          <AdapterBars rows={rows} />
        ) : (
          <p className="text-[12px] text-(--color-text-row-meta)">
            Adapter breakdown unavailable.
          </p>
        )}
        <p
          className="text-[12px] text-(--color-text-row-meta)"
          style={{ marginTop: 12 }}
          data-testid="source-breakdown-summary"
        >
          Total{" "}
          <span className="tabular-nums text-(--color-text-row-title)">
            {payload.total_unique}
          </span>{" "}
          unique sources from{" "}
          <span className="tabular-nums text-(--color-text-row-title)">
            {payload.total_returned}
          </span>{" "}
          returned across{" "}
          <span className="tabular-nums text-(--color-text-row-title)">
            {adapterCount}
          </span>{" "}
          {adapterCount === 1 ? "adapter" : "adapters"}.
        </p>
      </div>

      {payload.queries.length > 0 ? (
        <div
          className="px-4 py-3"
          style={{ borderTop: "1px solid var(--color-border-standard)" }}
        >
          <div className="font-label" style={{ marginBottom: 6 }}>
            Queries ({payload.queries.length})
          </div>
          <ul className="flex flex-wrap gap-1.5">
            {payload.queries.map((q, idx) => (
              <li
                key={`${q}-${idx}`}
                className="font-mono text-[11px] px-2 py-0.5 rounded-full"
                style={{
                  background: "var(--color-bg-pill-inactive)",
                  color: "var(--color-text-row-meta)",
                  border: "1px solid var(--color-border-pill)",
                }}
              >
                {q}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {payload.samples.length > 0 ? (
        <div
          className="px-4 py-3"
          style={{ borderTop: "1px solid var(--color-border-standard)" }}
        >
          <div className="font-label" style={{ marginBottom: 6 }}>
            Sample sources
          </div>
          <ul className="flex flex-col" data-testid="source-breakdown-samples">
            {payload.samples.map((s) => (
              <SampleRow key={s.source_id} sample={s} />
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
