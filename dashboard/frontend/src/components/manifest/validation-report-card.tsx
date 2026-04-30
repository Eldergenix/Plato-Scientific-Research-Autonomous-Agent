"use client";

import * as React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clipboard,
  Search,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* -----------------------------------------------------------------------------
 * Types — public API. Keep stable; the integration commit and other streams
 * may already render this card.
 * ---------------------------------------------------------------------------*/

export type ValidationStatus = "ok" | "warn" | "fail";

export interface ValidationFailure {
  source_id: string;
  reason: string;
  detail?: string | null;
  /** Coarse-grained category for grouping (e.g. "schema", "fetch", "parser"). */
  source_type?: string | null;
}

export interface ValidationReport {
  status: ValidationStatus;
  total: number;
  passed: number;
  failures: ValidationFailure[];
}

export interface ValidationReportCardProps {
  report: ValidationReport;
  /** Initial collapsed state for the failures section. Defaults to false. */
  defaultExpanded?: boolean;
  className?: string;
}

type GroupBy = "none" | "reason" | "source_type";

/* -----------------------------------------------------------------------------
 * Helpers
 * ---------------------------------------------------------------------------*/

function statusIcon(status: ValidationStatus) {
  if (status === "ok") {
    return (
      <CheckCircle2
        size={14}
        strokeWidth={1.75}
        className="text-(--color-status-green-spec)"
      />
    );
  }
  if (status === "warn") {
    return (
      <AlertTriangle
        size={14}
        strokeWidth={1.75}
        className="text-(--color-status-amber-spec)"
      />
    );
  }
  return (
    <XCircle size={14} strokeWidth={1.75} className="text-(--color-status-red)" />
  );
}

