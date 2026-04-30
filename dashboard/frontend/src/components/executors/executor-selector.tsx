"use client";

import * as React from "react";
import * as Select from "@radix-ui/react-select";
import { AlertTriangle, Check, CheckCircle2, ChevronDown } from "lucide-react";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

export type ExecutorKind = "real" | "stub" | "lazy";

export interface ExecutorInfo {
  name: string;
  available: boolean;
  kind: ExecutorKind;
  description: string;
}

export interface ExecutorSelectorProps {
  value: string;
  onChange: (name: string) => void;
  executors: ExecutorInfo[];
  disabled?: boolean;
}

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

function AvailabilityIcon({ available }: { available: boolean }) {
  if (available) {
    return (
      <CheckCircle2
        size={12}
        strokeWidth={1.75}
        className="text-(--color-status-emerald)"
        aria-label="available"
      />
    );
  }
  return (
    <AlertTriangle
      size={12}
      strokeWidth={1.75}
      className="text-(--color-status-amber)"
      aria-label="unavailable"
    />
  );
}

export function ExecutorSelector({
  value,
  onChange,
  executors,
  disabled,
}: ExecutorSelectorProps) {
  const current = executors.find((e) => e.name === value);

  return (
    <Select.Root
      value={value}
      onValueChange={onChange}
      disabled={disabled}
    >
      <Select.Trigger
        data-testid="executor-selector-trigger"
        aria-label="Select executor"
        className={cn(
          "inline-flex w-full items-center justify-between gap-2 rounded-[6px] border border-(--color-border-card) bg-(--color-bg-card) px-3",
          "h-9 text-[13px] font-medium text-(--color-text-primary)",
          "hover:border-(--color-border-strong) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
          "disabled:opacity-50 disabled:cursor-not-allowed",
        )}
      >
        <Select.Value asChild>
          {current ? (
            <span className="flex min-w-0 items-center gap-2">
              <AvailabilityIcon available={current.available} />
              <span className="truncate font-mono text-[13px]">
                {current.name}
              </span>
              <Pill tone={KIND_TONE[current.kind]} className="ml-1">
                {KIND_LABEL[current.kind]}
              </Pill>
            </span>
          ) : (
            <span className="text-(--color-text-tertiary)">Select executor…</span>
          )}
        </Select.Value>
        <Select.Icon>
          <ChevronDown
            size={13}
            strokeWidth={1.75}
            className="text-(--color-text-tertiary)"
          />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={4}
          className={cn(
            "z-[60] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-[8px]",
            "border border-(--color-border-card) bg-(--color-bg-card) shadow-[var(--shadow-dialog)]",
          )}
        >
          <Select.Viewport className="p-1">
            {executors.map((exec) => {
              // Stubs are non-actionable; the user can still see the entry
              // (hence not filtered out) but can't pick it from the menu.
              const isStubDisabled = exec.kind === "stub";
              return (
                <Select.Item
                  key={exec.name}
                  value={exec.name}
                  disabled={isStubDisabled}
                  data-testid={`executor-option-${exec.name}`}
                  className={cn(
                    "relative flex h-9 cursor-pointer items-center gap-2 rounded-[5px] pl-7 pr-2",
                    "text-[13px] text-(--color-text-secondary-spec)",
                    "data-[highlighted]:bg-(--color-ghost-bg-hover) data-[highlighted]:text-(--color-text-primary)",
                    "data-[highlighted]:outline-none",
                    "data-[disabled]:cursor-not-allowed data-[disabled]:opacity-60",
                  )}
                >
                  <Select.ItemIndicator className="absolute left-1.5 inline-flex items-center">
                    <Check
                      size={12}
                      strokeWidth={2}
                      className="text-(--color-brand-hover)"
                    />
                  </Select.ItemIndicator>
                  <AvailabilityIcon available={exec.available} />
                  <Select.ItemText asChild>
                    <span className="font-mono text-[13px]">{exec.name}</span>
                  </Select.ItemText>
                  <Pill tone={KIND_TONE[exec.kind]} className="ml-auto">
                    {KIND_LABEL[exec.kind]}
                  </Pill>
                </Select.Item>
              );
            })}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
