"use client";

import * as React from "react";
import {
  NoveltyScoreCard,
  type NoveltyPayload,
} from "@/components/novelty/novelty-score-card";
import {
  SourceBreakdown,
  type RetrievalSummaryPayload,
} from "@/components/retrieval/source-breakdown";
import { RunDetailNav } from "@/components/manifest/run-detail-nav";

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

interface LiteraturePageParams {
  runId: string;
}

export default function LiteratureClient({
  params,
}: {
  params: Promise<LiteraturePageParams>;
}) {
  // Next.js 15 dynamic route params arrive as a Promise; unwrap with React.use.
  const { runId } = React.use(params);

  const [novelty, setNovelty] =
    React.useState<Loadable<NoveltyPayload>>({ kind: "loading" });
  const [retrieval, setRetrieval] =
    React.useState<Loadable<RetrievalSummaryPayload>>({ kind: "loading" });

  React.useEffect(() => {
    let cancelled = false;
    setNovelty({ kind: "loading" });
    setRetrieval({ kind: "loading" });

    void Promise.all([
      fetchOptional<NoveltyPayload>(`/runs/${runId}/novelty`),
      fetchOptional<RetrievalSummaryPayload>(`/runs/${runId}/retrieval_summary`),
    ]).then(([n, r]) => {
      if (cancelled) return;
      setNovelty(n);
      setRetrieval(r);
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
            Literature signals
          </h1>
          <p className="font-mono text-[12px] text-(--color-text-row-meta)">
            {runId}
          </p>
        </header>

        <RunDetailNav runId={runId} />

        <NoveltySection state={novelty} />
        <RetrievalSection state={retrieval} />
      </div>
    </div>
  );
}

function NoveltySection({ state }: { state: Loadable<NoveltyPayload> }) {
  if (state.kind === "loading") {
    return (
      <PlaceholderCard label="Novelty score" message="Loading novelty…" />
    );
  }
  if (state.kind === "missing") {
    return (
      <PlaceholderCard
        label="Novelty score"
        message="Novelty score not computed."
      />
    );
  }
  if (state.kind === "error") {
    return (
      <PlaceholderCard
        label="Novelty score"
        message={`Failed to load novelty: ${state.message}`}
        tone="error"
      />
    );
  }
  return <NoveltyScoreCard payload={state.data} />;
}

function RetrievalSection({
  state,
}: {
  state: Loadable<RetrievalSummaryPayload>;
}) {
  if (state.kind === "loading") {
    return (
      <PlaceholderCard
        label="Retrieval sources"
        message="Loading retrieval breakdown…"
      />
    );
  }
  if (state.kind === "missing") {
    return (
      <SourceBreakdown
        payload={{
          by_adapter: [],
          total_unique: 0,
          total_returned: 0,
          queries: [],
          samples: [],
        }}
      />
    );
  }
  if (state.kind === "error") {
    return (
      <PlaceholderCard
        label="Retrieval sources"
        message={`Failed to load retrieval breakdown: ${state.message}`}
        tone="error"
      />
    );
  }
  return <SourceBreakdown payload={state.data} />;
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
