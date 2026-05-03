"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { ClarifierStep } from "@/components/clarifier/clarifier-step";
import {
  ClarifyingQuestionsModal,
  type ClarificationsPayload,
} from "@/components/clarifier/clarifying-questions-modal";
import { RunDetailNav } from "@/components/manifest/run-detail-nav";
import { getActiveRunId, getActiveUserId, setActiveRunId } from "@/lib/api";
import { cn } from "@/lib/utils";

/* -----------------------------------------------------------------------------
 * Loadable<T> + fetchOptional (inline; no shared util exists yet)
 * ---------------------------------------------------------------------------*/

type Loadable<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "error"; error: string };

async function fetchOptional<T>(url: string): Promise<T | null> {
  // Mirror fetchJson's correlation headers so the dashboard backend
  // can join this fetch into the same X-Plato-Run-Id / X-Plato-User
  // trace as the rest of the run-detail subtree.
  const headers: Record<string, string> = {};
  const runId = getActiveRunId();
  if (runId) headers["X-Plato-Run-Id"] = runId;
  const userId = getActiveUserId();
  if (userId) headers["X-Plato-User"] = userId;

  const resp = await fetch(url, {
    cache: "no-store",
    credentials: "include",
    headers,
  });
  if (resp.status === 404) return null;
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const msg =
      body?.detail?.message ?? body?.detail?.code ?? `HTTP ${resp.status}`;
    throw new Error(String(msg));
  }
  return (await resp.json()) as T;
}

/* -----------------------------------------------------------------------------
 * Page
 * ---------------------------------------------------------------------------*/

export default function ClarifyPage() {
  const params = useParams<{ runId: string }>();
  const runId = params?.runId ?? "";

  const [loadable, setLoadable] = React.useState<Loadable<ClarificationsPayload>>(
    { state: "loading" },
  );
  // Always-open modal for the full-page direct-link flow. Closing it
  // collapses back to the inline ClarifierStep so users can re-open.
  const [modalOpen, setModalOpen] = React.useState(true);

  // Bind run id to the api.ts module-level store so the local
  // fetchOptional (which reads getActiveRunId) carries
  // X-Plato-Run-Id. Cleared on unmount.
  React.useEffect(() => {
    if (!runId) return;
    setActiveRunId(runId);
    return () => setActiveRunId(null);
  }, [runId]);

  const refresh = React.useCallback(async () => {
    if (!runId) return;
    try {
      const data = await fetchOptional<ClarificationsPayload>(
        `/api/v1/runs/${runId}/clarifications`,
      );
      if (data == null) {
        setLoadable({ state: "error", error: "Run not found." });
        return;
      }
      setLoadable({ state: "ready", data });
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to load clarifications";
      setLoadable({ state: "error", error: msg });
    }
  }, [runId]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const headerCard = (
    <header
      className="surface-linear-card flex flex-col gap-1 px-4 py-3"
      data-testid="clarify-header"
    >
      <h1 className="text-[15px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
        Clarification
      </h1>
      <p className="font-mono text-[12px] text-(--color-text-row-meta)">
        run_id: {runId || "(missing)"}
      </p>
    </header>
  );

  const content = (() => {
    if (loadable.state === "loading") {
      return (
        <div
          data-testid="clarify-loading"
          className="surface-linear-card flex items-center justify-center px-4 py-8 text-[13px] text-(--color-text-row-meta)"
        >
          Loading clarifications...
        </div>
      );
    }
    if (loadable.state === "error") {
      return (
        <div
          data-testid="clarify-error"
          className="surface-linear-card px-4 py-3 text-[13px] text-(--color-status-red)"
        >
          {loadable.error}
        </div>
      );
    }

    const payload = loadable.data;
    if (!payload.needs_clarification) {
      return (
        <div
          data-testid="clarify-empty"
          className="surface-linear-card px-4 py-3 text-[13px] text-(--color-text-row-meta)"
        >
          No clarifying questions for this run.
        </div>
      );
    }

    return (
      <>
        <ClarifierStep
          payload={payload}
          runId={runId}
          onSubmitted={() => void refresh()}
        />
        <ClarifyingQuestionsModal
          payload={payload}
          runId={runId}
          open={modalOpen && !payload.answers_submitted}
          onOpenChange={(v) => {
            setModalOpen(v);
            if (!v) void refresh();
          }}
          onSubmitted={() => {
            setModalOpen(false);
            void refresh();
          }}
        />
      </>
    );
  })();

  return (
    <main
      className={cn(
        "min-h-screen w-full bg-(--color-bg-page) text-(--color-text-primary)",
        "flex flex-col gap-3 p-4",
      )}
    >
      {headerCard}
      <RunDetailNav runId={runId} />
      {content}
    </main>
  );
}
