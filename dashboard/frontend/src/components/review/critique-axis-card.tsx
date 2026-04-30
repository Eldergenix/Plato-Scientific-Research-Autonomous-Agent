"use client";

import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CritiqueIssue {
  section: string;
  issue: string;
  fix?: string | null;
}

export interface CritiqueAxis {
  severity: number;
  rationale: string;
  issues: CritiqueIssue[];
}

export type SeverityTone = "emerald" | "amber" | "red";

/**
 * Map a 0-5 severity score to a Linear-themed tone.
 *
 * 0-1: nothing to act on (emerald)
 * 2-3: warrants a look (amber)
 * 4-5: blocking issue (red)
 */
export function severityTone(s: number): SeverityTone {
  if (s <= 1) return "emerald";
  if (s <= 3) return "amber";
  return "red";
}

const TONE_VAR: Record<SeverityTone, string> = {
  emerald: "var(--color-status-emerald)",
  amber: "var(--color-status-amber-spec)",
  red: "var(--color-status-red-spec)",
};

const RATIONALE_PREVIEW_LEN = 200;

const AXIS_LABELS: Record<string, string> = {
  methodology: "Methodology",
  statistics: "Statistics",
  novelty: "Novelty",
  writing: "Writing",
};

export function CritiqueAxisCard({
  axis,
  data,
}: {
  axis: string;
  data: CritiqueAxis | null;
}) {
  const label = AXIS_LABELS[axis] ?? axis;

  if (data === null) {
    return (
      <section
        className="surface-linear-card flex flex-col px-4 py-3"
        data-testid={`critique-axis-${axis}`}
        style={{ border: "1px solid var(--color-border-card)" }}
      >
        <header className="flex items-center justify-between gap-2">
          <h3
            className="text-(--color-text-primary-strong) text-[13px]"
            style={{ fontWeight: 510 }}
          >
            {label}
          </h3>
        </header>
        <p className="mt-2 text-[12px] text-(--color-text-row-meta)">
          No critique recorded for this axis yet.
        </p>
      </section>
    );
  }

  return (
    <section
      className="surface-linear-card flex flex-col"
      data-testid={`critique-axis-${axis}`}
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center justify-between gap-2 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <h3
          className="text-(--color-text-primary-strong) text-[13px]"
          style={{ fontWeight: 510 }}
        >
          {label}
        </h3>
        <SeverityPill severity={data.severity} />
      </header>

      <div className="px-4 py-3">
        <Rationale text={data.rationale} />

        {data.issues.length > 0 ? (
          <ul
            className="mt-3 flex flex-col gap-2"
            data-testid={`critique-axis-${axis}-issues`}
          >
            {data.issues.map((issue, idx) => (
              <li
                key={`${issue.section}-${idx}`}
                className="flex flex-col gap-0.5 rounded-[4px] px-2 py-1.5"
                style={{ border: "1px solid var(--color-border-standard)" }}
              >
                <div className="flex items-baseline gap-2 text-[12px]">
                  <span className="font-mono text-(--color-text-row-meta)">
                    {issue.section}
                  </span>
                  <span className="text-(--color-text-row-title)">
                    {issue.issue}
                  </span>
                </div>
                {issue.fix ? (
                  <div className="text-[11px] text-(--color-text-tertiary)">
                    <span className="font-label">Fix </span>
                    <span>{issue.fix}</span>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

function SeverityPill({ severity }: { severity: number }) {
  const tone = severityTone(severity);
  const color = TONE_VAR[tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5",
        "font-mono tabular-nums text-[11px]",
      )}
      style={{
        color,
        border: `1px solid ${color}`,
      }}
      data-testid="critique-severity"
    >
      Severity {severity}
    </span>
  );
}

function Rationale({ text }: { text: string }) {
  const [open, setOpen] = React.useState(false);

  if (!text) {
    return (
      <p className="text-[12px] text-(--color-text-row-meta)">
        No rationale provided.
      </p>
    );
  }

  const needsTruncate = text.length > RATIONALE_PREVIEW_LEN;
  const display = open || !needsTruncate
    ? text
    : `${text.slice(0, RATIONALE_PREVIEW_LEN).trimEnd()}…`;

  return (
    <div className="flex flex-col gap-1">
      <p
        className="text-[12px] text-(--color-text-row-title) whitespace-pre-wrap"
        data-testid="critique-rationale"
      >
        {display}
      </p>
      {needsTruncate ? (
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1 self-start text-[11px]",
            "text-(--color-brand-interactive) hover:underline",
          )}
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          data-testid="critique-rationale-toggle"
        >
          {open ? (
            <ChevronDown size={11} />
          ) : (
            <ChevronRight size={11} />
          )}
          {open ? "Show less" : "Show more"}
        </button>
      ) : null}
    </div>
  );
}
