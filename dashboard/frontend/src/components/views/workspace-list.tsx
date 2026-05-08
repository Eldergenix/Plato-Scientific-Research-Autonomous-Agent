"use client";

import * as React from "react";
import { ChevronRight, PlayCircle, Plus, Signal, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn, formatRelativeTime, formatTokens } from "@/lib/utils";
import { MODELS_BY_ID } from "@/lib/models";
import type {
  Project,
  Provider,
  Stage,
  StageId,
  StageStatus,
} from "@/lib/types";
import { StatusIcon } from "./status-icon";

type GroupKey = "in-progress" | "backlog" | "done" | "failed";

interface WorkspaceListProps {
  project: Project;
  onSelectStage: (stage: StageId) => void;
  onRunStage: (stage: StageId) => void;
  onCancelRun: () => void;
  pipelineStage?: StageId;
}

const STAGE_ORDER: StageId[] = [
  "data",
  "idea",
  "literature",
  "method",
  "results",
  "paper",
  "referee",
];

const STAGE_INDEX: Record<StageId, number> = STAGE_ORDER.reduce(
  (acc, id, idx) => {
    acc[id] = idx + 1;
    return acc;
  },
  {} as Record<StageId, number>,
);

const GROUP_DEFS: Array<{
  key: GroupKey;
  label: string;
  matches: (status: StageStatus) => boolean;
  status: StageStatus;
  styleClass: string;
  metaClass: string;
}> = [
  {
    key: "failed",
    label: "Failed",
    matches: (s) => s === "failed",
    status: "failed",
    styleClass: "group-failed",
    metaClass: "text-(--color-text-row-meta)",
  },
  {
    key: "in-progress",
    label: "In Progress",
    matches: (s) => s === "running",
    status: "running",
    styleClass: "group-progress",
    metaClass: "text-(--color-text-progress-meta)",
  },
  {
    key: "backlog",
    label: "Backlog",
    matches: (s) => s === "empty" || s === "pending" || s === "stale",
    status: "empty",
    styleClass: "group-backlog",
    metaClass: "text-(--color-text-backlog-meta)",
  },
  {
    key: "done",
    label: "Done",
    matches: (s) => s === "done",
    status: "done",
    styleClass: "group-done",
    metaClass: "text-(--color-text-row-meta)",
  },
];

const PROVIDER_AVATAR: Record<
  Provider,
  { letter: string; bg: string; fg: string }
> = {
  anthropic: { letter: "A", bg: "#2A6F6A", fg: "#E6F8F5" },
  openai: { letter: "O", bg: "#10A37F", fg: "#E7FFF7" },
  gemini: { letter: "G", bg: "#4EA7FC", fg: "#0B1B33" },
  huggingface: { letter: "H", bg: "#FF9D00", fg: "#231400" },
  perplexity: { letter: "P", bg: "#1F8FA3", fg: "#E5FBFF" },
  semantic_scholar: { letter: "S", bg: "#5E6AD2", fg: "#F2F3FF" },
};

const NONE_AVATAR = {
  letter: "·",
  bg: "var(--color-bg-button-glass)",
  fg: "var(--color-text-row-meta)",
};

const PROVIDER_DOT_COLOR: Record<Provider, string> = {
  anthropic: "purple",
  openai: "green",
  gemini: "blue",
  huggingface: "amber",
  perplexity: "teal",
  semantic_scholar: "purple",
};

function groupStages(project: Project) {
  const stages = Object.values(project.stages);
  const result: Record<GroupKey, Stage[]> = {
    failed: [],
    "in-progress": [],
    backlog: [],
    done: [],
  };
  for (const def of GROUP_DEFS) {
    result[def.key] = stages
      .filter((s) => def.matches(s.status))
      .sort((a, b) => STAGE_INDEX[a.id] - STAGE_INDEX[b.id]);
  }
  return result;
}

function buildTitle(stage: Stage): string {
  const parts: string[] = [stage.label];
  if (stage.origin === "ai") parts.push("AI generated");
  else if (stage.origin === "edited") parts.push("Edited");
  else if (stage.progressLabel) parts.push(stage.progressLabel);
  return parts.join(" · ");
}

function ProviderAvatar({ provider }: { provider: Provider | null }) {
  const av = provider ? PROVIDER_AVATAR[provider] : NONE_AVATAR;
  return (
    <span
      className="flex h-[18px] w-[18px] items-center justify-center rounded-full text-[10px] font-medium"
      style={{ backgroundColor: av.bg, color: av.fg }}
      aria-label={provider ?? "no provider"}
    >
      {av.letter}
    </span>
  );
}

function TagPill({
  color,
  dotColor,
  label,
}: {
  color?: string;
  dotColor?: string;
  label: string;
}) {
  return (
    <span
      className="tag-pill"
      data-color={color}
      style={dotColor ? { color: dotColor } : undefined}
    >
      <span>{label}</span>
    </span>
  );
}