function csvEscape(field: string): string {
  // Excel-friendly: quote everything that contains comma, quote, CR, or LF.
  if (/[",\r\n]/.test(field)) {
    return `"${field.replace(/"/g, '""')}"`;
  }
  return field;
}

function failuresToCsv(rows: ValidationFailure[]): string {
  const header = "source_id,reason,detail";
  const body = rows
    .map((f) =>
      [csvEscape(f.source_id), csvEscape(f.reason), csvEscape(f.detail ?? "")].join(
        ",",
      ),
    )
    .join("\n");
  return body.length > 0 ? `${header}\n${body}` : header;
}

function groupKey(failure: ValidationFailure, by: GroupBy): string {
  if (by === "reason") return failure.reason || "(no reason)";
  if (by === "source_type") return failure.source_type ?? "(unknown)";
  return "all";
}

/* -----------------------------------------------------------------------------
 * Subcomponents
 * ---------------------------------------------------------------------------*/

function FailureRow({ failure }: { failure: ValidationFailure }) {
  return (
    <li
      data-testid="validation-failure-row"
      className="flex flex-col gap-0.5 rounded-[6px] border border-[#262628] bg-[#141415] px-2.5 py-2"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-[12px] text-(--color-text-primary)">
          {failure.source_id}
        </span>
        <span className="text-[11px] text-(--color-status-red)">{failure.reason}</span>
      </div>
      {failure.detail ? (
        <div className="text-[11px] leading-[1.4] text-(--color-text-tertiary-spec)">
          {failure.detail}
        </div>
      ) : null}
    </li>
  );
}

function GroupedSection({
  title,
  rows,
  defaultOpen = true,
}: {
  title: string;
  rows: ValidationFailure[];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div data-testid="validation-group" className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        data-testid="validation-group-toggle"
        className={cn(
          "flex h-7 items-center gap-1.5 rounded-[6px] px-1.5 text-left",
          "text-[11.5px] font-medium text-(--color-text-secondary-spec)",
          "hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)",
        )}
      >
        {open ? (
          <ChevronDown size={11} strokeWidth={1.75} />
        ) : (
          <ChevronRight size={11} strokeWidth={1.75} />
        )}
        <span>{title}</span>
        <span className="text-(--color-text-quaternary-spec)">({rows.length})</span>
      </button>
      {open ? (
        <ul className="flex flex-col gap-1 pl-4">
          {rows.map((f, i) => (
            <FailureRow key={`${f.source_id}-${i}`} failure={f} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/* -----------------------------------------------------------------------------
 * ValidationReportCard
 * ---------------------------------------------------------------------------*/

export function ValidationReportCard({
  report,
  defaultExpanded = false,
  className,
}: ValidationReportCardProps) {
  const [expanded, setExpanded] = React.useState(defaultExpanded);
  const [search, setSearch] = React.useState("");
  const [groupBy, setGroupBy] = React.useState<GroupBy>("none");
  const [copied, setCopied] = React.useState(false);

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return report.failures;
    return report.failures.filter(
      (f) =>
        f.source_id.toLowerCase().includes(q) ||
        f.reason.toLowerCase().includes(q),
    );
  }, [report.failures, search]);

  const grouped = React.useMemo(() => {
    if (groupBy === "none") return null;
    const map = new Map<string, ValidationFailure[]>();
    for (const f of filtered) {
      const key = groupKey(f, groupBy);
      const arr = map.get(key) ?? [];
      arr.push(f);
      map.set(key, arr);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [filtered, groupBy]);

  const handleCopyCsv = React.useCallback(async () => {
    const csv = failuresToCsv(filtered);
    try {
      await navigator.clipboard.writeText(csv);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard blocked — silently swallow; the button is best-effort.
    }
  }, [filtered]);

  const hasFailures = report.failures.length > 0;

  return (
    <section
      data-testid="validation-report-card"
      data-status={report.status}
      className={cn("surface-linear-card overflow-hidden", className)}
    >
      <header
        className="flex items-center justify-between gap-3 border-b border-[#1D1D1F] px-3 py-2"
        data-testid="validation-report-header"
      >
        <div className="flex items-center gap-2">
          {statusIcon(report.status)}
          <span className="text-[13px] font-medium text-(--color-text-primary)">
            Validation report
          </span>
          <span className="text-[11.5px] text-(--color-text-tertiary-spec)">
            {report.passed} / {report.total} passed
          </span>
        </div>
        {hasFailures ? (
          <Button
            type="button"
            variant="subtle"
            size="sm"
            onClick={() => setExpanded((v) => !v)}
            data-testid="validation-toggle-failures"
            aria-expanded={expanded}
          >
            {expanded ? (
              <ChevronDown size={11} strokeWidth={1.75} />
            ) : (
              <ChevronRight size={11} strokeWidth={1.75} />
            )}
            {report.failures.length} failure
            {report.failures.length === 1 ? "" : "s"}
          </Button>
        ) : null}
      </header>

      {!hasFailures ? (
        <div
          className="px-3 py-3 text-[12px] text-(--color-text-tertiary-spec)"
          data-testid="validation-empty-state"
        >
          No failures.
        </div>
      ) : expanded ? (
        <div
          className="flex flex-col gap-2 px-3 py-2.5"
          data-testid="validation-failures-panel"
        >
          {/* Toolbar — search, group-by, copy CSV. */}
          <div className="flex flex-wrap items-center gap-1.5">
            <div className="relative flex-1 min-w-[180px]">
              <Search
                size={11}
                strokeWidth={1.75}
                className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-(--color-text-quaternary-spec)"
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter by source or reason"
                data-testid="validation-search"
                className={cn(
                  "h-7 w-full rounded-[6px] border border-[#262628] bg-[#141415] pl-7 pr-2",
                  "text-[12px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary-spec)",
                  "transition-colors hover:border-[#34343a]",
                  "focus-visible:border-(--color-brand-indigo) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-indigo)",
                )}
              />
            </div>

            <label className="inline-flex items-center gap-1.5 text-[11.5px] text-(--color-text-tertiary-spec)">
              <span>Group by</span>
              <select
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value as GroupBy)}
                data-testid="validation-group-by"
                className={cn(
                  "h-7 rounded-[6px] border border-[#262628] bg-[#141415] px-2",
                  "text-[12px] text-(--color-text-primary)",
                  "transition-colors hover:border-[#34343a]",
                  "focus-visible:border-(--color-brand-indigo) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-indigo)",
                )}
              >
                <option value="none">None</option>
                <option value="reason">Reason</option>
                <option value="source_type">Source type</option>
              </select>
            </label>

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleCopyCsv}
              data-testid="validation-copy-csv"
              aria-label="Copy failures as CSV"
            >
              <Clipboard size={11} strokeWidth={1.75} />
              {copied ? "Copied" : "Copy CSV"}
            </Button>
          </div>

          {/* Failures list. */}
          {filtered.length === 0 ? (
            <div
              className="rounded-[6px] border border-dashed border-[#262628] px-2.5 py-3 text-[11.5px] text-(--color-text-tertiary-spec)"
              data-testid="validation-no-matches"
            >
              No failures match the current filter.
            </div>
          ) : grouped ? (
            <div className="flex flex-col gap-2">
              {grouped.map(([key, rows]) => (
                <GroupedSection key={key} title={key} rows={rows} />
              ))}
            </div>
          ) : (
            <ul
              className="flex flex-col gap-1"
              data-testid="validation-failure-list"
            >
              {filtered.map((f, i) => (
                <FailureRow key={`${f.source_id}-${i}`} failure={f} />
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </section>
  );
}
