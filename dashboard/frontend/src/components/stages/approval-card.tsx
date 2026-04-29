"use client";

import * as React from "react";
import {
  Sparkles,
  AlertTriangle,
  Check,
  X,
  RefreshCw,
  ArrowLeft,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";

export type ApprovalState = "pending" | "approved" | "rejected";

export interface ApprovalCardProps {
  /** What to show in the card title, e.g. "Approve idea" */
  title: string;
  /** Description of what the user is approving and what comes next */
  description: string;
  /** Active state: 'pending' | 'approved' | 'rejected' */
  state?: ApprovalState;
  /** Who/when approved (only when state === 'approved') */
  approvedAt?: string;
  approvedBy?: string;
  /** Action labels (defaults below) */
  approveLabel?: string;
  rejectLabel?: string;
  refineLabel?: string;
  /** Action callbacks */
  onApprove?: () => void;
  onReject?: () => void;
  onRefine?: () => void;
  onPivot?: () => void;
  /** Optional next-stage hint */
  nextStage?: string;
  /** When set, displays a contextual warning (e.g. "Runs cost ~$3 of LLM credits") */
  warning?: string;
}

export function ApprovalCard({
  title,
  description,
  state = "pending",
  approvedAt,
  approvedBy,
  approveLabel = "Approve",
  rejectLabel = "Reject",
  refineLabel = "Refine",
  onApprove,
  onReject,
  onRefine,
  onPivot,
  nextStage,
  warning,
}: ApprovalCardProps) {
  if (state === "approved") {
    return (
      <div
        className={cn(
          "flex items-center justify-between hairline-b px-4",
          "h-7 transition-[height,opacity] duration-200",
        )}
      >
        <div className="flex items-center gap-2 text-[12px] text-(--color-text-row-meta)">
          <Check
            size={12}
            strokeWidth={2}
            className="text-(--color-status-emerald)"
          />
          <span>
            Approved
            {approvedBy ? <> &middot; {approvedBy}</> : null}
            {approvedAt ? (
              <> &middot; {formatRelativeTime(approvedAt)}</>
            ) : null}
          </span>
        </div>
        <button
          type="button"
          onClick={onReject}
          className="text-[12px] text-(--color-text-row-meta) hover:text-(--color-text-primary) transition-colors"
        >
          Undo
        </button>
      </div>
    );
  }

  if (state === "rejected") {
    return (
      <div
        className={cn(
          "flex items-center justify-between hairline-b px-4",
          "h-7 transition-[height,opacity] duration-200",
        )}
      >
        <div className="flex items-center gap-2 text-[12px] text-(--color-text-row-meta)">
          <X
            size={12}
            strokeWidth={2}
            className="text-(--color-status-red)"
          />
          <span>Rejected</span>
        </div>
        <button
          type="button"
          onClick={onRefine}
          className="text-[12px] text-(--color-status-red) hover:opacity-80 transition-opacity"
        >
          click to revise
        </button>
      </div>
    );
  }

  // Pending state
  return (
    <div
      className={cn(
        "relative surface-linear-card overflow-hidden",
        "transition-[height,opacity] duration-200",
      )}
      style={{ minHeight: "64px" }}
    >
      {/* Indigo glow strip on the left edge */}
      <div
        aria-hidden
        className="absolute left-0 top-0 bottom-0 w-[3px]"
        style={{
          background:
            "linear-gradient(180deg, rgba(94,106,210,0.2) 0%, var(--color-brand-indigo) 50%, rgba(94,106,210,0.2) 100%)",
          boxShadow: "0 0 12px -2px rgba(94,106,210,0.6)",
        }}
      />

      <div
        className="flex items-center justify-between gap-4"
        style={{ padding: "12px 16px" }}
      >
        <div className="flex items-start gap-2.5 min-w-0">
          <Sparkles
            size={14}
            strokeWidth={1.5}
            className="text-(--color-brand-hover) shrink-0 mt-0.5"
          />
          <div className="min-w-0">
            <div
              className="text-white truncate"
              style={{ fontSize: "15px", fontWeight: 510 }}
            >
              {title}
            </div>
            <div
              className="text-[#d0d6e0] mt-0.5"
              style={{ fontSize: "13px", fontWeight: 450 }}
            >
              {description}
              {nextStage ? (
                <span className="ml-1.5 text-(--color-text-tertiary) font-mono text-[12px]">
                  &rarr; next: {nextStage}
                </span>
              ) : null}
            </div>
            {warning ? (
              <div
                className="flex items-center gap-1.5 mt-1.5"
                style={{ color: "#F0BF00" }}
              >
                <AlertTriangle size={12} strokeWidth={1.5} />
                <span style={{ fontSize: "12px", fontWeight: 450 }}>
                  {warning}
                </span>
              </div>
            ) : null}
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={onRefine}
            type="button"
          >
            <RefreshCw size={12} strokeWidth={1.5} />
            {refineLabel}
          </Button>
          <Button variant="ghost" size="sm" onClick={onPivot} type="button">
            <ArrowLeft size={12} strokeWidth={1.5} />
            Pivot
          </Button>
          <Button variant="danger" size="sm" onClick={onReject} type="button">
            <X size={12} strokeWidth={1.5} />
            {rejectLabel}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={onApprove}
            type="button"
          >
            <Check size={12} strokeWidth={2} />
            {approveLabel}
            <ArrowRight size={12} strokeWidth={1.5} />
          </Button>
        </div>
      </div>
    </div>
  );
}
