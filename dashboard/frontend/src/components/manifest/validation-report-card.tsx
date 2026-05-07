"use client";

import * as React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clipboard,
  FileText,
  Folder,
  Search,
  Tags,
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
  reason?: string | null;
  detail?: string | null;
  /** Coarse-grained category for grouping (e.g. "schema", "fetch", "parser"). */
  source_type?: string | null;
  title?: string | null;
  verdict?: "LIKELY" | "UNCERTAIN" | "UNLIKELY" | string | null;
  confidence?: number | null;
  folder?: string | null;
  tags?: string[];
  notes?: { markdown?: string; plain_text?: string } | null;
  corrections?: {
    bibtex?: string;
    plain_text?: string;
    bibitem?: string;
  } | null;
  hallucination_assessment?: {
    verdict?: string;
    explanation?: string;
    link?: string | null;
    found_title?: string | null;
    found_authors?: string | null;
    found_year?: string | null;
  } | null;
}

/**
 * Canonical schema produced by the backend's ``/api/v1/runs/{id}/validation_report``
 * endpoint. ``status`` is derived internally from ``validation_rate`` so callers
 * don't need to pre-compute it.
 */
export interface ValidationReport {
  validation_rate: number; // 0..1
  total_references?: number;
  verified_references?: number;
  total?: number;
  passed?: number;
  unverified_count?: number;
  likely_hallucinations?: number;
  accuracy_gate?: {
    threshold?: number;
    passed?: boolean;
    reason?: string | null;
  };
  failures: ValidationFailure[];
}

function deriveStatus(rate: number): ValidationStatus {
  if (!Number.isFinite(rate)) return "fail";
  if (rate >= 0.95) return "ok";
  if (rate >= 0.7) return "warn";
  return "fail";
}

function formatPct(rate: number): string {
  if (!Number.isFinite(rate)) return "—";
  const clamped = Math.max(0, Math.min(1, rate));
  return `${(clamped * 100).toFixed(1)}%`;
}

export interface ValidationReportCardProps {
  report: ValidationReport;
  /** Initial collapsed state for the failures section. Defaults to false. */
  defaultExpanded?: boolean;
  className?: string;
}

type GroupBy = "none" | "reason" | "source_type";
type ValidationFailureNote = NonNullable<ValidationFailure["notes"]>;

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
      [
        csvEscape(f.source_id),
        csvEscape(f.reason ?? ""),
        csvEscape(f.detail ?? ""),
      ].join(","),
    )
    .join("\n");
  return body.length > 0 ? `${header}\n${body}` : header;
}

function groupKey(failure: ValidationFailure, by: GroupBy): string {
  if (by === "reason") return failure.reason || "(no reason)";
  if (by === "source_type") return failure.source_type ?? "(unknown)";
  return "all";
}

function referenceTotals(report: ValidationReport) {
  return {
    total: report.total_references ?? report.total ?? 0,
    verified: report.verified_references ?? report.passed ?? 0,
  };
}

/* -----------------------------------------------------------------------------
 * Subcomponents
 * ---------------------------------------------------------------------------*/

function FailureRow({
  failure,
  onUpdateFailureNote,
}: {
  failure: ValidationFailure;
  onUpdateFailureNote?: (sourceId: string, notes: ValidationFailureNote) => void;
}) {
  const [noteFormat, setNoteFormat] = React.useState<"markdown" | "plain_text">(
    "markdown",
  );
  const [note, setNote] = React.useState(
    failure.notes?.markdown ?? failure.notes?.plain_text ?? "",
  );
  const assessment = failure.hallucination_assessment;
  const verdict = failure.verdict ?? assessment?.verdict;
  const correction =
    failure.corrections?.bibtex ??
    failure.corrections?.plain_text ??
    failure.corrections?.bibitem;
  const switchNoteFormat = React.useCallback(
    (nextFormat: "markdown" | "plain_text") => {
      if (nextFormat === noteFormat) return;
      const updatedNotes = {
        ...(failure.notes ?? {}),
        [noteFormat]: note,
      };
      onUpdateFailureNote?.(failure.source_id, updatedNotes);
      setNoteFormat(nextFormat);
      setNote(updatedNotes[nextFormat] ?? "");
    },
    [failure.notes, failure.source_id, note, noteFormat, onUpdateFailureNote],
  );

  return (
    <li
      data-testid="validation-failure-row"
      className="flex flex-col gap-0.5 rounded-[6px] border border-[#262628] bg-[#141415] px-2.5 py-2"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-[12px] text-(--color-text-primary)">
            {failure.source_id}
          </div>
          {failure.title ? (
            <div className="truncate text-[11px] text-(--color-text-tertiary-spec)">
              {failure.title}
            </div>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {verdict ? (
            <span className="rounded-[999px] border border-[#34343a] px-1.5 py-0.5 text-[10.5px] text-(--color-text-secondary-spec)">
              {verdict}
            </span>
          ) : null}
          <span className="text-[11px] text-(--color-status-red)">
            {failure.reason ?? "failed"}
          </span>
        </div>
      </div>
      {failure.detail ? (
        <div className="text-[11px] leading-[1.4] text-(--color-text-tertiary-spec)">
          {failure.detail}
        </div>
      ) : null}
      {assessment?.explanation ? (
        <div className="text-[11px] leading-[1.4] text-(--color-text-secondary-spec)">
          {assessment.explanation}
          {assessment.link ? (
            <>
              {" "}
              <a
                href={assessment.link}
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                source
              </a>
            </>
          ) : null}
        </div>
      ) : null}
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        {failure.folder ? (
          <span className="inline-flex items-center gap-1 rounded-[6px] bg-[#1b1b1d] px-1.5 py-0.5 text-[10.5px] text-(--color-text-tertiary-spec)">
            <Folder size={10} strokeWidth={1.75} />
            {failure.folder}
          </span>
        ) : null}
        {(failure.tags ?? []).map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 rounded-[6px] bg-[#1b1b1d] px-1.5 py-0.5 text-[10.5px] text-(--color-text-tertiary-spec)"
          >
            <Tags size={10} strokeWidth={1.75} />
            {tag}
          </span>
        ))}
      </div>
      {correction ? (
        <details className="mt-1">
          <summary className="flex cursor-pointer items-center gap-1 text-[11px] text-(--color-text-secondary-spec)">
            <FileText size={11} strokeWidth={1.75} />
            Correction
          </summary>
          <pre className="mt-1 max-h-36 overflow-auto rounded-[6px] border border-[#262628] bg-[#101011] p-2 text-[10.5px] leading-[1.45] text-(--color-text-tertiary-spec)">
            {correction}
          </pre>
        </details>
      ) : null}
      {failure.notes ? (
        <div className="mt-1 flex flex-col gap-1">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => switchNoteFormat("markdown")}
              className={cn(
                "h-6 rounded-[6px] px-1.5 text-[10.5px]",
                noteFormat === "markdown"
                  ? "bg-[#27272a] text-(--color-text-primary)"
                  : "text-(--color-text-tertiary-spec)",
              )}
            >
              Markdown
            </button>
            <button
              type="button"
              onClick={() => switchNoteFormat("plain_text")}
              className={cn(
                "h-6 rounded-[6px] px-1.5 text-[10.5px]",
                noteFormat === "plain_text"
                  ? "bg-[#27272a] text-(--color-text-primary)"
                  : "text-(--color-text-tertiary-spec)",
              )}
            >
              Plain text
            </button>
          </div>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            onBlur={() =>
              onUpdateFailureNote?.(failure.source_id, {
                ...(failure.notes ?? {}),
                [noteFormat]: note,
              })
            }
            className="min-h-20 rounded-[6px] border border-[#262628] bg-[#101011] p-2 text-[11px] leading-[1.45] text-(--color-text-secondary-spec) focus-visible:border-(--color-brand-indigo) focus-visible:outline-none"
            data-testid="validation-note-editor"
          />
        </div>
      ) : null}
    </li>
  );
}

