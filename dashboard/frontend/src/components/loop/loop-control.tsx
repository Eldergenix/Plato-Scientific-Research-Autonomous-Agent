"use client";

import * as React from "react";
import Link from "next/link";
import * as Dialog from "@radix-ui/react-dialog";
import { ChevronRight, PlayCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";
import { LoopSettingsForm } from "./loop-settings-form";
import { loopApi, type LoopStatus, type LoopStatusValue } from "./loop-api";

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

function LoopRow({ loop }: { loop: LoopStatus }) {
  return (
    <Link
      href={`/loop/${loop.loop_id}`}
      data-testid="loop-row"
      data-loop-id={loop.loop_id}
      className={cn(
        "group flex items-center gap-3 px-3 py-2.5 transition-colors",
        "border-b border-(--color-border-standard) last:border-b-0",
        "hover:bg-[rgba(255,255,255,0.02)]",
      )}
    >
      <span
        className="font-mono text-[12px] text-(--color-text-row-meta) tabular-nums"
        title={loop.loop_id}
      >
        {loop.loop_id}
      </span>
      <Pill tone={statusTone(loop.status)} className="text-[11px]">
        {loop.status}
      </Pill>
      <span className="font-mono text-[12px] text-(--color-text-tertiary-spec) tabular-nums">
        {loop.iterations} iter · kept {loop.kept} · discarded {loop.discarded}
      </span>
      <span className="ml-auto inline-flex items-center gap-1 text-[12px] font-medium text-(--color-text-tertiary-spec) group-hover:text-(--color-text-primary)">
        View
        <ChevronRight size={12} strokeWidth={1.75} />
      </span>
    </Link>
  );
}

export function LoopControl() {
  const [loops, setLoops] = React.useState<LoopStatus[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      const list = await loopApi.list();
      setLoops(list);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load loops");
      setLoops((prev) => prev ?? []);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
    const handle = setInterval(() => {
      void refresh();
    }, POLL_MS);
    return () => clearInterval(handle);
  }, [refresh]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[14px] font-medium text-(--color-text-primary)">
          Active loops
        </h2>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setDialogOpen(true)}
          data-testid="loop-start-button"
        >
          <PlayCircle size={12} strokeWidth={1.75} />
          Start autonomous loop
        </Button>
      </div>

      {error ? (
        <div className="rounded-[6px] border border-(--color-status-red)/30 bg-(--color-status-red)/10 px-2.5 py-1.5 text-[12px] text-(--color-status-red)">
          {error}
        </div>
      ) : null}

      {loops == null ? (
        <div className="flex items-center justify-center rounded-[8px] border border-dashed border-[#262628] py-10 text-[12px] text-(--color-text-tertiary-spec)">
          Loading loops…
        </div>
      ) : loops.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center rounded-[8px] border border-dashed border-[#262628] py-10 text-center"
          data-testid="loop-empty"
        >
          <p className="text-[13px] font-medium text-(--color-text-primary)">
            No autonomous loops yet
          </p>
          <p className="mt-1 max-w-[320px] text-[12px] text-(--color-text-tertiary-spec)">
            Start a loop to run Plato iteratively under a time, iteration, and
            cost budget. Each accepted iteration is committed to a tracking
            branch.
          </p>
        </div>
      ) : (
        <div className="surface-linear-card overflow-hidden">
          {loops.map((loop) => (
            <LoopRow key={loop.loop_id} loop={loop} />
          ))}
        </div>
      )}

      <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=open]:fade-in-0"
          />
          <Dialog.Content
            className={cn(
              "fixed left-1/2 top-1/2 z-50 w-[560px] -translate-x-1/2 -translate-y-1/2",
              "surface-linear-card overflow-hidden",
              "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
            )}
            data-testid="loop-start-dialog"
          >
            <div className="flex h-11 items-center justify-between gap-2 border-b border-[#1D1D1F] px-4">
              <Dialog.Title className="flex items-center gap-2 text-[15px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
                <PlayCircle size={14} strokeWidth={1.75} className="text-(--color-brand-hover)" />
                Start autonomous loop
              </Dialog.Title>
              <Dialog.Close
                aria-label="Close"
                className={cn(
                  "inline-flex size-7 items-center justify-center rounded-full text-(--color-text-tertiary-spec)",
                  "transition-colors hover:bg-white/5 hover:text-(--color-text-primary)",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
                )}
              >
                <X size={14} strokeWidth={1.75} />
              </Dialog.Close>
            </div>
            <Dialog.Description className="sr-only">
              Configure budgets and project directory, then start the autonomous loop.
            </Dialog.Description>
            <LoopSettingsForm
              onStarted={() => {
                setDialogOpen(false);
                void refresh();
              }}
            />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
