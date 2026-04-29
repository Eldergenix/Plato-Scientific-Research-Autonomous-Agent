"use client";

import * as React from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { StatusDot } from "@/components/ui/status-dot";
import type { Stage, StageId } from "@/lib/types";

const ORDER: StageId[] = [
  "data",
  "idea",
  "literature",
  "method",
  "results",
  "paper",
  "referee",
];

export function StageStrip({
  stages,
  activeStage,
  onSelect,
}: {
  stages: Record<StageId, Stage>;
  activeStage: StageId;
  onSelect: (s: StageId) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Research pipeline stages"
      className="h-10 hairline-b flex items-center px-3 gap-1 bg-(--color-bg-marketing) sticky top-12 z-20 overflow-x-auto"
    >
      {ORDER.map((id, idx) => {
        const stage = stages[id];
        const active = id === activeStage;
        return (
          <React.Fragment key={id}>
            <button
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onSelect(id)}
              className={cn(
                "h-7 flex items-center gap-1.5 px-2 rounded-[6px] text-[12px] transition-colors whitespace-nowrap",
                active
                  ? "bg-(--color-ghost-bg-hover) text-(--color-text-primary)"
                  : "text-(--color-text-tertiary) hover:text-(--color-text-primary) hover:bg-(--color-ghost-bg)",
              )}
            >
              <StatusDot status={stage.status} size={6} />
              <span className="capitalize font-medium">{stage.label}</span>
              {stage.progressLabel && (
                <span className="text-(--color-text-quaternary) font-mono ml-0.5">
                  {stage.progressLabel}
                </span>
              )}
            </button>
            {idx < ORDER.length - 1 && (
              <ChevronRight
                size={12}
                strokeWidth={1.5}
                className="text-(--color-text-quaternary) shrink-0"
                aria-hidden
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
