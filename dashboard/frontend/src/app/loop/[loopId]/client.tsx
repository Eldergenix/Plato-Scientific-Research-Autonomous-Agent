"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Repeat } from "lucide-react";
import { LoopTsvViewer } from "@/components/loop/loop-tsv-viewer";

export default function LoopDetailClient() {
  const params = useParams<{ loopId: string }>();
  const loopId = params?.loopId ?? "";

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="hairline-b flex h-11 flex-none items-center gap-2 px-4">
        <Link
          href="/loop"
          className="inline-flex items-center gap-1.5 h-7 px-2 rounded-[6px] text-[12px] text-(--color-text-tertiary-spec) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary) transition-colors"
        >
          <ArrowLeft size={12} strokeWidth={1.75} />
          Back to loops
        </Link>
        <span className="text-[12px] text-(--color-text-quaternary-spec)">/</span>
        <h1 className="flex items-center gap-2 text-[14px] font-medium text-(--color-text-primary)">
          <Repeat size={13} strokeWidth={1.75} className="text-(--color-brand-hover)" />
          <span className="font-mono text-[13px] text-(--color-text-row-meta)" data-testid="loop-detail-id">
            {loopId}
          </span>
        </h1>
      </div>

      <div className="flex flex-1 min-h-0 flex-col overflow-y-auto p-4">
        <LoopTsvViewer loopId={loopId} />
      </div>
    </div>
  );
}
