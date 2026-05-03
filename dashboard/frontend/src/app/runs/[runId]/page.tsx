"use client";

import * as React from "react";
import { use as usePromise } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { Ban, RotateCcw } from "lucide-react";
import {
  ManifestPanel,
  type RunManifest,
} from "@/components/manifest/manifest-panel";
import type { EvidenceMatrixData } from "@/components/manifest/evidence-matrix-table";
import type { ValidationReport } from "@/components/manifest/validation-report-card";
import { RunDetailNav } from "@/components/manifest/run-detail-nav";
import { AgentLogStream } from "@/components/shell/agent-log-stream";
import { TableSkeleton } from "@/components/shell/route-loading";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { api, ApiError, setActiveRunId } from "@/lib/api";
import type { LogLine, Run, StageId } from "@/lib/types";
import { cn } from "@/lib/utils";

// Code-split the four panels that render below-the-fold or only after
// async data lands. ManifestPanel stays static because it's the
// first-paint critical path; the live SSE log stream stays static so we
// don't defer the tail connection this page exists to surface. ssr:false
// because each panel is gated on a client-side fetch and would otherwise
// pay a hydration round-trip for a placeholder it can't render anyway.
const NodeBreakdown = dynamic(
  () =>
    import("@/components/manifest/node-breakdown").then((m) => ({
      default: m.NodeBreakdown,
    })),
  {
    ssr: false,
    loading: () => (
      <PanelSkeleton
        label="Node breakdown"
        columnWidths={["28%", "16%", "16%", "16%", "16%"]}
      />
    ),
  },
);
const EvidenceMatrixTable = dynamic(
  () =>
    import("@/components/manifest/evidence-matrix-table").then((m) => ({
      default: m.EvidenceMatrixTable,
    })),
  {
    ssr: false,
    loading: () => (
      <PanelSkeleton
        label="Evidence matrix"
        columnWidths={["32%", "20%", "16%", "16%", "12%"]}
      />
    ),
  },
);
const ValidationReportCard = dynamic(
  () =>
    import("@/components/manifest/validation-report-card").then((m) => ({
      default: m.ValidationReportCard,
    })),
  {
    ssr: false,
    loading: () => (
      <PanelSkeleton
        label="Validation report"
        columnWidths={["40%", "20%", "20%", "16%"]}
        rows={4}
      />
    ),
  },
);
const ArtifactsPanel = dynamic(
  () =>
    import("@/components/manifest/artifacts-panel").then((m) => ({
      default: m.ArtifactsPanel,
    })),
  {
    ssr: false,
    loading: () => (
      <PanelSkeleton
        label="Artifacts"
        columnWidths={["44%", "16%", "20%", "16%"]}
      />
    ),
  },
);

function PanelSkeleton({
  label,
  columnWidths,
  rows = 6,
}: {
  label: string;
  columnWidths: ReadonlyArray<string>;
  rows?: number;
}) {
  const slug = label.toLowerCase().replace(/\s+/g, "-");
  const headingId = `panel-skeleton-${slug}-heading`;
  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid={`panel-skeleton-${slug}`}
      style={{ border: "1px solid var(--color-border-card)" }}
      aria-labelledby={headingId}
    >
      <header
        className="flex items-center justify-between gap-3 px-4 py-2"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <h2 id={headingId} className="font-label">
          {label}
        </h2>
      </header>
      <TableSkeleton
        rows={rows}
        columnWidths={columnWidths}
        caption={`Loading ${label.toLowerCase()}`}
      />
    </section>
  );
}

// Cancel is meaningful only while the worker is alive; retry is the
// inverse — only a terminal failed/cancelled run can be re-launched. We
// branch on Run.status (live, polled) rather than RunManifest.status so a
// cancel that hasn't yet been mirrored into manifest.json still flips
// the toolbar correctly.
type RunActionStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

const CANCELLABLE: ReadonlySet<RunActionStatus> = new Set(["running", "queued"]);
const RETRYABLE: ReadonlySet<RunActionStatus> = new Set(["failed", "cancelled"]);

type Toast = { kind: "ok" | "err"; message: string };

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

