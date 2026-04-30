"use client";

import * as React from "react";
import { CheckCircle2, ChevronDown, ChevronRight, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ValidationFailure {
  source_id: string;
  reason: string;
  detail?: string | null;
}

export interface ValidationReport {
  validation_rate: number; // 0..1
  total_references: number;
  verified_references: number;
  failures: ValidationFailure[];
}

function formatPct(rate: number): string {
  if (!Number.isFinite(rate)) return "—";
  const clamped = Math.max(0, Math.min(1, rate));
  return `${(clamped * 100).toFixed(1)}%`;
}

export function ValidationReportCard({ report }: { report: ValidationReport }) {
  const [open, setOpen] = React.useState(false);

  const tone =
    report.validation_rate >= 0.9
      ? "var(--color-status-emerald)"
      : report.validation_rate >= 0.7
        ? "var(--color-status-amber)"
        : "var(--color-status-red-spec)";

  const Icon = report.validation_rate >= 0.9 ? CheckCircle2 : ShieldAlert;
  const failureCount = report.failures.length;

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="validation-report-card"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <Icon size={16} style={{ color: tone }} />
        <h2
          className="text-(--color-text-primary-strong) text-[15px]"
          style={{ fontWeight: 510 }}
        >
          Validation report
        </h2>
      </header>

      <div className="px-4 py-4 flex items-baseline gap-3">
        <span
          className="font-mono tabular-nums"
          style={{ fontSize: 32, fontWeight: 500, lineHeight: 1, color: tone }}
          data-testid="validation-rate"
        >
          {formatPct(report.validation_rate)}
        </span>
        <span className="text-[12px] text-(--color-text-row-meta)">
          {report.verified_references} / {report.total_references} references verified
        </span>
      </div>

      {failureCount > 0 ? (
        <div style={{ borderTop: "1px solid var(--color-border-standard)" }}>
          <button
            type="button"
            className={cn(
              "flex w-full items-center gap-2 px-4 py-2.5 text-left",
              "text-[12px] text-(--color-text-row-title)",
              "hover:bg-(--color-ghost-bg-hover)",
            )}
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            data-testid="validation-failures-toggle"
          >
            {open ? (
              <ChevronDown size={12} className="text-(--color-text-tertiary)" />
            ) : (
              <ChevronRight size={12} className="text-(--color-text-tertiary)" />
            )}
            <span className="font-label">Failures</span>
            <span className="text-(--color-text-row-meta)">
              ({failureCount})
            </span>
          </button>

          {open ? (
            <ul
              className="flex flex-col"
              style={{ borderTop: "1px solid var(--color-border-standard)" }}
              data-testid="validation-failures-list"
            >
              {report.failures.map((failure, idx) => (
                <li
                  key={`${failure.source_id}-${idx}`}
                  className="flex flex-col gap-0.5 px-4 py-2"
                  style={{
                    borderBottom: "1px solid var(--color-border-standard)",
                  }}
                >
                  <div className="flex items-center gap-2 text-[12px]">
                    <span className="font-mono text-(--color-text-row-title)">
                      {failure.source_id}
                    </span>
                    <span className="text-(--color-status-red-spec)">
                      {failure.reason}
                    </span>
                  </div>
                  {failure.detail ? (
                    <span className="text-[11px] text-(--color-text-row-meta)">
                      {failure.detail}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <div
          className="px-4 py-2.5 text-[12px] text-(--color-text-row-meta)"
          style={{ borderTop: "1px solid var(--color-border-standard)" }}
        >
          All references verified.
        </div>
      )}
    </section>
  );
}
