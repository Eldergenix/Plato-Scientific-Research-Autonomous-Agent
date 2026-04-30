"use client";

import * as React from "react";
import { Star } from "lucide-react";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";
import type { LoopTsvRow } from "./loop-api";

export interface LoopHistoryProps {
  rows: LoopTsvRow[];
}

function statusTone(status: string) {
  switch (status) {
    case "keep":
      return "green";
    case "discard":
      return "neutral";
    case "interrupted":
      return "amber";
    case "error":
      return "red";
    default:
      return "neutral";
  }
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatComposite(value: number): string {
  if (Number.isNaN(value)) return "—";
  return value.toFixed(4);
}

const GRID = "grid-cols-[64px_120px_120px_88px_minmax(0,1fr)]";

export function LoopHistory({ rows }: LoopHistoryProps) {
  const bestIter = React.useMemo(() => {
    if (rows.length === 0) return null;
    let bestComposite = -Infinity;
    let bestIdx: number | null = null;
    rows.forEach((r) => {
      if (!Number.isNaN(r.composite) && r.composite > bestComposite) {
        bestComposite = r.composite;
        bestIdx = r.iter;
      }
    });
    return bestIdx;
  }, [rows]);

  if (rows.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-[8px] border border-dashed border-[#262628] py-10 text-[12px] text-(--color-text-tertiary-spec)"
        data-testid="loop-history-empty"
      >
        No iterations recorded yet.
      </div>
    );
  }

  return (
    <div
      className="surface-linear-card overflow-hidden"
      role="table"
      aria-label="Loop iteration history"
    >
      <div
        role="row"
        className={cn(
          "grid items-center gap-2 px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-(--color-text-tertiary-spec)",
          GRID,
          "border-b border-(--color-border-standard)",
        )}
      >
        <span role="columnheader">Iter</span>
        <span role="columnheader">Time</span>
        <span role="columnheader">Composite</span>
        <span role="columnheader">Status</span>
        <span role="columnheader">Description</span>
      </div>

      <div className="flex flex-col" data-testid="loop-history-rows">
        {rows.map((row) => {
          const isBest = bestIter === row.iter;
          return (
            <div
              key={`${row.iter}-${row.timestamp}`}
              role="row"
              data-iter={row.iter}
              data-status={row.status}
              className={cn(
                "grid items-center gap-2 px-3 py-2 text-[12.5px]",
                "border-b border-(--color-border-standard) last:border-b-0",
                "hover:bg-[rgba(255,255,255,0.02)]",
                GRID,
              )}
            >
              <span
                role="cell"
                className="font-mono tabular-nums text-(--color-text-row-meta)"
              >
                #{row.iter}
              </span>
              <span
                role="cell"
                className="font-mono text-[11.5px] text-(--color-text-tertiary-spec) tabular-nums"
                title={row.timestamp}
              >
                {formatTimestamp(row.timestamp)}
              </span>
              <span
                role="cell"
                className={cn(
                  "flex items-center gap-1 font-mono tabular-nums",
                  isBest
                    ? "text-(--color-status-emerald)"
                    : "text-(--color-text-row-title)",
                )}
              >
                {isBest ? (
                  <Star
                    size={11}
                    strokeWidth={1.75}
                    className="text-(--color-status-emerald)"
                    aria-label="best composite"
                  />
                ) : null}
                {formatComposite(row.composite)}
              </span>
              <span role="cell">
                <Pill tone={statusTone(row.status)} className="text-[11px]">
                  {row.status}
                </Pill>
              </span>
              <span
                role="cell"
                className="truncate text-(--color-text-row-meta)"
                title={row.description}
              >
                {row.description}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