// Cap matches use-project.ts so the run-detail tail and the workspace
// dock can't disagree on max retained lines after a long run.
const LOG_MAX = 2000;

type StreamStatus = "idle" | "live" | "ended" | "offline";

/** Subscribe to live SSE events and buffer the last LOG_MAX log lines. */
function useRunLogStream(
  projectId: string | null,
  runId: string,
  paused: boolean,
): { lines: LogLine[]; status: StreamStatus } {
  const [lines, setLines] = React.useState<LogLine[]>([]);
  const [status, setStatus] = React.useState<StreamStatus>("idle");
  // Mirror ``paused`` into a ref so the SSE callback closes over a
  // stable reference. Without this, toggling pause would tear down and
  // recreate the EventSource (losing any buffered backlog) just to read
  // a single boolean.
  const pausedRef = React.useRef(paused);
  React.useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  React.useEffect(() => {
    if (!projectId) return;
    setStatus("live");
    const unsubscribe = api.subscribeRunEvents(
      projectId,
      runId,
      (evt) => {
        if (evt.kind === "log.line") {
          if (pausedRef.current) return;
          setLines((prev) => {
            const next = [
              ...prev,
              {
                ts: String(evt.ts),
                source: String(evt.source ?? "run"),
                agent: evt.agent as string | undefined,
                level:
                  (evt.level as "info" | "warn" | "error" | "tool") ?? "info",
                text: String(evt.text ?? ""),
              } satisfies LogLine,
            ];
            return next.length > LOG_MAX ? next.slice(-LOG_MAX) : next;
          });
        } else if (evt.kind === "stage.finished") {
          setStatus("ended");
        }
      },
      () => {
        // The api wrapper retries with backoff internally; we surface
        // the disconnect so the panel header can show "reconnecting…"
        // until onopen fires again. Status flips back to "live" on the
        // next received event.
        setStatus("offline");
      },
    );
    return () => {
      unsubscribe();
    };
  }, [projectId, runId]);

  // Reset when the run id changes so a navigation across run detail
  // pages doesn't bleed lines from the previous run.
  React.useEffect(() => {
    setLines([]);
    setStatus("idle");
  }, [runId]);

  return { lines, status };
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

  // Bind this run id to the module-level store so every fetchJson
  // call from the run-detail subtree carries X-Plato-Run-Id for
  // backend log correlation. Cleared on unmount so navigating away
  // doesn't leave a stale id tagged on unrelated requests.
  React.useEffect(() => {
    setActiveRunId(runId);
    return () => setActiveRunId(null);
  }, [runId]);

  const router = useRouter();
  const [manifest, setManifest] =
    React.useState<Loadable<RunManifest>>({ kind: "loading" });
  const [evidence, setEvidence] =
    React.useState<Loadable<EvidenceMatrixData>>({ kind: "loading" });
  const [validation, setValidation] =
    React.useState<Loadable<ValidationReport>>({ kind: "loading" });
  const [logHeight, setLogHeight] = React.useState<0 | 30 | 60>(30);
  const [logPaused, setLogPaused] = React.useState(false);
  // Live Run record for status/stage. Manifest gives us project_id, but
  // status there only flips on flush — Run.status updates the moment the
  // worker process changes state, so use that to gate the toolbar.
  const [run, setRun] = React.useState<Run | null>(null);
  const [cancelOpen, setCancelOpen] = React.useState(false);
  const [retryOpen, setRetryOpen] = React.useState(false);
  const [toast, setToast] = React.useState<Toast | null>(null);
  const toastTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = React.useCallback((t: Toast) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(t);
    toastTimer.current = setTimeout(() => setToast(null), 2800);
  }, []);

  React.useEffect(
    () => () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    },
    [],
  );

  // The SSE subscription needs a project_id; the manifest endpoint
  // injects it from the run dir layout. Until that resolves we render
  // a placeholder. Memoised so the hook doesn't re-subscribe on every
  // unrelated state change.
  const projectId = React.useMemo<string | null>(() => {
    if (manifest.kind !== "ready") return null;
    const pid = manifest.data.project_id;
    return typeof pid === "string" && pid.length > 0 ? pid : null;
  }, [manifest]);

  const { lines: logLines, status: logStatus } = useRunLogStream(
    projectId,
    runId,
    logPaused,
  );

  // Poll the live Run while it's a candidate for cancel/retry. Once the
  // worker is in a terminal state and not retryable in flight, we stop
  // polling — the toolbar reads off the last snapshot.
  React.useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const r = await api.getRun(projectId, runId);
        if (cancelled) return;
        setRun(r);
        // Keep polling while the run could change state under us
        // (queued/running) so the toolbar swaps between Cancel and
        // Retry without a manual refresh.
        if (r.status === "queued" || r.status === "running") {
          timer = setTimeout(tick, 2000);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          // Run not in the in-memory map (dashboard restart). Fall back
          // to manifest-derived status; nothing to retry on a poll.
          return;
        }
        // Transient errors: back off but keep trying.
        timer = setTimeout(tick, 5000);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [projectId, runId]);

  // Resolve the action status. Run.status (live) wins; manifest is the
  // fallback when the worker has been reaped from the in-memory map.
  const actionStatus: RunActionStatus | null = React.useMemo(() => {
    if (run) return run.status;
    if (manifest.kind === "ready") {
      const s = manifest.data.status;
      if (s === "success") return "succeeded";
      if (s === "error") return "failed";
      if (s === "running") return "running";
    }
    return null;
  }, [run, manifest]);

  const stage: StageId | null = run?.stage ?? null;
  const canCancel = !!projectId && actionStatus !== null && CANCELLABLE.has(actionStatus);
  const canRetry = !!projectId && !!stage && actionStatus !== null && RETRYABLE.has(actionStatus);

  const handleCancel = React.useCallback(async () => {
    if (!projectId) return;
    try {
      await api.cancelRun(projectId, runId);
      showToast({ kind: "ok", message: "Cancellation requested" });
      // Re-pull Run so the toolbar swaps to Retry once the worker
      // finishes draining.
      try {
        const r = await api.getRun(projectId, runId);
        setRun(r);
      } catch {
        /* polling loop will recover */
      }
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `Cancel failed (HTTP ${err.status})`
          : err instanceof Error
            ? err.message
            : "Cancel failed";
      showToast({ kind: "err", message: msg });
    }
  }, [projectId, runId, showToast]);

  const handleRetry = React.useCallback(async () => {
    if (!projectId || !stage) return;
    try {
      const fresh = await api.retryRun(projectId, stage);
      showToast({ kind: "ok", message: `Started new run ${fresh.id.slice(0, 8)}…` });
      router.push(`/runs/${fresh.id}`);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `Retry failed (HTTP ${err.status})`
          : err instanceof Error
            ? err.message
            : "Retry failed";
      showToast({ kind: "err", message: msg });
    }
  }, [projectId, stage, router, showToast]);

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
          className="surface-linear-card flex items-start justify-between gap-3 px-4 py-3"
          style={{ border: "1px solid var(--color-border-card)" }}
        >
          <div className="flex flex-col gap-1 min-w-0">
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
            <p className="font-mono text-[12px] text-(--color-text-row-meta) truncate">
              {runId}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="ghost"
              size="sm"
              disabled={!canCancel}
              onClick={() => setCancelOpen(true)}
              data-testid="run-action-cancel"
              title={canCancel ? "Cancel this run" : "Run is not active"}
            >
              <Ban size={13} strokeWidth={1.75} />
              Cancel
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={!canRetry}
              onClick={() => setRetryOpen(true)}
              data-testid="run-action-retry"
              title={
                canRetry
                  ? `Restart the ${stage} stage`
                  : "Retry available after a run fails or is cancelled"
              }
            >
              <RotateCcw size={13} strokeWidth={1.75} />
              Retry
            </Button>
          </div>
        </header>

        <RunDetailNav runId={runId} />

        {/* Manifest */}
        <ManifestSection state={manifest} />

        {/* Per-node telemetry breakdown */}
        <NodeBreakdownSection state={manifest} />

        {/* Live logs */}
        <LiveLogsSection
          manifestState={manifest}
          projectId={projectId}
          lines={logLines}
          status={logStatus}
          height={logHeight}
          onChangeHeight={setLogHeight}
          paused={logPaused}
          onTogglePause={() => setLogPaused((p) => !p)}
        />

        {/* Validation report */}
        <ValidationSection state={validation} />

        {/* Evidence matrix */}
        <EvidenceSection state={evidence} />

        {/* Downloadable run artefacts */}
        <ArtifactsPanel projectId={projectId} runId={runId} />
      </div>

      <ConfirmDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title={stage ? `Cancel ${stage} run?` : "Cancel run?"}
        description="The subprocess will receive SIGTERM and shut down cleanly. Partial output already written to disk is preserved."
        confirmLabel="Cancel run"
        cancelLabel="Keep running"
        variant="danger"
        onConfirm={handleCancel}
      />

      <ConfirmDialog
        open={retryOpen}
        onOpenChange={setRetryOpen}
        title={stage ? `Restart ${stage} stage?` : "Restart stage?"}
        description="A new run is launched against the same stage. The current run's artefacts and manifest stay on disk."
        confirmLabel="Restart"
        cancelLabel="Back"
        variant="primary"
        onConfirm={handleRetry}
      />

      {toast ? (
        <div
          role="status"
          data-testid="run-action-toast"
          className={cn(
            "fixed bottom-6 left-1/2 -translate-x-1/2 rounded-[8px] border px-3 py-2 text-[12.5px] shadow-[var(--shadow-dialog)]",
            toast.kind === "ok"
              ? "border-(--color-status-emerald)/30 bg-(--color-status-emerald)/12 text-(--color-status-emerald)"
              : "border-(--color-status-red)/30 bg-(--color-status-red)/12 text-(--color-status-red)",
          )}
        >
          {toast.message}
        </div>
      ) : null}
    </div>
  );
}

