"use client";

import * as React from "react";
import { ExternalLink, GitBranch, Quote } from "lucide-react";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";
import type { CitationGraphPayload, CitationNode } from "./citation-graph-view";

interface DegreeMaps {
  /** Edges that originate from this node (out-degree). */
  outgoing: Map<string, number>;
  /** Edges that terminate at this node (in-degree). */
  incoming: Map<string, number>;
  /** Edges where this node is the seed and the kind is ``cited_by``. */
  citedByOut: Map<string, number>;
}

function buildDegreeMaps(payload: CitationGraphPayload): DegreeMaps {
  const outgoing = new Map<string, number>();
  const incoming = new Map<string, number>();
  const citedByOut = new Map<string, number>();
  for (const e of payload.edges) {
    outgoing.set(e.from, (outgoing.get(e.from) ?? 0) + 1);
    incoming.set(e.to, (incoming.get(e.to) ?? 0) + 1);
    if (e.kind === "cited_by") {
      citedByOut.set(e.from, (citedByOut.get(e.from) ?? 0) + 1);
    }
  }
  return { outgoing, incoming, citedByOut };
}

/** Best-effort arxiv extraction from an OpenAlex id like "W..." — none in
 * practice, but we honor any title fragment of the form ``arXiv:1234.5678``. */
function extractArxiv(node: CitationNode): string | null {
  const m = node.title.match(/arXiv:\s*(\d{4}\.\d{4,5})/i);
  return m ? m[1] : null;
}

function CitationRow({
  node,
  refsCount,
  citedByCount,
}: {
  node: CitationNode;
  refsCount: number;
  citedByCount: number;
}) {
  const arxiv = extractArxiv(node);
  return (
    <div
      className="flex flex-col gap-1.5 px-4 py-3"
      data-testid={`citation-row-${node.id}`}
      style={{ borderBottom: "1px solid var(--color-border-standard)" }}
    >
      <div className="flex items-start gap-2">
        <span
          className="flex-1 text-[13px] text-(--color-text-row-title) leading-snug"
          style={{ fontWeight: 500 }}
        >
          {node.title}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {node.doi ? (
          <a
            href={`https://doi.org/${node.doi}`}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-mono",
              "border-(--color-border-pill) bg-(--color-bg-pill-inactive)",
              "text-(--color-text-row-meta) hover:text-white hover:border-(--color-brand-interactive)",
              "transition-colors",
            )}
            data-testid={`doi-link-${node.id}`}
          >
            <ExternalLink size={10} strokeWidth={1.75} />
            {node.doi}
          </a>
        ) : null}
        {arxiv ? (
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-mono",
              "border-(--color-border-pill) bg-(--color-bg-pill-inactive) text-(--color-status-purple)",
            )}
          >
            arXiv:{arxiv}
          </span>
        ) : null}
        {node.openalex_id ? (
          <span
            className={cn(
              "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-mono",
              "border-(--color-border-pill) bg-(--color-bg-pill-inactive) text-(--color-text-quaternary-spec)",
            )}
            title="OpenAlex id"
          >
            {node.openalex_id}
          </span>
        ) : null}
        <span aria-hidden className="flex-1" />
        <span
          className="inline-flex items-center gap-1 text-[11px] text-(--color-text-row-meta)"
          title={`${refsCount} references`}
        >
          <Quote size={10} strokeWidth={1.75} />
          {refsCount} references
        </span>
        <span
          className="inline-flex items-center gap-1 text-[11px] text-(--color-text-row-meta)"
          title={`${citedByCount} cited by`}
        >
          <GitBranch size={10} strokeWidth={1.75} />
          {citedByCount} cited by
        </span>
      </div>
    </div>
  );
}

function SectionHeader({
  label,
  count,
  tone,
}: {
  label: string;
  count: number;
  tone: "purple" | "blue";
}) {
  return (
    <header
      className="flex items-center gap-2 px-4 py-2.5"
      style={{
        borderBottom: "1px solid var(--color-border-standard)",
        background: "rgba(255,255,255,0.02)",
      }}
    >
      <span
        aria-hidden
        className="rounded-full"
        style={{
          width: 8,
          height: 8,
          background:
            tone === "purple"
              ? "var(--color-status-purple)"
              : "var(--color-status-blue)",
        }}
      />
      <span className="font-label">{label}</span>
      <Pill tone="neutral" className="font-mono">
        {count}
      </Pill>
    </header>
  );
}

export function CitationList({ payload }: { payload: CitationGraphPayload }) {
  const degrees = React.useMemo(() => buildDegreeMaps(payload), [payload]);

  return (
    <div className="flex flex-col gap-4" data-testid="citation-list">
      <section
        className="surface-linear-card overflow-hidden"
        data-testid="citation-list-seeds"
      >
        <SectionHeader label="Seeds" count={payload.seeds.length} tone="purple" />
        {payload.seeds.length === 0 ? (
          <div className="px-4 py-6 text-[12px] text-(--color-text-row-meta)">
            No seed papers in this graph.
          </div>
        ) : (
          payload.seeds.map((node) => (
            <CitationRow
              key={node.id}
              node={node}
              refsCount={degrees.outgoing.get(node.id) ?? 0}
              citedByCount={degrees.citedByOut.get(node.id) ?? 0}
            />
          ))
        )}
      </section>

      <section
        className="surface-linear-card overflow-hidden"
        data-testid="citation-list-expanded"
      >
        <SectionHeader
          label="Expanded"
          count={payload.expanded.length}
          tone="blue"
        />
        {payload.expanded.length === 0 ? (
          <div className="px-4 py-6 text-[12px] text-(--color-text-row-meta)">
            No 1-hop expansion targets.
          </div>
        ) : (
          payload.expanded.map((node) => (
            <CitationRow
              key={node.id}
              node={node}
              refsCount={degrees.outgoing.get(node.id) ?? 0}
              citedByCount={degrees.incoming.get(node.id) ?? 0}
            />
          ))
        )}
      </section>
    </div>
  );
}
