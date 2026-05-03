"use client";

import * as React from "react";
import { ApprovalCard, type ApprovalState } from "./approval-card";
import { api, type ApprovalsState } from "@/lib/api";
import type { Project, StageId } from "@/lib/types";

export interface ApprovalCheckpointsProps {
  project: Project;
  currentStage: StageId;
  onApprove: (stage: StageId) => void;
  onReject: (stage: StageId) => void;
  onRefine: (stage: StageId) => void;
  onPivot: (stage: StageId) => void;
  /**
   * Iter-27: parent's project-refresh hook. After a successful PUT
   * /approvals we trigger this so ``project.approvals`` repopulates
   * downstream gate evaluations.
   */
  onApprovalsChanged?: () => void | Promise<void>;
}

type PersistedState = ApprovalState | "skipped";

// Iter-27: localStorage keys retained ONLY for one-time migration from
// pre-iter-27 installs. After successful migration the entries are
// cleared and never read again.
const LEGACY_STORAGE_PREFIX = "plato:approvals";
const LEGACY_AUTO_SKIP_KEY = "plato:approvals:auto-skip";

function legacyApprovalKey(projectId: string, stage: StageId): string {
  return `${LEGACY_STORAGE_PREFIX}:${projectId}:${stage}`;
}

/**
 * Iter-27: returns the upstream stage blocking ``targetStage``, or null
 * if nothing is blocking. Reads from ``project.approvals`` (now carried
 * on the Project shape after the iter-27 backend change) so gate
 * evaluation stays synchronous — no async fetch per page render.
 *
 * Gating rules (mirror of approvals.py::compute_blocking_approval):
 *   - idea must be approved before literature/method/results/paper/referee
 *   - literature must be approved before method/results/paper/referee
 *   - method must be approved before results/paper/referee
 *
 * The frontend and backend implementations stay in lockstep so a user
 * who sees "blocked by idea" in the UI gets the same answer when the
 * server refuses the launch via the iter-27 ``run_stage`` 403.
 */
export function getBlockingApproval(
  project: Project,
  targetStage: StageId,
): StageId | null {
  const approvals = project.approvals;
  if (approvals?.auto_skip) return null;

  const guardOrder: { gate: StageId; blocks: StageId[] }[] = [
    { gate: "idea", blocks: ["literature", "method", "results", "paper", "referee"] },
    { gate: "literature", blocks: ["method", "results", "paper", "referee"] },
    { gate: "method", blocks: ["results", "paper", "referee"] },
  ];

  for (const { gate, blocks } of guardOrder) {
    if (!blocks.includes(targetStage)) continue;
    const gateStage = project.stages[gate];
    if (!gateStage || gateStage.status !== "done") continue;
    const state = approvals?.per_stage?.[gate] ?? "pending";
    if (state === "approved" || state === "skipped") continue;
    return gate;
  }
  return null;
}

/** React hook returning ``{blockedBy, isBlocked}`` for a given stage.
 *
 * Iter-27: re-derives synchronously from project on every change. The
 * old localStorage `storage` event listener is gone — project.approvals
 * is the single source of truth, so anywhere the project re-renders
 * (after ``refresh()`` post-PUT) the gate updates automatically.
 */
export function useApprovalGate(
  project: Project,
  stage: StageId,
): { blockedBy: StageId | null; isBlocked: boolean } {
  const blockedBy = React.useMemo(
    () => getBlockingApproval(project, stage),
    [project, stage],
  );
  return { blockedBy, isBlocked: blockedBy !== null };
}

async function persistApproval(
  projectId: string,
  current: ApprovalsState | null | undefined,
  stage: StageId,
  next: PersistedState,
): Promise<ApprovalsState> {
  // Read-modify-write: keep the rest of per_stage intact, only update
  // the target stage. Auto-skip flag passes through unchanged.
  const merged: ApprovalsState = {
    per_stage: { ...(current?.per_stage ?? {}), [stage]: next },
    auto_skip: current?.auto_skip ?? false,
  };
  return api.setApprovals(projectId, merged);
}