interface IssueRowProps {
  stage: Stage;
  project: Project;
  onSelect: () => void;
  onRun: () => void;
  onCancelRun: () => void;
}

function IssueRow({ stage, project, onSelect, onRun, onCancelRun }: IssueRowProps) {
  const idx = STAGE_INDEX[stage.id];
  const issueId = `PLATO-${idx}`;
  const model = stage.model ? MODELS_BY_ID[stage.model] : undefined;
  const provider = (model?.provider ?? null) as Provider | null;
  const showJournal = stage.id === "paper" && project.journal !== "NONE";
  const activeRun = project.activeRun;
  const isActiveRun = activeRun?.stage === stage.id;
  const isBlockedByOtherRun = Boolean(activeRun && !isActiveRun);
  const tokens =
    stage.id === activeRun?.stage ? project.totalTokens : 0;
  const priorityColor =
    stage.status === "failed"
      ? "var(--color-status-orange)"
      : stage.status === "running"
        ? "var(--color-text-row-meta)"
        : "var(--color-text-quinary)";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className={cn(
        "group flex min-h-[44px] cursor-pointer flex-wrap items-center gap-x-2 gap-y-1 rounded-[8px] px-3 py-2 sm:h-[36px] sm:min-h-0 sm:flex-nowrap sm:py-0 sm:pl-4 sm:pr-[26px]",
        "transition-colors duration-100 hover:bg-(--color-ghost-bg-hover)",
      )}
      data-stage={stage.id}
    >
      <span
        className="hidden h-[22px] w-[18px] flex-none items-center justify-center opacity-0 transition-opacity group-hover:opacity-100 sm:flex"
        aria-hidden
      >
        <input
          type="checkbox"
          onClick={(e) => e.stopPropagation()}
          className="h-3 w-3 cursor-pointer rounded-[3px] border border-(--color-border-pill) bg-transparent accent-(--color-brand-interactive)"
        />
      </span>

      <Signal
        size={16}
        strokeWidth={1.75}
        className="flex-none"
        style={{ color: priorityColor }}
        aria-hidden
      />

      <span
        className="flex-none whitespace-nowrap text-[13px] font-medium tabular-nums"
        style={{
          minWidth: 56,
          color: "var(--color-text-row-meta)",
          letterSpacing: "-0.26px",
        }}
      >
        {issueId}
      </span>

      <StatusIcon status={stage.status} />

      <div className="flex min-w-[160px] flex-1 items-center gap-2">
        <span className="truncate text-[13px] font-medium text-(--color-text-row-title)">
          {buildTitle(stage)}
        </span>

        <span className="ml-auto hidden min-w-0 flex-none items-center gap-[3px] sm:flex">
          {model ? (
            <TagPill
              color={PROVIDER_DOT_COLOR[provider as Provider]}
              dotColor={undefined}
              label={model.label}
            />
          ) : null}

          {project.activeRun?.stage === stage.id ? (
            <TagPill color="blue" dotColor="var(--color-status-blue)" label="cmbagent" />
          ) : stage.status === "running" ? (
            <TagPill color="blue" dotColor="var(--color-status-blue)" label="fast" />
          ) : null}

          {showJournal ? (
            <TagPill color="red" dotColor="var(--color-status-red-spec)" label={project.journal} />
          ) : null}

          {tokens > 0 ? (
            <TagPill color="purple" label={formatTokens(tokens)} />
          ) : null}

          {stage.status === "failed" ? (
            <TagPill color="red" dotColor="var(--color-status-red-spec)" label="failed" />
          ) : null}
        </span>

        <ProviderAvatar provider={provider} />
      </div>

      <span
        className="hidden flex-none text-right text-[12px] font-medium sm:block"
        style={{ width: 60, color: "var(--color-text-row-meta)" }}
      >
        {stage.lastRunAt ? formatRelativeTime(stage.lastRunAt) : "—"}
      </span>

      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          if (isActiveRun) {
            onCancelRun();
            return;
          }
          onRun();
        }}
        disabled={isBlockedByOtherRun}
        title={
          isBlockedByOtherRun
            ? `Wait for the ${activeRun?.stage} run to finish or cancel it first.`
            : undefined
        }
        aria-label={isActiveRun ? `Cancel ${stage.label} run` : `Run ${stage.label}`}
        data-testid={`stage-run-button-${stage.id}`}
        className={cn(
          "ml-auto inline-flex h-7 flex-none items-center gap-1.5 rounded-[6px] border px-2",
          "text-[12px] font-medium transition-colors",
          isActiveRun
            ? "border-(--color-status-red-spec) text-(--color-status-red-spec) hover:bg-(--color-status-red-spec)/10"
            : "border-(--color-border-card) text-(--color-text-secondary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)",
          "disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent",
        )}
      >
        {isActiveRun ? (
          <Square size={11} strokeWidth={1.75} />
        ) : (
          <PlayCircle size={12} strokeWidth={1.75} />
        )}
        {isActiveRun ? "Stop" : "Run"}
      </button>
    </div>
  );
}

