"use client";

import * as React from "react";
import { ApprovalCard, type ApprovalState } from "./approval-card";
import type { Project, StageId } from "@/lib/types";

export interface ApprovalCheckpointsProps {
  project: Project;
  currentStage: StageId;
  onApprove: (stage: StageId) => void;
  onReject: (stage: StageId) => void;
  onRefine: (stage: StageId) => void;
  onPivot: (stage: StageId) => void;
}

type PersistedState = ApprovalState | "skipped";

const STORAGE_PREFIX = "plato:approvals";
const AUTO_SKIP_KEY = "plato:approvals:auto-skip";

function approvalKey(projectId: string, stage: StageId): string {
  return `${STORAGE_PREFIX}:${projectId}:${stage}`;
}

function readState(
  projectId: string,
  stage: StageId,
): PersistedState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(approvalKey(projectId, stage));
    if (!raw) return null;
    if (
      raw === "pending" ||
      raw === "approved" ||
      raw === "rejected" ||
      raw === "skipped"
    ) {
      return raw;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Returns the upstream stage that's blocking the given target stage,
 * or null if nothing is blocking.
 *
 * Gating rules (see CHECKPOINTS map):
 *   - idea must be approved before literature/method/results/paper/referee
 *   - literature must be approved before method/results/paper/referee
 *   - method must be approved before results/paper/referee
 *
 * Auto-skip (`plato:approvals:auto-skip = "1"`) bypasses all gates.
 */
export function getBlockingApproval(
  project: Project,
  targetStage: StageId,
): StageId | null {
  if (typeof window === "undefined") return null;
  if (window.localStorage.getItem(AUTO_SKIP_KEY) === "1") return null;

  // Stages that GUARD a downstream run.
  const guardOrder: { gate: StageId; blocks: StageId[] }[] = [
    { gate: "idea", blocks: ["literature", "method", "results", "paper", "referee"] },
    { gate: "literature", blocks: ["method", "results", "paper", "referee"] },
    { gate: "method", blocks: ["results", "paper", "referee"] },
  ];

  for (const { gate, blocks } of guardOrder) {
    if (!blocks.includes(targetStage)) continue;
    const gateStage = project.stages[gate];
    if (!gateStage || gateStage.status !== "done") continue; // gate hasn't run yet — different problem
    const state = readState(project.id, gate);
    if (state === "approved" || state === "skipped") continue;
    return gate;
  }
  return null;
}

/** React hook returning {blockedBy, isBlocked} for a given stage. */
export function useApprovalGate(
  project: Project,
  stage: StageId,
): { blockedBy: StageId | null; isBlocked: boolean } {
  const [blockedBy, setBlockedBy] = React.useState<StageId | null>(null);

  React.useEffect(() => {
    const compute = () => setBlockedBy(getBlockingApproval(project, stage));
    compute();
    // Re-evaluate when localStorage changes (e.g., user approves elsewhere).
    const onStorage = (e: StorageEvent) => {
      if (e.key && (e.key.startsWith(STORAGE_PREFIX) || e.key === AUTO_SKIP_KEY)) {
        compute();
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [project, stage]);

  return { blockedBy, isBlocked: blockedBy !== null };
}

function writeState(
  projectId: string,
  stage: StageId,
  next: PersistedState,
) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(approvalKey(projectId, stage), next);
  } catch {
    // ignore quota / privacy-mode failures
  }
}

const CHECKPOINTS: Record<
  string,
  { stage: StageId; nextStage: StageId; title: string; description: string; warning?: string; nextLabel?: string }
> = {
  idea: {
    stage: "idea",
    nextStage: "literature",
    title: "Approve idea",
    description:
      "Review the generated research idea before generating literature review and methodology.",
  },
  literature: {
    stage: "literature",
    nextStage: "method",
    title: "Approve novelty verdict",
    description:
      "If the idea is 'not novel', consider pivoting to a different angle before continuing.",
  },
  method: {
    stage: "method",
    nextStage: "results",
    title: "Approve methodology",
    description:
      "Last cheap gate before the multi-hour Results run. Review the planned experiment carefully.",
    warning:
      "The Results stage executes generated Python code via cmbagent and can take 1-3 hours.",
    nextLabel: "Results experiment",
  },
};

export function ApprovalCheckpoints({
  project,
  currentStage,
  onApprove,
  onReject,
  onRefine,
  onPivot,
}: ApprovalCheckpointsProps) {
  const checkpoint = CHECKPOINTS[currentStage];
  const [persisted, setPersisted] = React.useState<PersistedState | null>(
    null,
  );
  const [hydrated, setHydrated] = React.useState(false);

  // Hydrate from localStorage after mount to avoid SSR mismatch.
  React.useEffect(() => {
    if (!checkpoint) {
      setHydrated(true);
      return;
    }
    setPersisted(readState(project.id, checkpoint.stage));
    setHydrated(true);
  }, [project.id, checkpoint]);

  if (!checkpoint || !hydrated) return null;

  const stage = project.stages[checkpoint.stage];
  const nextStage = project.stages[checkpoint.nextStage];

  // Don't show anything until the upstream stage is done.
  if (!stage || stage.status !== "done") return null;

  // Auto-skip rules.
  const autoSkipGlobal =
    typeof window !== "undefined" &&
    window.localStorage.getItem(AUTO_SKIP_KEY) === "1";
  const downstreamStarted = nextStage && nextStage.status !== "empty";

  if ((autoSkipGlobal || downstreamStarted) && persisted === null) {
    // Persist a 'skipped' marker so we don't re-evaluate every render.
    writeState(project.id, checkpoint.stage, "skipped");
    return null;
  }

  if (persisted === "skipped") return null;

  // Default un-set state is treated as 'pending'.
  const visualState: ApprovalState =
    persisted === "approved" || persisted === "rejected"
      ? persisted
      : "pending";

  const handle = (next: ApprovalState, cb: (s: StageId) => void) => () => {
    writeState(project.id, checkpoint.stage, next);
    setPersisted(next);
    cb(checkpoint.stage);
  };

  return (
    <ApprovalCard
      title={checkpoint.title}
      description={checkpoint.description}
      state={visualState}
      warning={checkpoint.warning}
      nextStage={checkpoint.nextLabel}
      onApprove={handle("approved", onApprove)}
      onReject={handle("rejected", onReject)}
      onRefine={() => onRefine(checkpoint.stage)}
      onPivot={() => onPivot(checkpoint.stage)}
    />
  );
}