/**
 * Iter-27 one-time migration: if the project's server-side approvals
 * are empty AND legacy localStorage entries exist, push them up via
 * PUT /approvals and clear the local copy. Idempotent: subsequent
 * mounts hit the server-side state and skip the migration block.
 */
async function migrateLegacyApprovals(
  projectId: string,
  current: ApprovalsState | null | undefined,
): Promise<ApprovalsState | null> {
  if (typeof window === "undefined") return null;
  if (
    current
    && (Object.keys(current.per_stage).length > 0 || current.auto_skip)
  ) {
    return null;
  }
  const stages: StageId[] = ["data", "idea", "literature", "method", "results", "paper", "referee"];
  const found: Record<string, PersistedState> = {};
  for (const stage of stages) {
    try {
      const raw = window.localStorage.getItem(legacyApprovalKey(projectId, stage));
      if (
        raw === "pending"
        || raw === "approved"
        || raw === "rejected"
        || raw === "skipped"
      ) {
        found[stage] = raw;
      }
    } catch {
      /* ignore */
    }
  }
  let legacyAutoSkip = false;
  try {
    legacyAutoSkip = window.localStorage.getItem(LEGACY_AUTO_SKIP_KEY) === "1";
  } catch {
    /* ignore */
  }
  if (Object.keys(found).length === 0 && !legacyAutoSkip) return null;

  try {
    const next = await api.setApprovals(projectId, {
      per_stage: found,
      auto_skip: legacyAutoSkip,
    });
    // Clear localStorage so future mounts skip the migration block.
    try {
      for (const stage of stages) {
        window.localStorage.removeItem(legacyApprovalKey(projectId, stage));
      }
      window.localStorage.removeItem(LEGACY_AUTO_SKIP_KEY);
    } catch {
      /* ignore */
    }
    return next;
  } catch {
    return null;
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
  onApprovalsChanged,
}: ApprovalCheckpointsProps) {
  const checkpoint = CHECKPOINTS[currentStage];
  const [migrated, setMigrated] = React.useState(false);

  // Iter-27: project.approvals is the source of truth. We only need
  // to do a one-time migration check on mount; after that, the parent
  // refreshes the project (via onApprovalsChanged → refresh) and we
  // re-render with the new state.
  React.useEffect(() => {
    if (migrated) return;
    if (!project.id) {
      setMigrated(true);
      return;
    }
    let cancelled = false;
    (async () => {
      const migratedState = await migrateLegacyApprovals(
        project.id,
        project.approvals,
      );
      if (cancelled) return;
      setMigrated(true);
      if (migratedState && onApprovalsChanged) {
        await onApprovalsChanged();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [project.id, project.approvals, migrated, onApprovalsChanged]);

  if (!checkpoint || !migrated) return null;

  const stage = project.stages[checkpoint.stage];
  const nextStage = project.stages[checkpoint.nextStage];

  // Don't show anything until the upstream stage is done.
  if (!stage || stage.status !== "done") return null;

  const persisted = project.approvals?.per_stage?.[checkpoint.stage] ?? null;
  const autoSkipGlobal = project.approvals?.auto_skip ?? false;
  const downstreamStarted = nextStage && nextStage.status !== "empty";

  if ((autoSkipGlobal || downstreamStarted) && persisted === null) {
    // Persist a 'skipped' marker so the next render reflects the auto-skip
    // semantics and the gate evaluator (getBlockingApproval) treats this
    // checkpoint as cleared. Fire-and-forget — failures are recoverable on
    // the next mount.
    void persistApproval(
      project.id,
      project.approvals,
      checkpoint.stage,
      "skipped",
    ).then(() => onApprovalsChanged?.());
    return null;
  }

  if (persisted === "skipped") return null;

  const visualState: ApprovalState =
    persisted === "approved" || persisted === "rejected"
      ? persisted
      : "pending";

  const handle = (next: ApprovalState, cb: (s: StageId) => void) => () => {
    void persistApproval(
      project.id,
      project.approvals,
      checkpoint.stage,
      next,
    ).then(async () => {
      cb(checkpoint.stage);
      if (onApprovalsChanged) await onApprovalsChanged();
    });
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