function GroupedSection({
  title,
  rows,
  defaultOpen = true,
  onUpdateFailureNote,
}: {
  title: string;
  rows: ValidationFailure[];
  defaultOpen?: boolean;
  onUpdateFailureNote?: (sourceId: string, notes: ValidationFailureNote) => void;
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
            <FailureRow
              key={`${f.source_id}-${i}`}
              failure={f}
              onUpdateFailureNote={onUpdateFailureNote}
            />
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
  const [noteOverrides, setNoteOverrides] = React.useState<
    Record<string, ValidationFailureNote>
  >({});

  const failuresWithNotes = React.useMemo(
    () =>
      report.failures.map((failure) => {
        const override = noteOverrides[failure.source_id];
        if (!override) return failure;
        return {
          ...failure,
          notes: { ...(failure.notes ?? {}), ...override },
        };
      }),
    [noteOverrides, report.failures],
  );

  const handleUpdateFailureNote = React.useCallback(
    (sourceId: string, notes: ValidationFailureNote) => {
      setNoteOverrides((current) => ({
        ...current,
        [sourceId]: { ...(current[sourceId] ?? {}), ...notes },
      }));
    },
    [],
  );

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return failuresWithNotes;
    return failuresWithNotes.filter(
      (f) =>
        f.source_id.toLowerCase().includes(q) ||
        (f.reason ?? "").toLowerCase().includes(q) ||
        (f.title ?? "").toLowerCase().includes(q) ||
        (f.verdict ?? "").toLowerCase().includes(q) ||
        (f.tags ?? []).some((tag) => tag.toLowerCase().includes(q)),
    );
  }, [failuresWithNotes, search]);

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
  const status = deriveStatus(report.validation_rate);
  const totals = referenceTotals(report);

  return (
    <section
      data-testid="validation-report-card"
      data-status={status}
      className={cn("surface-linear-card overflow-hidden", className)}
    >
      <header
        className="flex items-center justify-between gap-3 border-b border-[#1D1D1F] px-3 py-2"
        data-testid="validation-report-header"
      >
        <div className="flex items-center gap-2">
          {statusIcon(status)}
          <span className="text-[13px] font-medium text-(--color-text-primary)">
            Validation report
          </span>
          <span
            className="text-[11.5px] font-mono tabular-nums text-(--color-text-primary-strong)"
            data-testid="validation-rate"
          >
            {formatPct(report.validation_rate)}
          </span>
          <span className="text-[11.5px] text-(--color-text-tertiary-spec)">
            {totals.verified} / {totals.total} references verified
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
            Failures
            <span className="ml-0.5 text-(--color-text-tertiary-spec)">
              ({report.failures.length})
            </span>
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
                <GroupedSection
                  key={key}
                  title={key}
                  rows={rows}
                  onUpdateFailureNote={handleUpdateFailureNote}
                />
              ))}
            </div>
          ) : (
            <ul
              className="flex flex-col gap-1"
              data-testid="validation-failure-list"
            >
              {filtered.map((f, i) => (
                <FailureRow
                  key={`${f.source_id}-${i}`}
                  failure={f}
                  onUpdateFailureNote={handleUpdateFailureNote}
                />
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </section>
  );
}
