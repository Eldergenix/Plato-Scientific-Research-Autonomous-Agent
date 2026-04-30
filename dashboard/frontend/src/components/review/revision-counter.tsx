"use client";

import * as React from "react";
import { GitBranch } from "lucide-react";

export interface RevisionState {
  iteration: number;
  max_iterations: number;
}

type CounterTone = "emerald" | "amber" | "red";

const TONE_VAR: Record<CounterTone, string> = {
  emerald: "var(--color-status-emerald)",
  amber: "var(--color-status-amber-spec)",
  red: "var(--color-status-red-spec)",
};

/**
 * Pick the tone for a revision counter.
 *
 * - green: plenty of headroom (`iter < max - 1`)
 * - amber: one revision left (`iter == max - 1`)
 * - red: at or past the cap (`iter >= max`)
 */
function counterTone(iter: number, max: number): CounterTone {
  if (max <= 0) return "emerald";
  if (iter >= max) return "red";
  if (iter === max - 1) return "amber";
  return "emerald";
}

export function RevisionCounter({
  state,
}: {
  state: RevisionState | null;
}) {
  if (state === null) {
    return (
      <section
        className="surface-linear-card flex items-center gap-2 px-4 py-2.5"
        data-testid="revision-counter"
        style={{ border: "1px solid var(--color-border-card)" }}
      >
        <GitBranch size={14} className="text-(--color-text-tertiary)" />
        <span className="text-[12px] text-(--color-text-row-meta)">
          No revision in progress.
        </span>
      </section>
    );
  }

  const { iteration, max_iterations: max } = state;
  const tone = counterTone(iteration, max);
  const color = TONE_VAR[tone];

  return (
    <section
      className="surface-linear-card flex items-center justify-between gap-3 px-4 py-2.5"
      data-testid="revision-counter"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <div className="flex items-center gap-2">
        <GitBranch size={14} style={{ color }} />
        <span
          className="font-mono tabular-nums text-[13px]"
          style={{ color, fontWeight: 510 }}
          data-testid="revision-counter-label"
        >
          Revision {iteration} of {max}
        </span>
      </div>
      <ProgressDots iter={iteration} max={max} color={color} />
    </section>
  );
}

function ProgressDots({
  iter,
  max,
  color,
}: {
  iter: number;
  max: number;
  color: string;
}) {
  // Clamp dot count to a sane range. ``max`` should be >0 in practice but
  // guard so a corrupt payload can't blow up the page.
  const total = Math.max(0, Math.min(max, 12));
  const filled = Math.max(0, Math.min(iter, total));

  if (total === 0) return null;

  return (
    <div
      className="flex items-center gap-1"
      data-testid="revision-counter-dots"
      aria-label={`${filled} of ${total} revisions used`}
    >
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className="inline-block rounded-full"
          style={{
            width: 6,
            height: 6,
            border: `1px solid ${color}`,
            background: i < filled ? color : "transparent",
          }}
        />
      ))}
    </div>
  );
}
