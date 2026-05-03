"use client";

import * as React from "react";
import { MessagesSquare } from "lucide-react";
import {
  CritiqueAxisCard,
  type CritiqueAxis,
} from "@/components/review/critique-axis-card";
import type { RevisionState } from "@/components/review/revision-counter";

export interface CritiqueDigest {
  max_severity: number;
  iteration: number;
  issues: Array<{
    reviewer: string;
    section?: string;
    issue?: string;
    fix?: string | null;
  }>;
}

export interface ReviewsPayload {
  critiques: Partial<Record<"methodology" | "statistics" | "novelty" | "writing", CritiqueAxis | null>>;
  digest: CritiqueDigest | null;
  revision_state: RevisionState | null;
}

const AXES = ["methodology", "statistics", "novelty", "writing"] as const;

export function CritiquePanel({ payload }: { payload: ReviewsPayload }) {
  const critiques = payload.critiques ?? {};
  const allEmpty = AXES.every((axis) => !critiques[axis]);
  const iterationLabel = formatIterationBadge(payload.revision_state, payload.digest);

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="critique-panel"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <MessagesSquare size={16} className="text-(--color-text-tertiary)" />
          <h2
            className="text-(--color-text-primary-strong) text-[15px]"
            style={{ fontWeight: 510 }}
          >
            Reviewer panel
          </h2>
        </div>
        {iterationLabel ? (
          <span
            className="font-mono tabular-nums text-[11px] text-(--color-text-row-meta)"
            data-testid="critique-iteration-badge"
          >
            {iterationLabel}
          </span>
        ) : null}
      </header>

      {allEmpty ? (
        <div className="px-4 py-6 text-[13px] text-(--color-text-row-meta)">
          Reviewers haven&apos;t run yet.
        </div>
      ) : (
        <div
          className="grid gap-3 px-4 py-4"
          style={{
            gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          }}
          data-testid="critique-axis-grid"
        >
          {AXES.map((axis) => (
            <CritiqueAxisCard
              key={axis}
              axis={axis}
              data={critiques[axis] ?? null}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function formatIterationBadge(
  rev: RevisionState | null,
  digest: CritiqueDigest | null,
): string | null {
  if (rev) {
    return `Iteration ${rev.iteration} / ${rev.max_iterations}`;
  }
  if (digest && Number.isFinite(digest.iteration)) {
    return `Iteration ${digest.iteration}`;
  }
  return null;
}