interface GroupSectionProps {
  groupKey: GroupKey;
  label: string;
  status: StageStatus;
  styleClass: string;
  metaClass: string;
  stages: Stage[];
  collapsed: boolean;
  onToggle: () => void;
  onAddItem: () => void;
  project: Project;
  onSelectStage: (id: StageId) => void;
  onRunStage: (id: StageId) => void;
  onCancelRun: () => void;
}

function GroupSection({
  label,
  status,
  styleClass,
  metaClass,
  stages,
  collapsed,
  onToggle,
  onAddItem,
  project,
  onSelectStage,
  onRunStage,
  onCancelRun,
}: GroupSectionProps) {
  if (stages.length === 0) return null;

  return (
    <section className="flex flex-col gap-[2px]">
      <header
        className={cn(
          "group flex h-[36px] items-center gap-2 rounded-[8px] px-2",
          styleClass,
        )}
        style={
          status === "failed"
            ? {
                background: "var(--gradient-failed)",
              }
            : status === "done"
              ? {
                  background: "var(--gradient-done)",
                }
              : undefined
        }
      >
        <button
          type="button"
          onClick={onToggle}
          className="flex h-[28px] w-[28px] flex-none items-center justify-center rounded-[6px] text-(--color-text-tertiary-spec) transition-transform hover:bg-(--color-ghost-bg-hover)"
          aria-label={collapsed ? "Expand group" : "Collapse group"}
          aria-expanded={!collapsed}
        >
          <ChevronRight
            size={14}
            strokeWidth={2}
            className={cn(
              "transition-transform duration-150",
              !collapsed && "rotate-90",
            )}
          />
        </button>

        <StatusIcon status={status} />

        <span className="text-[13px] font-medium text-(--color-text-secondary-spec)">
          {label}
        </span>

        <span className={cn("text-[13px] font-medium", metaClass)}>
          {stages.length}
        </span>

        <button
          type="button"
          onClick={onAddItem}
          className="ml-auto flex h-[24px] w-[24px] flex-none items-center justify-center rounded-[6px] text-(--color-text-tertiary-spec) opacity-0 transition-opacity hover:bg-(--color-ghost-bg-hover) group-hover:opacity-100"
          aria-label={`Add to ${label}`}
        >
          <Plus size={14} strokeWidth={2} />
        </button>
      </header>

      {!collapsed ? (
        <div className="flex flex-col">
          {stages.map((stage) => (
            <IssueRow
              key={stage.id}
              stage={stage}
              project={project}
              onSelect={() => onSelectStage(stage.id)}
              onRun={() => onRunStage(stage.id)}
              onCancelRun={onCancelRun}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function WorkspaceList({
  project,
  onSelectStage,
  onRunStage,
  onCancelRun,
  pipelineStage = "idea",
}: WorkspaceListProps) {
  const groups = React.useMemo(() => groupStages(project), [project]);
  const [collapsed, setCollapsed] = React.useState<Record<GroupKey, boolean>>({
    failed: false,
    "in-progress": false,
    backlog: false,
    done: false,
  });

  const toggle = (key: GroupKey) =>
    setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));

  const handleAdd = (key: GroupKey) => {
    const next = groups[key][0];
    if (next) onRunStage(next.id);
  };

  // When every group is empty (e.g. a freshly-created project, or a
  // tab filter that excluded everything), show a single empty-state
  // instead of an invisible canvas.
  const totalStages = GROUP_DEFS.reduce(
    (n, def) => n + groups[def.key].length,
    0,
  );

  if (totalStages === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center"
        data-testid="workspace-empty-state"
      >
        <div className="text-[14px] font-medium text-(--color-text-primary)">
          No stages match this view
        </div>
        <div className="max-w-md text-[12.5px] text-(--color-text-tertiary-spec)">
          A new project starts with all stages empty. Run the pipeline to
          generate an idea, methods, results, and a draft paper — or open a
          stage from the sidebar to start one individually.
        </div>
        <div className="mt-3">
          <Button
            variant="primary"
            size="sm"
            onClick={() => onRunStage(pipelineStage)}
            data-testid="workspace-empty-run-pipeline"
          >
            <PlayCircle size={12} strokeWidth={1.75} />
            Run
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 px-2 py-2 sm:px-4 sm:py-3">
      {GROUP_DEFS.map((def) => (
        <GroupSection
          key={def.key}
          groupKey={def.key}
          label={def.label}
          status={def.status}
          styleClass={def.styleClass}
          metaClass={def.metaClass}
          stages={groups[def.key]}
          collapsed={collapsed[def.key]}
          onToggle={() => toggle(def.key)}
          onAddItem={() => handleAdd(def.key)}
          project={project}
          onSelectStage={onSelectStage}
          onRunStage={onRunStage}
          onCancelRun={onCancelRun}
        />
      ))}
    </div>
  );
}
