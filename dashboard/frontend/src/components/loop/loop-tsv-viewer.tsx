"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { Activity, AlertCircle, CheckCircle2, OctagonX, StopCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";
import {
  loopApi,
  type LoopStatus,
  type LoopStatusValue,
  type LoopTsvRow,
} from "./loop-api";

// Defer the iteration table until rows are fetched — keeps it out of the
// initial page chunk for the empty-loop case.
const LoopHistory = dynamic(
  () => import("./loop-history").then((m) => ({ default: m.LoopHistory })),
  { ssr: false },
);

// Stop dialog pulls in @radix-ui/react-dialog. Mount only when the user
// actually opens it so first paint stays light.
const ConfirmDialog = dynamic(
  () => import("@/components/ui/confirm-dialog").then((m) => ({ default: m.ConfirmDialog })),
  { ssr: false },
);

export interface LoopTsvViewerProps {
  loopId: string;
  initialStatus?: LoopStatus | null;
  initialRows?: LoopTsvRow[];
}

const POLL_MS = 5_000;

function statusTone(status: LoopStatusValue) {
  switch (status) {
    case "running":
      return "indigo" as const;
    case "stopped":
      return "neutral" as const;
    case "interrupted":
      return "amber" as const;
    case "error":
      return "red" as const;
    default:
      return "neutral" as const;
  }
}

function StatusIcon({ status }: { status: LoopStatusValue }) {
  const props = { size: 13, strokeWidth: 1.75 } as const;
  switch (status) {
    case "running":
      return <Activity {...props} className="text-(--color-brand-hover)" />;
    case "stopped":
      return <CheckCircle2 {...props} className="text-(--color-text-tertiary-spec)" />;
    case "interrupted":
      return <OctagonX {...props} className="text-(--color-status-amber)" />;
    case "error":
      return <AlertCircle {...props} className="text-(--color-status-red)" />;
    default:
      return null;
  }
}

function CounterCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "emerald";
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] font-medium uppercase tracking-wider text-(--color-text-tertiary-spec)">
        {label}
      </span>
      <span
        className={cn(
          "font-mono text-[15px] font-medium tabular-nums",
          tone === "emerald"
            ? "text-(--color-status-emerald)"
            : "text-(--color-text-primary)",
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function LoopTsvViewer({
  loopId,
  initialStatus = null,
  initialRows = [],
}: LoopTsvViewerProps) {
  const [status, setStatus] = React.useState<LoopStatus | null>(initialStatus);
  const [rows, setRows] = React.useState<LoopTsvRow[]>(initialRows);
  const [error, setError] = React.useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [stopping, setStopping] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      const [s, t] = await Promise.all([
        loopApi.status(loopId),
        loopApi.tsv(loopId),
      ]);
      setStatus(s);
      setRows(t.rows);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh loop");
    }
  }, [loopId]);

  // Initial fetch + polling while running.
  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  React.useEffect(() => {
    if (status?.status !== "running") return;
    const handle = setInterval(() => {
      void refresh();
    }, POLL_MS);
    return () => clearInterval(handle);
  }, [status?.status, refresh]);

  const handleStop = async () => {
    setStopping(true);
    try {
      const next = await loopApi.stop(loopId);
      setStatus(next);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to stop loop");
    } finally {
      setStopping(false);
    }
  };

  if (!status) {
    return (
      <div className="flex items-center justify-center py-10 text-[13px] text-(--color-text-tertiary-spec)">
        {error ?? "Loading loop status…"}
      </div>
    );
  }

  const bestComposite = Number.isFinite(status.best_composite)
    ? status.best_composite.toFixed(4)
    : "—";

  return (
    <div className="flex flex-col gap-4" data-testid="loop-tsv-viewer">
      {/* Status header */}
      <div className="surface-linear-card flex items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-3">
          <Pill tone={statusTone(status.status)} className="text-[11px]">
            <StatusIcon status={status.status} />
            <span data-testid="loop-status-pill">{status.status}</span>
          </Pill>
          <CounterCell
            label="Iterations"
            value={
              <span data-testid="loop-iterations">{status.iterations}</span>
            }
          />
          <CounterCell
            label="Kept"
            value={<span data-testid="loop-kept">{status.kept}</span>}
            tone="emerald"
          />
          <CounterCell
            label="Discarded"
            value={
              <span data-testid="loop-discarded">{status.discarded}</span>
            }
          />
          <CounterCell label="Best composite" value={bestComposite} />
        </div>
        <Button
          variant="danger"
          size="sm"
          disabled={status.status !== "running" || stopping}
          onClick={() => setConfirmOpen(true)}
          data-testid="loop-stop-button"
        >
          <StopCircle size={12} strokeWidth={1.75} />
          {stopping ? "Stopping…" : "Stop"}
        </Button>
      </div>

      {error ? (
        <div className="rounded-[6px] border border-(--color-status-red)/30 bg-(--color-status-red)/10 px-2.5 py-1.5 text-[12px] text-(--color-status-red)">
          {error}
        </div>
      ) : null}

      {status.error ? (
        <div className="rounded-[6px] border border-(--color-status-red)/30 bg-(--color-status-red)/10 px-2.5 py-1.5 text-[12px] text-(--color-status-red)">
          Loop error: {status.error}
        </div>
      ) : null}

      <LoopHistory rows={rows} />

      {confirmOpen ? (
        <ConfirmDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Stop autonomous loop?"
          description="The current iteration will be cancelled and any uncommitted git state from this iteration discarded. Loops cannot be resumed."
          confirmLabel="Stop loop"
          cancelLabel="Keep running"
          variant="danger"
          onConfirm={handleStop}
        />
      ) : null}
    </div>
  );
}
