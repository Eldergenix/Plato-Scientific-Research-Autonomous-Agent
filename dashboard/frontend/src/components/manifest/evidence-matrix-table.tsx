"use client";

import * as React from "react";
import { ExternalLink, FileText } from "lucide-react";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

export type SupportLabel = "supports" | "refutes" | "neutral" | "unclear";
export type StrengthLabel = "weak" | "moderate" | "strong";

export interface Claim {
  id: string;
  text: string;
  source_id?: string | null;
  section?: string | null;
}

export interface ClaimSource {
  id: string;
  title: string;
  url?: string | null;
}

export interface EvidenceLink {
  claim_id: string;
  source_id: string;
  support: SupportLabel;
  strength: StrengthLabel;
}

export interface EvidenceMatrixData {
  claims: Claim[];
  evidence_links: EvidenceLink[];
  /** Optional: lookup of source metadata. When absent we render IDs only. */
  sources?: ClaimSource[];
}

const SUPPORT_TONE: Record<SupportLabel, "green" | "red" | "amber" | "neutral"> = {
  supports: "green",
  refutes: "red",
  neutral: "amber",
  unclear: "neutral",
};

const STRENGTH_DOTS: Record<StrengthLabel, number> = {
  weak: 1,
  moderate: 2,
  strong: 3,
};

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1).trimEnd()}…`;
}

function StrengthIndicator({ strength }: { strength: StrengthLabel }) {
  const filled = STRENGTH_DOTS[strength];
  return (
    <span
      className="inline-flex items-center gap-0.5"
      title={`${strength} (${filled}/3)`}
      aria-label={`Strength ${strength}`}
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          aria-hidden
          className="rounded-full"
          style={{
            width: 6,
            height: 6,
            background:
              i < filled
                ? "var(--color-brand-interactive)"
                : "var(--color-border-strong)",
          }}
        />
      ))}
    </span>
  );
}

export function EvidenceMatrixTable({ data }: { data: EvidenceMatrixData }) {
  const { claims, evidence_links: links, sources = [] } = data;

  const claimById = React.useMemo(
    () => new Map(claims.map((c) => [c.id, c])),
    [claims],
  );
  const sourceById = React.useMemo(
    () => new Map(sources.map((s) => [s.id, s])),
    [sources],
  );

  if (links.length === 0) {
    return (
      <section
        className="surface-linear-card flex flex-col items-center justify-center gap-3 py-12 px-6 text-center"
        data-testid="evidence-matrix-empty"
        style={{ border: "1px solid var(--color-border-card)" }}
      >
        <div className="flex size-10 items-center justify-center rounded-full bg-(--color-bg-pill-inactive) text-(--color-text-tertiary)">
          <FileText size={18} />
        </div>
        <p className="text-[13px] text-(--color-text-row-meta) max-w-md">
          No evidence links yet — claim extraction not run.
        </p>
      </section>
    );
  }

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="evidence-matrix-table"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <h2
          className="text-(--color-text-primary-strong) text-[15px]"
          style={{ fontWeight: 510 }}
        >
          Claims × sources
        </h2>
        <span className="text-[12px] text-(--color-text-row-meta)">
          {links.length} {links.length === 1 ? "link" : "links"}
        </span>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr
              className="text-left text-(--color-text-tertiary)"
              style={{ borderBottom: "1px solid var(--color-border-standard)" }}
            >
              <th className="font-label px-4 py-2 w-[42%]">Claim</th>
              <th className="font-label px-4 py-2 w-[38%]">Source</th>
              <th className="font-label px-4 py-2 w-[12%]">Support</th>
              <th className="font-label px-4 py-2 w-[8%]">Strength</th>
            </tr>
          </thead>
          <tbody>
            {links.map((link, idx) => {
              const claim = claimById.get(link.claim_id);
              const source = sourceById.get(link.source_id);
              const claimText = claim?.text ?? `(claim ${link.claim_id})`;
              const sourceTitle = source?.title ?? link.source_id;
              const sourceUrl = source?.url ?? null;

              return (
                <tr
                  key={`${link.claim_id}-${link.source_id}-${idx}`}
                  className="text-(--color-text-row-title) hover:bg-(--color-ghost-bg-hover)"
                  style={{ borderBottom: "1px solid var(--color-border-standard)" }}
                  data-testid="evidence-matrix-row"
                >
                  <td className="px-4 py-2.5 align-top">
                    <span title={claimText}>{truncate(claimText, 90)}</span>
                  </td>
                  <td className="px-4 py-2.5 align-top">
                    {sourceUrl ? (
                      <a
                        href={sourceUrl}
                        target="_blank"
                        rel="noreferrer noopener"
                        title={sourceTitle}
                        className={cn(
                          "inline-flex items-center gap-1",
                          "text-(--color-brand-interactive) hover:underline",
                        )}
                      >
                        {truncate(sourceTitle, 70)}
                        <ExternalLink size={10} />
                      </a>
                    ) : (
                      <span title={sourceTitle} className="text-(--color-text-row-meta)">
                        {truncate(sourceTitle, 70)}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 align-top">
                    <Pill tone={SUPPORT_TONE[link.support]}>{link.support}</Pill>
                  </td>
                  <td className="px-4 py-2.5 align-top">
                    <StrengthIndicator strength={link.strength} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
