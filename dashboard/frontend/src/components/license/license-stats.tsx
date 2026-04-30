"use client";

import * as React from "react";
import { CheckCircle2, AlertTriangle, HelpCircle, Package } from "lucide-react";
import { cn } from "@/lib/utils";

export interface LicenseSummary {
  total: number;
  compatible: number;
  incompatible: number;
  unknown: number;
}

type Tone = "neutral" | "green" | "amber" | "red";

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-(--color-text-primary-strong)",
  green: "text-(--color-status-emerald)",
  amber: "text-(--color-status-amber)",
  red: "text-(--color-status-red)",
};

/** Pick the headline tone based on how clean the license set is.
 *
 * Rate is `compatible / (total - unknown)` — unknowns are excluded from
 * the denominator so a few un-fingerprintable packages don't drag a
 * mostly-Apache project below the green threshold.
 */
function compatibilityTone(summary: LicenseSummary): Tone {
  const denom = Math.max(0, summary.total - summary.unknown);
  if (denom === 0) return "neutral";
  const rate = summary.compatible / denom;
  if (rate >= 0.95) return "green";
  if (rate >= 0.85) return "amber";
  return "red";
}

export function LicenseStats({ summary }: { summary: LicenseSummary }) {
  const tone = compatibilityTone(summary);

  return (
    <section
      className="grid grid-cols-2 gap-3 sm:grid-cols-4"
      data-testid="license-stats"
      aria-label="License audit summary"
    >
      <Card
        icon={Package}
        label="Total"
        value={summary.total}
        tone="neutral"
        testid="license-stats-total"
      />
      <Card
        icon={CheckCircle2}
        label="Compatible"
        value={summary.compatible}
        tone={tone}
        testid="license-stats-compatible"
      />
      <Card
        icon={AlertTriangle}
        label="Incompatible"
        value={summary.incompatible}
        tone={summary.incompatible > 0 ? "red" : "neutral"}
        testid="license-stats-incompatible"
      />
      <Card
        icon={HelpCircle}
        label="Unknown"
        value={summary.unknown}
        tone={summary.unknown > 0 ? "amber" : "neutral"}
        testid="license-stats-unknown"
      />
    </section>
  );
}

function Card({
  icon: Icon,
  label,
  value,
  tone,
  testid,
}: {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  label: string;
  value: number;
  tone: Tone;
  testid?: string;
}) {
  return (
    <div
      className="surface-linear-card flex flex-col gap-2 px-4 py-3"
      data-testid={testid}
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <div className="flex items-center justify-between">
        <span className="font-label">{label}</span>
        <Icon size={14} strokeWidth={1.75} className="text-(--color-text-tertiary)" />
      </div>
      <span
        className={cn(
          "font-mono tabular-nums text-[28px] leading-none",
          TONE_TEXT[tone],
        )}
        style={{ fontWeight: 510 }}
      >
        {value}
      </span>
    </div>
  );
}
