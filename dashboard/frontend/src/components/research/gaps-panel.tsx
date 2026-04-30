"use client";

import * as React from "react";
import { AlertTriangle } from "lucide-react";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

export type GapKind = "contradiction" | "coverage" | "homogeneity" | string;

export interface ResearchGap {
  kind: GapKind;
  description: string;
  severity: number;
  evidence: string[];
}

export interface GapsPayload {
  gaps: ResearchGap[];
}

const KIND_ORDER: GapKind[] = ["contradiction", "coverage", "homogeneity"];

const KIND_LABELS: Record<string, string> = {
  contradiction: "Contradictions",
  coverage: "Coverage holes",
  homogeneity: "Methodology homogeneity",
};

const MAX_SEVERITY_DOTS = 5;

// Bucket-tone for the total-severity badge: emerald 0-3, amber 4-7, red 8+.
function totalSeverityTone(total: number): "green" | "amber" | "red" {
  if (total >= 8) return "red";
  if (total >= 4) return "amber";
  return "green";
}

// Permissive DOI matcher — looks for the canonical ``10.x/...`` prefix.
const DOI_RE = /^10\.\d{4,9}\/\S+$/;

function evidenceUrl(token: string): string | null {
  const trimmed = token.trim();
  if (DOI_RE.test(trimmed)) return `https://doi.org/${trimmed}`;
  return null;
}

function SeverityDots({ severity }: { severity: number }) {
  const filled = Math.max(0, Math.min(MAX_SEVERITY_DOTS, severity));
  return (
    <span
      className="inline-flex items-center gap-0.5"
      title={`Severity ${severity}/${MAX_SEVERITY_DOTS}`}
      aria-label={`Severity ${severity} of ${MAX_SEVERITY_DOTS}`}
    >
      {Array.from({ length: MAX_SEVERITY_DOTS }, (_, i) => (
        <span
          key={i}
          aria-hidden
          className="rounded-full"
          style={{
            width: 6,
            height: 6,
            background:
              i < filled
                ? severity >= 4
                  ? "var(--color-status-amber-spec)"
                  : "var(--color-brand-interactive)"
                : "var(--color-border-standard)",
          }}
        />
      ))}
    </span>
  );
}

function EvidenceChip({ token }: { token: string }) {
  const link = evidenceUrl(token);
  const display = token.length > 48 ? `${token.slice(0, 47)}…` : token;
  if (link) {
    return (
      <a
        href={link}
        target="_blank"
        rel="noreferrer noopener"
        className={cn(
          "inline-flex items-center gap-1 px-1.5 py-0.5 rounded",
          "text-[11px] font-mono",
          "text-(--color-brand-interactive) hover:underline",
        )}
        style={{ border: "1px solid var(--color-border-standard)" }}
        title={token}
      >
        {display}
      </a>
    );
  }
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono text-(--color-text-row-meta)"
      style={{ border: "1px solid var(--color-border-standard)" }}
      title={token}
    >
      {display}
    </span>
  );
}

function GapRow({ gap }: { gap: ResearchGap }) {
  return (
    <li
      className="flex flex-col gap-1.5 px-4 py-3"
      style={{ borderTop: "1px solid var(--color-border-standard)" }}
      data-testid="gap-row"
      data-kind={gap.kind}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] text-(--color-text-row-title) leading-relaxed">
          {gap.description}
        </p>
        <SeverityDots severity={gap.severity} />
      </div>
      {gap.evidence.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {gap.evidence.map((token, idx) => (
            <EvidenceChip key={`${token}-${idx}`} token={token} />
          ))}
        </div>
      ) : null}
    </li>
  );
}

export function GapsPanel({ payload }: { payload: GapsPayload }) {
  const { gaps } = payload;

  // Group by kind. Unknown kinds bucket under their own label so the
  // panel doesn't silently swallow new categories.
  const grouped = React.useMemo(() => {
    const map = new Map<string, ResearchGap[]>();
    for (const gap of gaps) {
      const existing = map.get(gap.kind);
      if (existing) {
        existing.push(gap);
      } else {
        map.set(gap.kind, [gap]);
      }
    }
    const ordered: Array<[string, ResearchGap[]]> = [];
    for (const kind of KIND_ORDER) {
      const bucket = map.get(kind);
      if (bucket && bucket.length > 0) {
        ordered.push([kind, bucket]);
        map.delete(kind);
      }
    }
    for (const [kind, bucket] of map) {
      ordered.push([kind, bucket]);
    }
    return ordered;
  }, [gaps]);

  const totalSeverity = React.useMemo(
    () => gaps.reduce((sum, g) => sum + (Number.isFinite(g.severity) ? g.severity : 0), 0),
    [gaps],
  );

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="gaps-panel"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <AlertTriangle size={16} className="text-(--color-text-tertiary)" />
          <h2
            className="text-(--color-text-primary-strong) text-[15px]"
            style={{ fontWeight: 510 }}
          >
            Research gaps
          </h2>
        </div>
        {gaps.length > 0 ? (
          <Pill
            tone={totalSeverityTone(totalSeverity)}
            data-testid="gaps-total-severity"
          >
            severity {totalSeverity}
          </Pill>
        ) : null}
      </header>

      {gaps.length === 0 ? (
        <div className="px-4 py-6 text-center" data-testid="gaps-empty">
          <p className="text-[13px] text-(--color-text-row-meta)">
            Gap analysis hasn&apos;t run yet.
          </p>
        </div>
      ) : (
        <div>
          {grouped.map(([kind, items]) => (
            <div key={kind} data-testid="gap-group" data-kind={kind}>
              <div
                className="flex items-baseline justify-between px-4 py-2"
                style={{
                  background: "var(--color-bg-card)",
                  borderTop: "1px solid var(--color-border-standard)",
                }}
              >
                <span className="font-label">
                  {KIND_LABELS[kind] ?? kind}
                </span>
                <span className="text-[11px] text-(--color-text-tertiary) tabular-nums">
                  {items.length}
                </span>
              </div>
              <ul className="flex flex-col">
                {items.map((gap, idx) => (
                  <GapRow key={`${gap.kind}-${idx}`} gap={gap} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
