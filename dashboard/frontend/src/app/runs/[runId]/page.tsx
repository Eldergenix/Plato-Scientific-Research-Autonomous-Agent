"use client";

import * as React from "react";
import { use as usePromise } from "react";
import {
  ManifestPanel,
  type RunManifest,
} from "@/components/manifest/manifest-panel";
import {
  EvidenceMatrixTable,
  type EvidenceMatrixData,
} from "@/components/manifest/evidence-matrix-table";
import {
  ValidationReportCard,
  type ValidationReport,
} from "@/components/manifest/validation-report-card";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

type Loadable<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T }
  | { kind: "missing" }
  | { kind: "error"; message: string };

async function fetchOptional<T>(path: string): Promise<Loadable<T>> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch (err) {
    return {
      kind: "error",
      message: err instanceof Error ? err.message : "Network error",
    };
  }
  if (resp.status === 404) return { kind: "missing" };
  if (!resp.ok) {
    return { kind: "error", message: `HTTP ${resp.status}` };
  }
  try {
    const data = (await resp.json()) as T;
    return { kind: "ready", data };
  } catch (err) {
    return {
      kind: "error",
      message: err instanceof Error ? err.message : "Failed to parse JSON",
    };
  }
}

interface RunDetailParams {
  runId: string;
}

export default function RunDetailPage({
  params,
}: {
  params: Promise<RunDetailParams>;
}) {
  // Next.js 15 dynamic route params arrive as a Promise; unwrap with React.use.
  const { runId } = usePromise(params);

  const [manifest, setManifest] =
    React.useState<Loadable<RunManifest>>({ kind: "loading" });
  const [evidence, setEvidence] =
    React.useState<Loadable<EvidenceMatrixData>>({ kind: "loading" });
  const [validation, setValidation] =
    React.useState<Loadable<ValidationReport>>({ kind: "loading" });

  React.useEffect(() => {
    let cancelled = false;
    setManifest({ kind: "loading" });
    setEvidence({ kind: "loading" });
    setValidation({ kind: "loading" });

    void Promise.all([
      fetchOptional<RunManifest>(`/runs/${runId}/manifest`),
      fetchOptional<EvidenceMatrixData>(`/runs/${runId}/evidence_matrix`),
      fetchOptional<ValidationReport>(`/runs/${runId}/validation_report`),
    ]).then(([m, e, v]) => {
      if (cancelled) return;
      setManifest(m);
      setEvidence(e);
      setValidation(v);
    });

    return () => {
      cancelled = true;
    };
  }, [runId]);

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <header
          className="surface-linear-card flex flex-col gap-1 px-4 py-3"
          style={{ border: "1px solid var(--color-border-card)" }}
        >
          <h1
            className="text-(--color-text-primary-strong)"
            style={{
              fontFamily: "Inter, var(--font-sans)",
              fontWeight: 510,
              fontSize: 22,
              letterSpacing: "-0.5px",
            }}
          >
            Run detail
          </h1>
          <p className="font-mono text-[12px] text-(--color-text-row-meta)">
            {runId}
          </p>
        </header>

        {/* Manifest */}
        <ManifestSection state={manifest} />

        {/* Validation report */}
        <ValidationSection state={validation} />

        {/* Evidence matrix */}
        <EvidenceSection state={evidence} />
      </div>
    </div>
  );
}

function ManifestSection({ state }: { state: Loadable<RunManifest> }) {
  if (state.kind === "loading") {
    return (
      <PlaceholderCard label="Manifest" message="Loading manifest…" />
    );
  }
  if (state.kind === "missing") {
    return (
      <PlaceholderCard
        label="Manifest"
        message="No manifest written for this run."
      />
    );
  }
  if (state.kind === "error") {
    return (
      <PlaceholderCard
        label="Manifest"
        message={`Failed to load manifest: ${state.message}`}
        tone="error"
      />
    );
  }
  return <ManifestPanel manifest={state.data} />;
}

function ValidationSection({ state }: { state: Loadable<ValidationReport> }) {
  if (state.kind === "loading") {
    return (
      <PlaceholderCard label="Validation report" message="Loading report…" />
    );
  }
  if (state.kind === "missing") {
    return (
      <PlaceholderCard
        label="Validation report"
        message="No validation report — citation check has not run yet."
      />
    );
  }
  if (state.kind === "error") {
    return (
      <PlaceholderCard
        label="Validation report"
        message={`Failed to load report: ${state.message}`}
        tone="error"
      />
    );
  }
  return <ValidationReportCard report={state.data} />;
}

function EvidenceSection({ state }: { state: Loadable<EvidenceMatrixData> }) {
  if (state.kind === "loading") {
    return (
      <PlaceholderCard label="Evidence matrix" message="Loading evidence…" />
    );
  }
  if (state.kind === "missing") {
    // Backend returns 404 only when the run dir is gone — fall back to the
    // empty-state card the table already renders for "no links yet".
    return <EvidenceMatrixTable data={{ claims: [], evidence_links: [] }} />;
  }
  if (state.kind === "error") {
    return (
      <PlaceholderCard
        label="Evidence matrix"
        message={`Failed to load evidence: ${state.message}`}
        tone="error"
      />
    );
  }
  return <EvidenceMatrixTable data={state.data} />;
}

function PlaceholderCard({
  label,
  message,
  tone = "neutral",
}: {
  label: string;
  message: string;
  tone?: "neutral" | "error";
}) {
  return (
    <section
      className="surface-linear-card px-4 py-4"
      data-testid={`placeholder-${label.toLowerCase().replace(/\s+/g, "-")}`}
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <div className="font-label" style={{ marginBottom: 6 }}>
        {label}
      </div>
      <p
        className="text-[13px]"
        style={{
          color:
            tone === "error"
              ? "var(--color-status-red-spec)"
              : "var(--color-text-row-meta)",
        }}
      >
        {message}
      </p>
    </section>
  );
}
