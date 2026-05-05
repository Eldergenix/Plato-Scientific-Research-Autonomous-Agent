"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import {
  CritiquePanel,
  type ReviewsPayload,
} from "@/components/review/critique-panel";
import { RevisionCounter } from "@/components/review/revision-counter";
import { RunDetailNav } from "@/components/manifest/run-detail-nav";
import { useFocusRefresh } from "@/lib/use-focus-refresh";

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

// Placeholder param emitted by the static-export build — see clarify/client.tsx.
const PLACEHOLDER_RUN_ID = "_";

export default function RunReviewsClient() {
  const params = useParams<{ runId: string }>();
  const runId = params?.runId ?? "";
  const ready = !!runId && runId !== PLACEHOLDER_RUN_ID;

  const [reviews, setReviews] = React.useState<Loadable<ReviewsPayload>>({
    kind: "loading",
  });

  const refresh = React.useCallback(() => {
    if (!ready) return;
    void fetchOptional<ReviewsPayload>(`/runs/${runId}/critiques`).then(setReviews);
  }, [ready, runId]);

  React.useEffect(() => {
    if (!ready) {
      // Iter-7: same fix as research/literature/citations — drop into
      // "missing" so the empty-state placeholder shows instead of a
      // permanent loading spinner.
      setReviews({ kind: "missing" });
      return;
    }
    let cancelled = false;
    setReviews({ kind: "loading" });
    void fetchOptional<ReviewsPayload>(`/runs/${runId}/critiques`).then((r) => {
      if (cancelled) return;
      setReviews(r);
    });
    return () => {
      cancelled = true;
    };
  }, [ready, runId]);

  // Iter-11: refresh on focus + 15s polling — see citations/client.tsx.
  useFocusRefresh(refresh, { enabled: ready });

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
    // Iter-7: render the RevisionCounter with state=null (it has its
    // own "No revision in progress" empty state) so the user still sees
    // both panels — the previous version omitted the counter entirely.
    return (
      <>
        <RevisionCounter state={null} />
        <PlaceholderCard
          label="Reviewer panel"
          message="No critiques written for this run yet."
        />
      </>
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
