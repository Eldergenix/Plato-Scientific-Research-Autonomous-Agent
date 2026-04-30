"use client";

import { Repeat } from "lucide-react";
import { LoopControl } from "@/components/loop/loop-control";

export default function LoopIndexPage() {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="hairline-b flex h-11 flex-none items-center justify-between gap-2 px-4">
        <h1 className="flex items-center gap-2 text-[15px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
          <Repeat size={14} strokeWidth={1.75} className="text-(--color-brand-hover)" />
          Autonomous loops
        </h1>
      </div>

      <div className="flex flex-1 min-h-0 flex-col overflow-y-auto p-4">
        <p className="mb-4 max-w-[640px] text-[13px] text-(--color-text-tertiary-spec)">
          Run Plato unattended under a time, iteration, and cost budget. Each
          iteration scores the project against citation validity, unsupported
          claims, referee severity, and lines-of-code drift. Improvements are
          committed to a tracking branch; regressions are reverted.
        </p>
        <LoopControl />
      </div>
    </div>
  );
}
