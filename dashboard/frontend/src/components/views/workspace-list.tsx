"use client";

import * as React from "react";
import { ChevronRight, PlayCircle, Plus, Signal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn, formatRelativeTime, formatTokens } from "@/lib/utils";
import { getCachedModelsCatalog, loadModelsCatalog } from "@/lib/models-async";
import type {
  ModelDef,
  Project,
  Provider,
  Stage,
  StageId,
  StageStatus,
} from "@/lib/types";
import { StatusIcon } from "./status-icon";

// Lookup table for model->provider, sourced from the catalog. The home
// shell renders WorkspaceList synchronously, so we eagerly trigger the
// catalog load on mount; until it resolves we fall back to a stage's
// raw model id (no provider color), which beats blocking First Load JS
// on the catalog or showing a spinner inside every row.
function useModelsById(): Record<string, ModelDef> | null {
  const [byId, setById] = React.useState<Record<string, ModelDef> | null>(
    () => getCachedModelsCatalog()?.MODELS_BY_ID ?? null,
  );
  React.useEffect(() => {
    if (byId) return;
    let alive = true;
    loadModelsCatalog().then((c) => {
      if (alive) setById(c.MODELS_BY_ID);
    });
    return () => {
      alive = false;
    };
  }, [byId]);
  return byId;
}

type GroupKey = "in-progress" | "backlog" | "done" | "failed";

interface WorkspaceListProps {
  project: Project;
  onSelectStage: (stage: StageId) => void;
  onRunStage: (stage: StageId) => void;
  onCancelRun: () => void;
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
  perplexity: { letter: "P", bg: "#1F8FA3", fg: "#E5FBFF" },
  semantic_scholar: { letter: "S", bg: "#5E6AD2", fg: "#F2F3FF" },
};

const NONE_AVATAR = { letter: "·", bg: "#1D1D1F", fg: "#919193" };

const PROVIDER_DOT_COLOR: Record<Provider, string> = {
  anthropic: "purple",
  openai: "green",
  gemini: "blue",
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
    <span className="tag-pill" data-color={color}>
      {dotColor ? (
        <span
          className="block flex-none rounded-full"
          style={{ width: 9, height: 9, backgroundColor: dotColor }}
          aria-hidden
        />
      ) : null}
      <span>{label}</span>
    </span>
  );
}

interface IssueRowProps {
  stage: Stage;
  project: Project;
  onSelect: () => void;
  onRun: () => void;
}

function IssueRow({
  stage,
  project,
  onSelect,
  modelsById,
}: IssueRowProps & {
  modelsById: Record<string, ModelDef> | null;
}) {
  const idx = STAGE_INDEX[stage.id];
  const issueId = `PLATO-${idx}`;
  const model = stage.model && modelsById ? modelsById[stage.model] : undefined;
  const provider = (model?.provider ?? null) as Provider | null;
  const showJournal = stage.id === "paper" && project.journal !== "NONE";
  const tokens =
    stage.id === project.activeRun?.stage ? project.totalTokens : 0;
  const priorityColor =
    stage.status === "failed"
      ? "#FF7236"
      : stage.status === "running"
        ? "#949496"
        : "rgba(148, 148, 150, 0.4)";

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
        "group flex h-[36px] cursor-pointer items-center gap-2 rounded-[8px] pl-4 pr-[26px]",
        "transition-colors duration-100 hover:bg-[#151516]",
      )}
      data-stage={stage.id}
    >
      <span
        className="flex h-[22px] w-[18px] flex-none items-center justify-center opacity-0 transition-opacity group-hover:opacity-100"
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
          color: "#949496",
          letterSpacing: "-0.26px",
        }}
      >
        {issueId}
      </span>

      <StatusIcon status={stage.status} />

      <div className="flex min-w-0 flex-1 items-center gap-2">
        <span className="truncate text-[13px] font-medium text-(--color-text-row-title)">
          {buildTitle(stage)}
        </span>

        <span className="ml-auto flex flex-none items-center gap-[3px]">
          {model ? (
            <TagPill
              color={PROVIDER_DOT_COLOR[provider as Provider]}
              dotColor={undefined}
              label={model.label}
            />
          ) : null}

          {project.activeRun?.stage === stage.id ? (
            <TagPill color="blue" dotColor="#4EA7FC" label="cmbagent" />
          ) : stage.status === "running" ? (
            <TagPill color="blue" dotColor="#4EA7FC" label="fast" />
          ) : null}

          {showJournal ? (
            <TagPill color="red" dotColor="#EB5757" label={project.journal} />
          ) : null}

          {tokens > 0 ? (
            <TagPill color="purple" label={formatTokens(tokens)} />
          ) : null}

          {stage.status === "failed" ? (
            <TagPill color="red" dotColor="#EB5757" label="code-exec failed" />
          ) : null}
        </span>

        <ProviderAvatar provider={provider} />
      </div>

      <span
        className="flex-none text-right text-[12px] font-medium"
        style={{ width: 60, color: "#949496" }}
      >
        {stage.lastRunAt ? formatRelativeTime(stage.lastRunAt) : "—"}
      </span>
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
  modelsById: Record<string, ModelDef> | null;
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
  modelsById,
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
                background:
                  "linear-gradient(90deg, #1F1818 0%, #171718 100%)",
              }
            : status === "done"
              ? {
                  background:
                    "linear-gradient(90deg, #1C1A18 0%, #171718 100%)",
                }
              : undefined
        }
      >
        <button
          type="button"
          onClick={onToggle}
          className="flex h-[28px] w-[28px] flex-none items-center justify-center rounded-[6px] text-(--color-text-tertiary-spec) transition-transform hover:bg-white/5"
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
          className="ml-auto flex h-[24px] w-[24px] flex-none items-center justify-center rounded-[6px] text-(--color-text-tertiary-spec) opacity-0 transition-opacity hover:bg-white/5 group-hover:opacity-100"
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
              modelsById={modelsById}
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
}: WorkspaceListProps) {
  const groups = React.useMemo(() => groupStages(project), [project]);
  const modelsById = useModelsById();
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
            onClick={() => onRunStage("idea")}
            data-testid="workspace-empty-run-pipeline"
          >
            <PlayCircle size={12} strokeWidth={1.75} />
            Run pipeline
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
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
          modelsById={modelsById}
        />
      ))}
    </div>
  );
}
