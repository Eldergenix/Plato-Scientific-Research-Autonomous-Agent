"use client";

import * as React from "react";
import { ExternalLink, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export interface NoveltyPayload {
  score: number | null;
  max_similarity: number | null;
  nearest_source_id: string | null;
  llm_score: number | null;
  embedding_score: number | null;
  agreement: boolean | null;
}

/**
 * Render an external-link URL for a source identifier — same DOI / arxiv
 * resolution as ``manifest-panel.tsx``. Inlined here to keep the card
 * standalone and avoid widening that module's public surface.
 */
function sourceUrl(id: string): string | null {
  const trimmed = id.trim();
  if (!trimmed) return null;
  if (/^10\.\d{4,9}\//.test(trimmed)) return `https://doi.org/${trimmed}`;
  if (/^arxiv:/i.test(trimmed)) {
    return `https://arxiv.org/abs/${trimmed.slice(6)}`;
  }
  if (/^\d{4}\.\d{4,5}(v\d+)?$/.test(trimmed)) {
    return `https://arxiv.org/abs/${trimmed}`;
  }
  return null;
}

function formatPctScore(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function formatSubScore(value: number | null): string {
  if (value == null) return "—";
  return value.toFixed(2);
}

/**
 * Map composite novelty into a green/amber/red traffic light. Thresholds
 * match the plan's spec: ≥ 0.7 high novelty (green), 0.4–0.7 amber,
 * < 0.4 low novelty (red). The same colour drives both the big number
 * and the subtle ring around it.
 */
function noveltyTone(score: number): {
  color: string;
  ring: string;
  label: "high" | "moderate" | "low";
} {
  if (score >= 0.7) {
    return {
      color: "var(--color-status-green-spec)",
      ring: "var(--color-status-green-spec)",
      label: "high",
    };
  }
  if (score >= 0.4) {
    return {
      color: "var(--color-status-amber-spec)",
      ring: "var(--color-status-amber-spec)",
      label: "moderate",
    };
  }
  return {
    color: "var(--color-status-red-spec)",
    ring: "var(--color-status-red-spec)",
    label: "low",
  };
}

export function NoveltyScoreCard({ payload }: { payload: NoveltyPayload }) {
  if (payload.score == null) {
    return (
      <section
        className="surface-linear-card flex flex-col items-center justify-center gap-3 py-12 px-6 text-center"
        data-testid="novelty-score-empty"
        style={{ border: "1px solid var(--color-border-card)" }}
      >
        <div className="flex size-10 items-center justify-center rounded-full bg-(--color-bg-pill-inactive) text-(--color-text-tertiary)">
          <Sparkles size={18} />
        </div>
        <p className="text-[13px] text-(--color-text-row-meta) max-w-md">
          Novelty score not computed.
        </p>
      </section>
    );
  }

  const tone = noveltyTone(payload.score);
  const nearestUrl = payload.nearest_source_id
    ? sourceUrl(payload.nearest_source_id)
    : null;

  const agreement = payload.agreement;
  const llm = payload.llm_score;
  const emb = payload.embedding_score;

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="novelty-score-card"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <Sparkles size={16} style={{ color: tone.color }} />
        <h2
          className="text-(--color-text-primary-strong) text-[15px]"
          style={{ fontWeight: 510 }}
        >
          Novelty score
        </h2>
        <div aria-hidden className="flex-1" />
        <span
          className="font-label uppercase"
          style={{ color: tone.color, letterSpacing: "0.05em" }}
        >
          {tone.label}
        </span>
      </header>

      <div className="flex items-baseline gap-3 px-4 py-4">
        <span
          className="font-mono tabular-nums"
          style={{
            fontSize: 40,
            fontWeight: 500,
            lineHeight: 1,
            color: tone.color,
          }}
          data-testid="novelty-score-value"
        >
          {formatPctScore(payload.score)}
        </span>
        <span className="text-[12px] text-(--color-text-row-meta)">
          composite novelty
        </span>
      </div>

      <div
        className="grid gap-3 px-4 py-3"
        style={{
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          borderTop: "1px solid var(--color-border-standard)",
        }}
      >
        <Metric label="LLM judge" value={formatSubScore(llm)} />
        <Metric label="Embedding" value={formatSubScore(emb)} />
        <Metric
          label="Max similarity"
          value={formatSubScore(payload.max_similarity)}
        />
      </div>

      <div
        className="px-4 py-3 text-[12px] text-(--color-text-row-meta)"
        style={{ borderTop: "1px solid var(--color-border-standard)" }}
        data-testid="novelty-score-subline"
      >
        Composite of LLM (
        <span className="font-mono tabular-nums text-(--color-text-row-title)">
          {formatSubScore(llm)}
        </span>
        ) + embedding (
        <span className="font-mono tabular-nums text-(--color-text-row-title)">
          {formatSubScore(emb)}
        </span>
        ){" | "}
        agreement:{" "}
        {agreement === true ? (
          <span
            aria-label="agreement"
            className="font-mono"
            style={{ color: "var(--color-status-green-spec)" }}
          >
            ✓
          </span>
        ) : agreement === false ? (
          <span
            aria-label="disagreement"
            className="font-mono"
            style={{ color: "var(--color-status-red-spec)" }}
          >
            ✗
          </span>
        ) : (
          <span className="font-mono text-(--color-text-row-meta)">—</span>
        )}
      </div>

      {payload.nearest_source_id ? (
        <div
          className="px-4 py-3 flex flex-col gap-1"
          style={{ borderTop: "1px solid var(--color-border-standard)" }}
        >
          <div className="font-label">Nearest prior work</div>
          {nearestUrl ? (
            <a
              href={nearestUrl}
              target="_blank"
              rel="noreferrer noopener"
              className={cn(
                "inline-flex items-center gap-1 font-mono text-[12px] self-start",
                "text-(--color-brand-interactive) hover:underline",
              )}
              data-testid="novelty-nearest-link"
            >
              {payload.nearest_source_id}
              <ExternalLink size={10} />
            </a>
          ) : (
            <span
              className="font-mono text-[12px] text-(--color-text-row-title)"
              data-testid="novelty-nearest-id"
            >
              {payload.nearest_source_id}
            </span>
          )}
        </div>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="font-label">{label}</span>
      <span
        className={cn(
          "text-(--color-text-primary-strong)",
          "tabular-nums font-mono text-[14px]",
        )}
      >
        {value}
      </span>
    </div>
  );
}
