"use client";

import * as React from "react";
import { use as usePromise } from "react";
import {
  CritiquePanel,
  type ReviewsPayload,
} from "@/components/review/critique-panel";
import { RevisionCounter } from "@/components/review/revision-counter";
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

interface RunReviewsParams {
  runId: string;
}

export default function RunReviewsPage({
  params,
}: {
  params: Promise<RunReviewsParams>;
}) {
  // Next.js 15 dynamic-route params are a Promise; unwrap with React.use.
  const { runId } = usePromise(params);

  const [reviews, setReviews] = React.useState<Loadable<ReviewsPayload>>({
    kind: "loading",
  });

  // Bind run id to the api.ts module-level store so the local
  // fetchOptional (which reads getActiveRunId) carries
  // X-Plato-Run-Id. Cleared on unmount.
  React.useEffect(() => {
    setActiveRunId(runId);
    return () => setActiveRunId(null);
  }, [runId]);

  React.useEffect(() => {
    let cancelled = false;
    setReviews({ kind: "loading" });
    void fetchOptional<ReviewsPayload>(`/runs/${runId}/critiques`).then((r) => {
      if (cancelled) return;
      setReviews(r);
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
            Run reviews
          </h1>
          <p className="font-mono text-[12px] text-(--color-text-row-meta)">
            {runId}
          </p>
        </header>

        <RunDetailNav runId={runId} />

        <ReviewsSection state={reviews} />
      </div>
    </div>
  );
}

function ReviewsSection({ state }: { state: Loadable<ReviewsPayload> }) {
  if (state.kind === "loading") {
    return (
      <>
        <PlaceholderCard label="Revision" message="Loading revision state…" />
        <PlaceholderCard label="Reviewer panel" message="Loading critiques…" />
      </>
    );
  }
  if (state.kind === "missing") {
    return (
      <PlaceholderCard
        label="Reviewer panel"
        message="No critiques written for this run yet."
      />
    );
  }
  if (state.kind === "error") {
    return (
      <PlaceholderCard
        label="Reviewer panel"
        message={`Failed to load critiques: ${state.message}`}
        tone="error"
      />
    );
  }

  return (
    <>
      <RevisionCounter state={state.data.revision_state} />
      <CritiquePanel payload={state.data} />
    </>
  );
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
