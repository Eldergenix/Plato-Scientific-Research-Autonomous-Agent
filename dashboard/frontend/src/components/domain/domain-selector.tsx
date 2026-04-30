"use client";

import * as React from "react";
import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface DomainProfileLite {
  name: string;
  retrieval_sources: string[];
  executor: string;
}

export interface DomainSelectorProps {
  value: string | null;
  onChange: (name: string) => void;
  domains: DomainProfileLite[];
  disabled?: boolean;
  ariaLabel?: string;
}

/**
 * Radix Select wrapper for picking the active DomainProfile. Mirrors the
 * Journal picker in `create-project-modal.tsx` so the visual language stays
 * consistent across the dashboard.
 */
export function DomainSelector({
  value,
  onChange,
  domains,
  disabled,
  ariaLabel = "Domain profile",
}: DomainSelectorProps) {
  const active = React.useMemo(
    () => domains.find((d) => d.name === value) ?? null,
    [domains, value],
  );

  return (
    <Select.Root
      value={value ?? undefined}
      onValueChange={(v) => onChange(v)}
      disabled={disabled || domains.length === 0}
    >
      <Select.Trigger
        className={cn(
          "inline-flex w-full items-center justify-between gap-2 rounded-[6px] border border-(--color-border-card) bg-(--color-bg-card) px-2.5",
          "h-8 text-[13px] font-medium text-(--color-text-primary)",
          "hover:border-(--color-border-strong) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
          "disabled:opacity-50",
        )}
        aria-label={ariaLabel}
        data-testid="domain-selector-trigger"
      >
        <Select.Value placeholder="Select a domain…">
          {active ? (
            <span className="truncate">{active.name}</span>
          ) : (
            <span className="text-(--color-text-tertiary)">Select a domain…</span>
          )}
        </Select.Value>
        <Select.Icon>
          <ChevronDown
            size={12}
            strokeWidth={1.75}
            className="text-(--color-text-tertiary-spec)"
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
            {domains.map((d) => {
              const isSelected = d.name === value;
              return (
                <Select.Item
                  key={d.name}
                  value={d.name}
                  data-testid={`domain-option-${d.name}`}
                  className={cn(
                    "relative flex cursor-pointer items-start gap-2 rounded-[4px] py-1.5 pl-6 pr-2",
                    "text-[13px] text-(--color-text-secondary-spec)",
                    "data-[highlighted]:bg-(--color-ghost-bg-hover) data-[highlighted]:text-(--color-text-primary)",
                    "data-[highlighted]:outline-none",
                  )}
                >
                  <Select.ItemIndicator className="absolute left-1.5 top-2 inline-flex items-center">
                    <Check
                      size={12}
                      strokeWidth={2}
                      className="text-(--color-brand-hover)"
                    />
                  </Select.ItemIndicator>
                  <div className="flex flex-1 flex-col gap-0.5">
                    <Select.ItemText>
                      <span
                        className={cn(
                          "text-[13px]",
                          isSelected
                            ? "text-(--color-text-primary)"
                            : "text-(--color-text-primary)",
                        )}
                      >
                        {d.name}
                      </span>
                    </Select.ItemText>
                    <span className="text-[11px] text-(--color-text-tertiary)">
                      {d.retrieval_sources.length}{" "}
                      {d.retrieval_sources.length === 1 ? "source" : "sources"}{" "}
                      &middot; executor{" "}
                      <code className="font-mono text-[10.5px]">{d.executor}</code>
                    </span>
                  </div>
                </Select.Item>
              );
            })}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
