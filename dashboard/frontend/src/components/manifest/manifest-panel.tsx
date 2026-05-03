"use client";

import * as React from "react";
import { Activity, ExternalLink, GitCommit } from "lucide-react";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

export interface NodeTelemetry {
  ti: number;
  to: number;
  calls: number;
  cost_usd: number;
}

export interface RunManifest {
  run_id: string;
  workflow: string;
  started_at: string;
  ended_at?: string | null;
  status: "running" | "success" | "error" | string;
  domain: string;
  git_sha?: string;
  project_sha?: string;
  models: Record<string, string>;
  prompt_hashes?: Record<string, string>;
  seeds?: Record<string, number>;
  source_ids: string[];
  cost_usd: number;
  tokens_in: number;
  tokens_out: number;
  // Per-node telemetry breakdown — populated when LLM_call/LLM_call_stream
  // run with a manifest recorder seeded on state. Absent on legacy runs.
  tokens_per_node?: Record<string, NodeTelemetry>;
  error?: string | null;
  user_id?: string | null;
  // Injected by the manifest endpoint from the run dir layout so the
  // run-detail page can subscribe to the per-project SSE stream without
  // a separate lookup. Absent for flat (single-project) installs.
  project_id?: string | null;
}

const STATUS_TONE: Record<string, "green" | "amber" | "red" | "neutral"> = {
  success: "green",
  running: "amber",
  error: "red",
};

function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

function formatCostUsd(usd: number): string {
  return `$${usd.toFixed(4)}`;
}

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

/**
 * Render an external-link URL for a source identifier.
 *
 * The manifest's ``source_ids`` are opaque strings; the most common
 * forms we care about are bare DOIs (``10.x/...``) and arxiv IDs
 * (``arxiv:1234.5678`` or ``2403.12345``). Anything else falls through
 * to plain text — no clickable link.
 *
 * Defined at module scope so its identity is stable across renders —
 * the run-detail page polls this panel every 2s and we don't want to
 * reallocate a new function each tick.
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

export function ManifestPanel({ manifest }: { manifest: RunManifest }) {
  const tone = STATUS_TONE[manifest.status] ?? "neutral";
  const truncatedRunId =
    manifest.run_id.length > 8 ? `${manifest.run_id.slice(0, 8)}…` : manifest.run_id;

  // Memoize the entries array so it has stable identity between polls.
  // The run-detail page refetches the manifest every 2s; without this,
  // the table body re-keys on every tick even when models hasn't changed.
  const modelEntries = React.useMemo(
    () => Object.entries(manifest.models ?? {}),
    [manifest.models],
  );

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="manifest-panel"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      {/* Header */}
      <header
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <Activity size={16} className="text-(--color-text-tertiary)" />
          <div className="flex flex-col min-w-0">
            <div className="flex items-baseline gap-2">
              <h2
                className="text-(--color-text-primary-strong) text-[15px]"
                style={{ fontWeight: 510 }}
              >
                Run manifest
              </h2>
              <span
                className="font-mono text-[12px] text-(--color-text-row-meta) truncate"
                title={manifest.run_id}
              >
                {truncatedRunId}
              </span>
            </div>
            <div className="text-[12px] text-(--color-text-tertiary)">
              <span className="font-mono">{manifest.workflow}</span>
              <span aria-hidden> · </span>
              <span>{manifest.domain}</span>
            </div>
          </div>
        </div>
        <Pill tone={tone}>{manifest.status}</Pill>
      </header>

      {/* Cost / token row */}
      <div
        className="grid gap-3 px-4 py-3"
        style={{
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          borderBottom: "1px solid var(--color-border-standard)",
        }}
      >
        <Metric label="Tokens in" value={formatTokens(manifest.tokens_in)} />
        <Metric label="Tokens out" value={formatTokens(manifest.tokens_out)} />
        <Metric label="Cost" value={formatCostUsd(manifest.cost_usd)} mono />
      </div>

      {/* Models */}
      <div
        className="px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="font-label" style={{ marginBottom: 6 }}>
          Models
        </div>
        {modelEntries.length === 0 ? (
          <p className="text-[12px] text-(--color-text-row-meta)">
            No models recorded.
          </p>
        ) : (
          <table className="w-full text-[12px]" data-testid="manifest-models-table">
            <thead>
              <tr className="text-left text-(--color-text-tertiary)">
                <th className="font-medium pb-1.5 pr-3">Role</th>
                <th className="font-medium pb-1.5">Model</th>
              </tr>
            </thead>
            <tbody>
              {modelEntries.map(([role, model]) => (
                <tr
                  key={role}
                  className="text-(--color-text-row-title)"
                  style={{ borderTop: "1px solid var(--color-border-standard)" }}
                >
                  <td className="py-1.5 pr-3 font-mono text-(--color-text-row-meta)">
                    {role}
                  </td>
                  <td className="py-1.5 font-mono">{model}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Sources */}
      <div
        className="px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="font-label" style={{ marginBottom: 6 }}>
          Sources ({manifest.source_ids.length})
        </div>
        {manifest.source_ids.length === 0 ? (
          <p className="text-[12px] text-(--color-text-row-meta)">
            No sources cited.
          </p>
        ) : (
          <ul className="flex flex-col gap-1">
            {manifest.source_ids.map((id) => {
              const url = sourceUrl(id);
              return (
                <li
                  key={id}
                  className="flex items-center gap-1.5 text-[12px] text-(--color-text-row-title)"
                >
                  {url ? (
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className={cn(
                        "inline-flex items-center gap-1 font-mono",
                        "text-(--color-brand-interactive) hover:underline",
                      )}
                    >
                      {id}
                      <ExternalLink size={10} />
                    </a>
                  ) : (
                    <span className="font-mono text-(--color-text-row-meta)">{id}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Footer: timestamps + git */}
      <footer
        className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-3 text-[11px] text-(--color-text-row-meta)"
      >
        <span>
          <span className="text-(--color-text-tertiary)">Started </span>
          {formatTimestamp(manifest.started_at)}
        </span>
        <span>
          <span className="text-(--color-text-tertiary)">Ended </span>
          {formatTimestamp(manifest.ended_at)}
        </span>
        {manifest.git_sha ? (
          <span className="inline-flex items-center gap-1 font-mono">
            <GitCommit size={11} />
            {manifest.git_sha.slice(0, 8)}
          </span>
        ) : null}
      </footer>

      {manifest.error ? (
        <div
          className="px-4 py-2 text-[12px] text-(--color-status-red-spec)"
          style={{ borderTop: "1px solid var(--color-border-standard)" }}
        >
          {manifest.error}
        </div>
      ) : null}
    </section>
  );
}

function Metric({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <span className="font-label">{label}</span>
      <span
        className={cn(
          "text-(--color-text-primary-strong)",
          "tabular-nums",
          mono ? "font-mono text-[14px]" : "font-mono text-[14px]",
        )}
      >
        {value}
      </span>
    </div>
  );
}
