"use client";

import * as React from "react";
import { use as usePromise } from "react";
import {
  CitationGraphView,
  type CitationGraphPayload,
} from "@/components/citations/citation-graph-view";
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
  if (!resp.ok) return { kind: "error", message: `HTTP ${resp.status}` };
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

interface CitationPageParams {
  runId: string;
}

const EMPTY_PAYLOAD: CitationGraphPayload = {
  seeds: [],
  expanded: [],
  edges: [],
  stats: {
    seed_count: 0,
    expanded_count: 0,
    edge_count: 0,
    duplicates_filtered: 0,
  },
};

// TODO(i18n+seo): convert to server-wrapper pattern (see ./literature/page.tsx).
export default function CitationsPage({
  params,
}: {
  params: Promise<CitationPageParams>;
}) {
  const { runId } = usePromise(params);
  const [state, setState] = React.useState<Loadable<CitationGraphPayload>>({
    kind: "loading",
  });

  React.useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    void fetchOptional<CitationGraphPayload>(
      `/runs/${runId}/citation_graph`,
    ).then((s) => {
      if (!cancelled) setState(s);
    });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8 text-(--color-text-primary)">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <header
          className="surface-linear-card flex flex-col gap-1 px-4 py-3"
          data-testid="citations-page-header"
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
            Citation graph
          </h1>
          <p className="font-mono text-[12px] text-(--color-text-row-meta)">
            {runId}
          </p>
        </header>

        <RunDetailNav runId={runId} />

        <Body state={state} />
      </div>
    </div>
  );
}

function Body({ state }: { state: Loadable<CitationGraphPayload> }) {
  if (state.kind === "loading") {
    return (
      <Placeholder
        message="Loading citation graph…"
        testId="citations-loading"
      />
    );
  }
  if (state.kind === "missing") {
    // Backend returns 404 only when the run dir is gone — fall back to the
    // empty-state card the view itself renders for "no graph computed".
    return <CitationGraphView payload={EMPTY_PAYLOAD} />;
  }
  if (state.kind === "error") {
    return (
      <Placeholder
        message={`Failed to load citation graph: ${state.message}`}
        tone="error"
        testId="citations-error"
      />
    );
  }
  return <CitationGraphView payload={state.data} />;
}

function Placeholder({
  message,
  tone = "neutral",
  testId,
}: {
  message: string;
  tone?: "neutral" | "error";
  testId: string;
}) {
  return (
    <section className="surface-linear-card px-4 py-6" data-testid={testId}>
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
