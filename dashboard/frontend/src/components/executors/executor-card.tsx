"use client";

import * as React from "react";
import { AlertTriangle, CheckCircle2, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import type { ExecutorInfo, ExecutorKind } from "./executor-selector";

const KIND_TONE: Record<ExecutorKind, "green" | "amber" | "red"> = {
  real: "green",
  lazy: "amber",
  stub: "red",
};

const KIND_LABEL: Record<ExecutorKind, string> = {
  real: "real",
  lazy: "lazy",
  stub: "stub",
};

const STUB_NAMES = new Set(["modal", "e2b"]);

export interface ExecutorCardProps {
  executor: ExecutorInfo;
  isDefault: boolean;
  onSetDefault: () => void;
  pending?: boolean;
}

export function ExecutorCard({
  executor,
  isDefault,
  onSetDefault,
  pending,
}: ExecutorCardProps) {
  const isStub = executor.kind === "stub" || STUB_NAMES.has(executor.name);

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="executor-card"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Cpu size={14} className="text-(--color-text-tertiary)" />
          <h3
            className="font-mono text-[14px] text-(--color-text-primary-strong) truncate"
            style={{ fontWeight: 510 }}
          >
            {executor.name}
          </h3>
          <Pill tone={KIND_TONE[executor.kind]}>{KIND_LABEL[executor.kind]}</Pill>
          {isDefault ? <Pill tone="indigo">default</Pill> : null}
        </div>
        <AvailabilityBadge available={executor.available} />
      </header>

      <div className="px-4 py-3">
        <p className="text-[13px] leading-[1.55] text-(--color-text-secondary-spec)">
          {executor.description}
        </p>
      </div>

      {isStub ? (
        <div
          className="mx-4 mb-3 flex items-start gap-2 rounded-[6px] border px-3 py-2 text-[12px]"
          style={{
            borderColor: "var(--color-status-amber)",
            backgroundColor: "color-mix(in oklab, var(--color-status-amber) 12%, transparent)",
            color: "var(--color-status-amber)",
          }}
          data-testid="executor-stub-warning"
        >
          <AlertTriangle size={13} strokeWidth={1.75} className="mt-px shrink-0" />
          <span>
            Modal/E2B require their respective SDKs to be installed and
            configured. The current backend is a stub and will raise on run.
          </span>
        </div>
      ) : null}

      <footer
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderTop: "1px solid var(--color-border-standard)" }}
      >
        <span className="text-[12px] text-(--color-text-tertiary)">
          {executor.available
            ? "Ready to run"
            : "Install dependencies before selecting."}
        </span>
        <Button
          variant={isDefault ? "ghost" : "primary"}
          size="sm"
          disabled={isDefault || pending || isStub}
          onClick={onSetDefault}
          data-testid="executor-set-default"
        >
          {isDefault ? "Default" : pending ? "Saving…" : "Set as default"}
        </Button>
      </footer>
    </section>
  );
}

function AvailabilityBadge({ available }: { available: boolean }) {
  if (available) {
    return (
      <span className="inline-flex items-center gap-1 text-[12px] text-(--color-status-emerald)">
        <CheckCircle2 size={13} strokeWidth={1.75} />
        available
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[12px] text-(--color-status-amber)">
      <AlertTriangle size={13} strokeWidth={1.75} />
      unavailable
    </span>
  );
}