function LiveLogsSection({
  manifestState,
  projectId,
  lines,
  status,
  height,
  onChangeHeight,
  paused,
  onTogglePause,
}: {
  manifestState: Loadable<RunManifest>;
  projectId: string | null;
  lines: LogLine[];
  status: StreamStatus;
  height: 0 | 30 | 60;
  onChangeHeight: (h: 0 | 30 | 60) => void;
  paused: boolean;
  onTogglePause: () => void;
}) {
  // We can't subscribe until the manifest tells us which project this
  // run belongs to. Surface the same loading / missing affordances the
  // other sections use so the page reads consistently.
  if (manifestState.kind === "loading") {
    return <PlaceholderCard label="Live logs" message="Waiting for manifest…" />;
  }
  if (manifestState.kind === "missing" || !projectId) {
    return (
      <PlaceholderCard
        label="Live logs"
        message="No manifest yet — live log stream becomes available once the run writes its manifest."
      />
    );
  }
  if (manifestState.kind === "error") {
    return (
      <PlaceholderCard
        label="Live logs"
        message={`Cannot stream logs: ${manifestState.message}`}
        tone="error"
      />
    );
  }

  const statusLabel =
    status === "offline"
      ? "reconnecting…"
      : status === "ended"
        ? "stream closed"
        : "live";
  const statusTone =
    status === "offline"
      ? "var(--color-status-amber)"
      : status === "ended"
        ? "var(--color-text-quaternary)"
        : "var(--color-status-emerald)";

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="live-logs"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center justify-between gap-3 px-4 py-2"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="font-label">Live logs</div>
        <div
          className="flex items-center gap-1.5 font-mono text-[11px]"
          style={{ color: statusTone }}
        >
          <span
            aria-hidden
            className="size-1.5 rounded-full"
            style={{ backgroundColor: statusTone }}
          />
          {statusLabel}
        </div>
      </header>
      <AgentLogStream
        lines={lines}
        height={height}
        onChangeHeight={onChangeHeight}
        paused={paused}
        onTogglePause={onTogglePause}
      />
    </section>
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

function NodeBreakdownSection({ state }: { state: Loadable<RunManifest> }) {
  // Render only when the manifest is loaded — otherwise the placeholder
  // is redundant with the ManifestSection one directly above.
  if (state.kind !== "ready") return null;
  return <NodeBreakdown manifest={state.data} />;
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
