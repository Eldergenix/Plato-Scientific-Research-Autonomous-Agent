"use client";

import * as React from "react";
import { use as usePromise } from "react";
import {
  CounterEvidenceList,
  type CounterEvidencePayload,
} from "@/components/research/counter-evidence-list";
import {
  GapsPanel,
  type GapsPayload,
} from "@/components/research/gaps-panel";
import { RunDetailNav } from "@/components/manifest/run-detail-nav";
import { getActiveRunId, getActiveUserId, setActiveRunId } from "@/lib/api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

type Loadable<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T }
  | { kind: "missing" }
  | { kind: "error"; message: string };

async function fetchOptional<T>(path: string): Promise<Loadable<T>> {
  // Mirror fetchJson's correlation headers so the dashboard backend
  // can join SSR-style fetches into the same X-Plato-Run-Id /
  // X-Plato-User trace as the rest of the run-detail subtree.
  const headers: Record<string, string> = { Accept: "application/json" };
  const runId = getActiveRunId();
  if (runId) headers["X-Plato-Run-Id"] = runId;
  const userId = getActiveUserId();
  if (userId) headers["X-Plato-User"] = userId;

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      headers,
      cache: "no-store",
      credentials: "include",
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

interface RunResearchParams {
  runId: string;
}

export default function RunResearchPage({
  params,
}: {
  params: Promise<RunResearchParams>;
}) {
  const { runId } = usePromise(params);

  const [counter, setCounter] =
    React.useState<Loadable<CounterEvidencePayload>>({ kind: "loading" });
  const [gaps, setGaps] = React.useState<Loadable<GapsPayload>>({ kind: "loading" });

  // Bind run id to the api.ts module-level store so the local
  // fetchOptional (which reads getActiveRunId) carries
  // X-Plato-Run-Id. Cleared on unmount.
  React.useEffect(() => {
    setActiveRunId(runId);
    return () => setActiveRunId(null);
  }, [runId]);

  React.useEffect(() => {
    let cancelled = false;
    setCounter({ kind: "loading" });
    setGaps({ kind: "loading" });

    void Promise.all([
      fetchOptional<CounterEvidencePayload>(`/runs/${runId}/counter_evidence`),
      fetchOptional<GapsPayload>(`/runs/${runId}/gaps`),
    ]).then(([c, g]) => {
      if (cancelled) return;
      setCounter(c);
      setGaps(g);
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
          data-testid="research-header"
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
            Research signals
          </h1>
          <p className="font-mono text-[12px] text-(--color-text-row-meta)">
            {runId}
          </p>
        </header>

        <RunDetailNav runId={runId} />

        <CounterEvidenceSection state={counter} />
        <GapsSection state={gaps} />
      </div>
    </div>
  );
}

function CounterEvidenceSection({
  state,
}: {
  state: Loadable<CounterEvidencePayload>;
}) {
  if (state.kind === "loading") {
    return (
      <PlaceholderCard
        label="Counter-evidence"
        message="Loading counter-evidence…"
      />
    );
  }
  if (state.kind === "missing") {
    return (
      <PlaceholderCard
        label="Counter-evidence"
        message="Run not found — counter-evidence search has no record for this run."
      />
    );
  }
  if (state.kind === "error") {
    return (
      <PlaceholderCard
        label="Counter-evidence"
        message={`Failed to load: ${state.message}`}
        tone="error"
      />
    );
  }
  return <CounterEvidenceList payload={state.data} />;
}

function GapsSection({ state }: { state: Loadable<GapsPayload> }) {
  if (state.kind === "loading") {
    return (
      <PlaceholderCard label="Research gaps" message="Loading gap analysis…" />
    );
  }
  if (state.kind === "missing") {
    return (
      <PlaceholderCard
        label="Research gaps"
        message="Run not found — gap analysis has no record for this run."
      />
    );
  }
  if (state.kind === "error") {
    return (
      <PlaceholderCard
        label="Research gaps"
        message={`Failed to load: ${state.message}`}
        tone="error"
      />
    );
  }
  return <GapsPanel payload={state.data} />;
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
