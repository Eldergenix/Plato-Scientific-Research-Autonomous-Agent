"use client";

import * as React from "react";
import { Sidebar } from "@/components/shell/sidebar";
import { TopBar } from "@/components/shell/topbar";
import { CommandPalette } from "@/components/shell/command-palette";
import { AgentLogStream } from "@/components/shell/agent-log-stream";
import { BottomBar } from "@/components/shell/bottom-bar";
import { CapabilitiesBanner } from "@/components/shell/capabilities-banner";
import { WorkspaceList } from "@/components/views/workspace-list";
import { DataStage } from "@/components/stages/data-stage";
import { IdeaStage } from "@/components/stages/idea-stage";
import { ResultsStage } from "@/components/stages/results-stage";
import { EmptyStage } from "@/components/stages/empty-stage";
import { ApprovalCheckpoints, getBlockingApproval } from "@/components/stages/approval-checkpoints";
import { CostMeterPanel, useCostMeter } from "@/components/cost/cost-meter-panel";
import { CreateProjectModal } from "@/components/projects/create-project-modal";
import { PaperPreview } from "@/components/stages/paper-preview";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Sheet } from "@/components/ui/sheet";
import { useProject } from "@/lib/use-project";
import { api } from "@/lib/api";
import type { RunRecord, ScientificScores, StageRunBody } from "@/lib/api";
import { cn, formatDuration } from "@/lib/utils";

import {
  ArrowLeft,
  BookMarked,
  ClipboardList,
  FlaskConical,
  Lightbulb,
  Menu,
  Newspaper,
  Stamp,
} from "lucide-react";
import type { Project, StageId, Stage } from "@/lib/types";

const PIPELINE_STAGE_ORDER: StageId[] = [
  "idea",
  "literature",
  "method",
  "results",
  "paper",
  "referee",
];

const PIPELINE_PHASES: Array<{
  id: "research" | "thinking" | "refining" | "writing";
  label: string;
  detail: string;
  stages: StageId[];
  agents: string[];
}> = [
  {
    id: "research",
    label: "Research",
    detail: "sources, novelty, experiments",
    stages: ["literature", "results"],
    agents: ["semantic_scholar", "novelty", "researcher", "engineer"],
  },
  {
    id: "thinking",
    label: "Thinking",
    detail: "ideas, plans, methods",
    stages: ["idea", "method"],
    agents: ["idea_maker", "maker", "planner", "methods"],
  },
  {
    id: "refining",
    label: "Refining",
    detail: "critique, review, retries",
    stages: ["idea", "method", "results", "referee"],
    agents: ["idea_hater", "hater", "plan_reviewer", "refine_results", "referee"],
  },
  {
    id: "writing",
    label: "Writing",
    detail: "paper sections and citations",
    stages: ["paper"],
    agents: [
      "keywords_node",
      "abstract_node",
      "introduction_node",
      "methods_node",
      "results_node",
      "conclusions_node",
      "citations_node",
    ],
  },
];

export default function Home() {
  const [collapsed, setCollapsed] = React.useState(false);
  const [cmdOpen, setCmdOpen] = React.useState(false);
  const [mobileNavOpen, setMobileNavOpen] = React.useState(false);
  const [openStage, setOpenStage] = React.useState<StageId | null>(null);
  const [logHeight, setLogHeight] = React.useState<0 | 30 | 60>(0);
  const [paused, setPaused] = React.useState(false);
  const [elapsedMs, setElapsedMs] = React.useState(0);
  const [filterTab, setFilterTab] = React.useState<"active" | "backlog" | "all">(
    "active",
  );

  const { project, log, plots, nodeEvents, codeEvents, loading, isLive, capabilities, startRun, cancelRun, selectProject, refresh } = useProject();
  const cost = useCostMeter();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const [runHistoryOpen, setRunHistoryOpen] = React.useState(false);
  const [runHistory, setRunHistory] = React.useState<RunRecord[] | null>(null);
  const [runHistoryError, setRunHistoryError] = React.useState<string | null>(null);
  const [cancelConfirmOpen, setCancelConfirmOpen] = React.useState(false);
  const [runToast, setRunToast] = React.useState<{
    title: string;
    body: string;
    tone: "amber" | "red";
  } | null>(null);

  const refreshRunHistory = React.useCallback(async () => {
    if (!project.id) {
      setRunHistoryError(null);
      setRunHistory([]);
      return;
    }
    try {
      setRunHistoryError(null);
      setRunHistory(await api.listRuns(project.id));
    } catch (error) {
      setRunHistoryError(error instanceof Error ? error.message : "Failed to load runs");
      setRunHistory([]);
    }
  }, [project.id]);

  React.useEffect(() => {
    if (!runHistoryOpen) return;
    void refreshRunHistory();
  }, [refreshRunHistory, runHistoryOpen]);

  // Fetch the current key-status snapshot once on mount so the
  // Run-pipeline button can render in a clearly-disabled state when
  // the user has no LLM provider keys set anywhere (env vars or in-app
  // store). Previously the button fired silently and the run failed
  // with a console.error the user never saw.
  const [hasAnyLlmKey, setHasAnyLlmKey] = React.useState<boolean | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    api
      .getKeysStatus()
      .then((s) => {
        if (cancelled) return;
        const llmStates = [
          s.OPENAI,
          s.GEMINI,
          s.ANTHROPIC,
          s.HUGGINGFACE,
          s.PERPLEXITY,
        ];
        setHasAnyLlmKey(llmStates.some((v) => v && v !== "unset"));
      })
      .catch(() => {
        // Backend offline / 5xx: don't disable the button on a probe
        // failure — the user should still be able to try.
        if (!cancelled) setHasAnyLlmKey(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const runPipelineDisabledReason = React.useMemo(() => {
    if (hasAnyLlmKey === false) {
      return "Add an LLM API key in /keys before running the pipeline.";
    }
    return undefined;
  }, [hasAnyLlmKey]);
  const nextPipelineStage = React.useMemo(() => getNextPipelineStage(project), [project]);

  const showRunToast = React.useCallback(
    (toast: { title: string; body: string; tone: "amber" | "red" }) => {
      setRunToast(toast);
      setTimeout(() => setRunToast(null), 5000);
    },
    [],
  );

  const requestCancel = React.useCallback(() => {
    if (!project.activeRun) return;
    setCancelConfirmOpen(true);
  }, [project.activeRun]);

  const [gateToast, setGateToast] = React.useState<{
    target: StageId;
    blockedBy: StageId;
  } | null>(null);

  // Wrap startRun so all callers (sidebar, palette, list, detail) respect approval gates.
  const guardedStartRun = React.useCallback<typeof startRun>(
    async (stage, body) => {
      if (runPipelineDisabledReason) {
        showRunToast({
          title: "Run blocked",
          body: runPipelineDisabledReason,
          tone: "amber",
        });
        return;
      }
      if (project.activeRun) {
        showRunToast({
          title: "Pipeline already running",
          body: `Cancel the ${project.activeRun.stage} run or wait for it to finish before starting another stage.`,
          tone: "amber",
        });
        return;
      }
      const blockedBy = getBlockingApproval(project, stage);
      if (blockedBy) {
        setGateToast({ target: stage, blockedBy });
        // Auto-dismiss after 4s
        setTimeout(() => setGateToast(null), 4000);
        return;
      }
      try {
        await startRun(stage, body);
        setLogHeight((height) => (height === 0 ? 30 : height));
      } catch (error) {
        showRunToast({
          title: "Run failed to start",
          body: error instanceof Error ? error.message : "The backend rejected the run request.",
          tone: "red",
        });
      }
    },
    [project, runPipelineDisabledReason, showRunToast, startRun],
  );

  React.useEffect(() => {
    if (!project.activeRun) {
      setElapsedMs(0);
      return;
    }
    const start = new Date(project.activeRun.startedAt).getTime();
    const t = setInterval(() => setElapsedMs(Date.now() - start), 1000);
    setElapsedMs(Date.now() - start);
    return () => clearInterval(t);
  }, [project.activeRun]);

  // Filter stages by current tab; the WorkspaceList itself handles grouping.
  const filteredProject = React.useMemo(() => {
    if (filterTab === "all") return project;
    const keep = (s: Stage): boolean => {
      if (filterTab === "active") {
        return s.status === "running" || s.status === "failed";
      }
      // backlog
      return s.status === "empty" || s.status === "pending" || s.status === "stale";
    };
    const stages = Object.fromEntries(
      Object.entries(project.stages).filter(([, s]) => keep(s as Stage)),
    ) as typeof project.stages;
    return { ...project, stages };
  }, [project, filterTab]);

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden bg-(--color-bg-page) text-(--color-text-primary)">
      <div className="hidden md:flex">
        <Sidebar
          collapsed={collapsed}
          onToggle={() => setCollapsed((c) => !c)}
          onOpenCommand={() => setCmdOpen(true)}
          onCreateProject={() => setCreateOpen(true)}
          projectName={loading ? "" : project.name}
        />
      </div>

      <Sheet
        open={mobileNavOpen}
        onOpenChange={setMobileNavOpen}
        title="Navigation"
        srOnly
        side="left"
        hideCloseButton
        className="w-[min(280px,calc(100vw-24px))]"
      >
        <Sidebar
          collapsed={false}
          onToggle={() => setMobileNavOpen(false)}
          onOpenCommand={() => {
            setMobileNavOpen(false);
            setCmdOpen(true);
          }}
          onCreateProject={() => {
            setMobileNavOpen(false);
            setCreateOpen(true);
          }}
          projectName={loading ? "" : project.name}
        />
      </Sheet>

      {/* Outer canvas with the Linear-style inset card */}
      <div className="flex-1 min-w-0 flex flex-col">
        <div
          className="flex min-h-12 items-center gap-2 px-3 hairline-b bg-(--color-bg-marketing) md:hidden"
          data-testid="mobile-shell-header"
        >
          <button
            type="button"
            aria-label="Open navigation"
            data-testid="mobile-nav-trigger"
            onClick={() => setMobileNavOpen(true)}
            className="size-8 inline-flex items-center justify-center rounded-[6px] text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)"
          >
            <Menu size={16} strokeWidth={1.75} />
          </button>
          <span className="min-w-0 truncate text-[13px] font-medium text-(--color-text-primary)">
            Plato
          </span>
        </div>

        {capabilities?.is_demo && (
          <CapabilitiesBanner isDemo notes={capabilities.notes} />
        )}
        {!isLive && capabilities === null && <OfflineBanner />}

        <div className="flex-1 min-h-0 flex flex-col p-1.5 md:pl-0">
          <main
            id="main-content"
            className="flex-1 min-h-0 flex flex-col bg-(--color-bg-card) overflow-hidden"
            style={{
              border: "1px solid var(--color-border-card)",
              borderRadius: 12,
              boxShadow:
                "0 4px 4px -1px rgba(0, 0, 0, 0.04), 0 1px 1px rgba(0, 0, 0, 0.08)",
            }}
          >
            <TopBar
              project={
                // While the initial fetch is in flight, hand TopBar a
                // blank-name + zeroed project so the cost meter and
                // project-title don't briefly render the iter-1
                // EMPTY_PROJECT placeholder ("Untitled project · $0.00 ·
                // 0 tok"). The Sidebar already does the same on line 160.
                loading
                  ? { ...project, name: "", totalCostCents: 0, totalTokens: 0 }
                  : project
              }
              elapsedMs={elapsedMs}
              filterTab={filterTab}
              onChangeFilter={setFilterTab}
              onCancelRun={requestCancel}
              onRunPipeline={() => void guardedStartRun(nextPipelineStage)}
              runPipelineDisabledReason={
                loading ? "Loading…" : runPipelineDisabledReason
              }
              onOpenCostMeter={cost.openMeter}
              onAddFilter={() =>
                setFilterTab((t) =>
                  t === "active" ? "backlog" : t === "backlog" ? "all" : "active",
                )
              }
              onChangeDisplay={() =>
                setLogHeight((h) => (h === 0 ? 30 : h === 30 ? 60 : 0))
              }
              onToggleDetails={() => setDetailsOpen(true)}
              onMoreActions={() => setCmdOpen(true)}
              onToggleFavorite={() => {
                /* favorites — Phase 4 */
              }}
              onOpenNotifications={() => {
                /* notifications — Phase 4 */
              }}
            />

            <PipelineRunMonitor
              project={project}
              log={log}
              nodeEvents={nodeEvents}
              codeEvents={codeEvents}
              elapsedMs={elapsedMs}
              nextStage={nextPipelineStage}
              onOpenStage={(stage) => setOpenStage(stage)}
              onOpenLogs={() => setLogHeight((height) => (height === 0 ? 30 : height))}
            />

            <div className="flex-1 min-h-0 overflow-hidden">
              {openStage ? (
                <StageDetail
                  stage={openStage}
                  project={project}
                  plots={plots}
                  nodeEvents={nodeEvents}
                  codeEvents={codeEvents}
                  onBack={() => setOpenStage(null)}
                  onRun={(body) => guardedStartRun(openStage, body)}
                  onRefresh={refresh}
                  onCancelRun={requestCancel}
                />
              ) : (
                <div className="h-full overflow-y-auto">
                  <WorkspaceList
                    project={filteredProject}
                    onSelectStage={(stage) => setOpenStage(stage)}
                    onRunStage={(stage) => guardedStartRun(stage)}
                    onCancelRun={requestCancel}
                    pipelineStage={nextPipelineStage}
                  />
                </div>
              )}
            </div>

            <AgentLogStream
              lines={log}
              height={logHeight}
              onChangeHeight={setLogHeight}
              paused={paused}
              onTogglePause={() => setPaused((p) => !p)}
            />
          </main>

          <BottomBar
            onAskAi={() => setCmdOpen(true)}
            onOpenHistory={() => setRunHistoryOpen(true)}
          />
        </div>
      </div>

      <CommandPalette
        open={cmdOpen}
        onOpenChange={setCmdOpen}
        onRunStage={(s) => guardedStartRun(s)}
        onCreateProject={() => setCreateOpen(true)}
      />

      <CostMeterPanel
        open={cost.open}
        onOpenChange={cost.onOpenChange}
        project={project}
      />

      <ProjectDetailsSheet
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
        project={project}
      />

      <RunHistorySheet
        open={runHistoryOpen}
        onOpenChange={setRunHistoryOpen}
        runs={runHistory}
        error={runHistoryError}
        onRefresh={refreshRunHistory}
      />

      <CreateProjectModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(createdProject) => {
          selectProject(createdProject);
          setCreateOpen(false);
        }}
      />

      {runToast && (
        <div
          role="alert"
          className="fixed bottom-12 right-4 z-50 max-w-sm surface-linear-card px-4 py-3"
          style={{
            background: "var(--color-bg-card)",
            border:
              runToast.tone === "red"
                ? "1px solid var(--color-status-red-spec)"
                : "1px solid var(--color-status-amber-spec)",
          }}
        >
          <div className="flex items-start gap-3">
            <Lightbulb
              size={14}
              strokeWidth={1.75}
              className={cn(
                "mt-0.5",
                runToast.tone === "red"
                  ? "text-(--color-status-red-spec)"
                  : "text-(--color-status-amber-spec)",
              )}
            />
            <div className="flex-1 text-[12.5px] leading-[1.5]">
              <div className="font-medium text-(--color-text-primary)">
                {runToast.title}
              </div>
              <div className="mt-0.5 text-(--color-text-tertiary)">
                {runToast.body}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setRunToast(null)}
              className="text-[16px] leading-none text-(--color-text-tertiary) hover:text-(--color-text-primary)"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {gateToast && (
        <div
          role="alert"
          className="fixed bottom-12 right-4 z-50 max-w-sm surface-linear-card px-4 py-3"
          style={{
            background: "var(--color-bg-card)",
            border: "1px solid var(--color-status-amber-spec)",
          }}
        >
          <div className="flex items-start gap-3">
            <Lightbulb size={14} strokeWidth={1.75} className="text-(--color-status-amber-spec) mt-0.5" />
            <div className="flex-1 text-[12.5px] leading-[1.5]">
              <div className="font-medium text-(--color-text-primary)">
                Blocked by approval gate
              </div>
              <div className="mt-0.5 text-(--color-text-tertiary)">
                Approve <span className="font-mono">{gateToast.blockedBy}</span> before running{" "}
                <span className="font-mono">{gateToast.target}</span>. Open the {gateToast.blockedBy}{" "}
                stage and click <span className="font-medium">Approve</span>.
              </div>
            </div>
            <button
              type="button"
              onClick={() => setGateToast(null)}
              className="text-(--color-text-tertiary) hover:text-(--color-text-primary) text-[16px] leading-none"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={cancelConfirmOpen}
        onOpenChange={setCancelConfirmOpen}
        title={
          project.activeRun
            ? `Cancel ${project.activeRun.stage} run?`
            : "Cancel run?"
        }
        description="The subprocess will receive SIGTERM and shut down cleanly. Partial output already written to disk is preserved."
        confirmLabel="Cancel run"
        cancelLabel="Keep running"
        variant="danger"
        onConfirm={cancelRun}
      />
    </div>
  );
}

function RunHistorySheet({
  open,
  onOpenChange,
  runs,
  error,
  onRefresh,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runs: RunRecord[] | null;
  error: string | null;
  onRefresh: () => Promise<void>;
}) {
  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Run history"
      side="right"
      className="w-[min(400px,calc(100vw-24px))]"
    >
      <div className="space-y-4 px-4 py-4 text-[13px]">
        <div className="flex items-center justify-between gap-3">
          <p className="text-(--color-text-tertiary)">
            Persisted pipeline runs for the current project.
          </p>
          <button
            type="button"
            onClick={() => void onRefresh()}
            className="rounded-[6px] border border-(--color-border-card) px-2.5 py-1 text-[12px] text-(--color-text-secondary) hover:bg-(--color-ghost-bg-hover)"
          >
            Refresh
          </button>
        </div>

        {error ? (
          <div
            role="alert"
            className="rounded-[6px] border border-(--color-status-red-spec) px-3 py-2 text-(--color-status-red-spec)"
          >
            {error}
          </div>
        ) : null}

        {runs === null ? (
          <div className="text-(--color-text-tertiary)">Loading runs...</div>
        ) : runs.length === 0 ? (
          <div className="text-(--color-text-tertiary)">No runs recorded yet.</div>
        ) : (
          <div className="space-y-2">
            {runs.map((run) => (
              <div
                key={run.id}
                className="rounded-[8px] border border-(--color-border-card) px-3 py-2.5"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="capitalize text-(--color-text-primary)">
                    {run.stage}
                  </span>
                  <span className="rounded-full bg-(--color-ghost-bg) px-2 py-0.5 font-mono text-[11px] text-(--color-text-tertiary)">
                    {run.status}
                  </span>
                </div>
                <div className="mt-1 font-mono text-[11px] text-(--color-text-tertiary)">
                  {run.id}
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-[11.5px] text-(--color-text-tertiary)">
                  <span>Started {formatRunTime(run.startedAt)}</span>
                  <span className="text-right">Finished {formatRunTime(run.finishedAt)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Sheet>
  );
}

function formatRunTime(value?: string | null): string {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "n/a";
  return date.toLocaleString();
}

function ProjectDetailsSheet({
  open,
  onOpenChange,
  project,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: ReturnType<typeof useProject>["project"];
}) {
  const stageEntries = Object.values(project.stages);
  const completed = stageEntries.filter((stage) => stage.status === "done").length;
  const active = project.activeRun;

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Project details"
      side="right"
      className="w-[min(360px,calc(100vw-24px))]"
    >
      <div className="space-y-4 px-4 py-4 text-[13px]">
        <section className="space-y-2">
          <h3 className="text-[12px] font-medium uppercase tracking-wide text-(--color-text-tertiary)">
            Project
          </h3>
          <dl className="space-y-1.5">
            <DetailRow label="Name" value={project.name} />
            <DetailRow label="ID" value={project.id || "—"} mono />
            <DetailRow label="Journal" value={project.journal} />
            <DetailRow
              label="Updated"
              value={new Date(project.updatedAt).toLocaleString()}
            />
          </dl>
        </section>

        <section className="space-y-2">
          <h3 className="text-[12px] font-medium uppercase tracking-wide text-(--color-text-tertiary)">
            Progress
          </h3>
          <dl className="space-y-1.5">
            <DetailRow label="Stages complete" value={`${completed}/${stageEntries.length}`} />
            <DetailRow
              label="Active run"
              value={active ? `${active.stage} · ${active.runId}` : "None"}
              mono={Boolean(active)}
            />
            <DetailRow
              label="Tokens"
              value={project.totalTokens.toLocaleString()}
            />
            <DetailRow
              label="Cost"
              value={`$${(project.totalCostCents / 100).toFixed(2)}`}
            />
          </dl>
        </section>

        <section className="space-y-2">
          <h3 className="text-[12px] font-medium uppercase tracking-wide text-(--color-text-tertiary)">
            Stage status
          </h3>
          <div className="space-y-1.5">
            {stageEntries.map((stage) => (
              <div
                key={stage.id}
                className="flex items-center justify-between gap-3 rounded-[6px] border border-(--color-border-card) px-2.5 py-2"
              >
                <span className="capitalize text-(--color-text-secondary)">
                  {stage.label}
                </span>
                <span className="font-mono text-[11px] text-(--color-text-tertiary)">
                  {stage.status}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </Sheet>
  );
}

function DetailRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-(--color-text-tertiary)">{label}</dt>
      <dd
        className={cn(
          "min-w-0 text-right text-(--color-text-primary)",
          mono && "font-mono text-[11.5px]",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function getNextPipelineStage(project: ReturnType<typeof useProject>["project"]): StageId {
  if (project.activeRun) return project.activeRun.stage;
  return (
    PIPELINE_STAGE_ORDER.find((stage) => project.stages[stage]?.status === "failed") ??
    PIPELINE_STAGE_ORDER.find((stage) => project.stages[stage]?.status !== "done") ??
    "idea"
  );
}

function phaseForStage(stage: StageId | undefined) {
  if (!stage) return PIPELINE_PHASES[1];
  return PIPELINE_PHASES.find((phase) => phase.stages.includes(stage)) ?? PIPELINE_PHASES[1];
}

function phaseForAgent(agent: string | undefined) {
  if (!agent) return null;
  const normalized = agent.toLowerCase();
  return (
    PIPELINE_PHASES.find((phase) =>
      phase.agents.some((candidate) => normalized.includes(candidate)),
    ) ?? null
  );
}

function formatAgentName(value: string): string {
  return value
    .replace(/_node$/u, "")
    .replace(/_/gu, " ")
    .replace(/\b\w/gu, (char) => char.toUpperCase());
}

function latestActivityItems({
  log,
  nodeEvents,
  codeEvents,
}: {
  log: ReturnType<typeof useProject>["log"];
  nodeEvents: ReturnType<typeof useProject>["nodeEvents"];
  codeEvents: ReturnType<typeof useProject>["codeEvents"];
}) {
  const nodeItems = nodeEvents.slice(-3).map((event) => ({
    key: `node-${event.ts}-${event.name}-${event.kind}`,
    ts: event.ts,
    phase: phaseForStage(event.stage as StageId | undefined).label,
    text: `${event.kind === "entered" ? "Started" : "Finished"} ${formatAgentName(event.name)}`,
  }));
  const logItems = log.slice(-4).map((line, index) => {
    const raw = line.agent ?? line.source;
    return {
      key: `log-${line.ts}-${index}`,
      ts: Date.parse(line.ts),
      phase: formatAgentName(raw || "agent"),
      text: line.text.trim(),
    };
  });
  const latestCode = codeEvents[codeEvents.length - 1];
  const codeItems = latestCode
    ? [
        {
          key: `code-${latestCode.ts}-${latestCode.index ?? "latest"}`,
          ts: latestCode.ts,
          phase: "Execution",
          text: `Executed code cell ${latestCode.index != null ? latestCode.index + 1 : ""}`.trim(),
        },
      ]
    : [];

  return [...nodeItems, ...logItems, ...codeItems]
    .filter((item) => item.text.length > 0)
    .sort((a, b) => {
      const aTime = Number.isFinite(a.ts) ? a.ts : 0;
      const bTime = Number.isFinite(b.ts) ? b.ts : 0;
      return bTime - aTime;
    })
    .slice(0, 5);
}

function PipelineRunMonitor({
  project,
  log,
  nodeEvents,
  codeEvents,
  elapsedMs,
  nextStage,
  onOpenStage,
  onOpenLogs,
}: {
  project: ReturnType<typeof useProject>["project"];
  log: ReturnType<typeof useProject>["log"];
  nodeEvents: ReturnType<typeof useProject>["nodeEvents"];
  codeEvents: ReturnType<typeof useProject>["codeEvents"];
  elapsedMs: number;
  nextStage: StageId;
  onOpenStage: (stage: StageId) => void;
  onOpenLogs: () => void;
}) {
  const active = project.activeRun;
  const latestNode = nodeEvents[nodeEvents.length - 1]?.name;
  const latestLog = log[log.length - 1];
  const activePhase =
    phaseForAgent(latestNode) ??
    phaseForAgent(latestLog?.agent ?? latestLog?.source) ??
    phaseForStage(active?.stage ?? nextStage);
  const activity = React.useMemo(
    () => latestActivityItems({ log, nodeEvents, codeEvents }),
    [log, nodeEvents, codeEvents],
  );

  if (!active) return null;

  return (
    <section
      className="hairline-b bg-(--color-bg-marketing) px-3 py-2"
      data-testid="pipeline-run-monitor"
      aria-label="Pipeline run monitor"
    >
      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-(--color-ghost-bg-hover) px-2 py-0.5 font-mono text-[11px] text-(--color-text-secondary)">
              {active.stage}
            </span>
            <span className="text-[12px] font-medium text-(--color-text-primary)">
              Agent is {activePhase.label.toLowerCase()}
            </span>
            <span className="text-[12px] text-(--color-text-tertiary)">
              {activePhase.detail}
            </span>
            <span className="font-mono text-[11px] text-(--color-text-quaternary)">
              {formatDuration(elapsedMs)}
            </span>
            {active.step != null && active.totalSteps != null ? (
              <span className="font-mono text-[11px] text-(--color-text-tertiary)">
                step {active.step}/{active.totalSteps}
              </span>
            ) : null}
            {active.attempt != null && active.totalAttempts != null ? (
              <span className="font-mono text-[11px] text-(--color-text-tertiary)">
                attempt {active.attempt}/{active.totalAttempts}
              </span>
            ) : null}
          </div>

          <div className="mt-2 flex min-w-0 flex-wrap gap-1.5">
            {PIPELINE_STAGE_ORDER.map((stage) => {
              const stageState = project.stages[stage]?.status ?? "empty";
              const isActive = active.stage === stage;
              return (
                <button
                  key={stage}
                  type="button"
                  onClick={() => onOpenStage(stage)}
                  className={cn(
                    "inline-flex h-6 items-center gap-1.5 rounded-full border px-2 text-[11px] capitalize transition-colors",
                    isActive
                      ? "border-(--color-brand-indigo) bg-(--color-brand-indigo)/10 text-(--color-text-primary)"
                      : stageState === "done"
                        ? "border-(--color-status-green-spec)/40 text-(--color-status-green-spec)"
                        : stageState === "failed"
                          ? "border-(--color-status-red-spec)/40 text-(--color-status-red-spec)"
                          : "border-(--color-border-card) text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover)",
                  )}
                >
                  <span
                    className={cn(
                      "size-1.5 rounded-full",
                      isActive
                        ? "bg-(--color-brand-indigo)"
                        : stageState === "done"
                          ? "bg-(--color-status-green-spec)"
                          : stageState === "failed"
                            ? "bg-(--color-status-red-spec)"
                            : "bg-(--color-text-quaternary)",
                    )}
                  />
                  {stage}
                </button>
              );
            })}
          </div>

          <div className="mt-2 grid gap-1.5 md:grid-cols-4">
            {PIPELINE_PHASES.map((phase) => {
              const phaseActive = phase.id === activePhase.id;
              const phaseDone = phase.stages.every(
                (stage) => project.stages[stage]?.status === "done",
              );
              return (
                <div
                  key={phase.id}
                  className={cn(
                    "rounded-[6px] border px-2.5 py-2",
                    phaseActive
                      ? "border-(--color-brand-indigo) bg-(--color-brand-indigo)/10"
                      : phaseDone
                        ? "border-(--color-status-green-spec)/30"
                        : "border-(--color-border-card)",
                  )}
                >
                  <div className="text-[12px] font-medium text-(--color-text-primary)">
                    {phase.label}
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-(--color-text-tertiary)">
                    {phase.detail}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="w-full shrink-0 rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) p-2 lg:w-[360px]">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wide text-(--color-text-tertiary)">
              Live activity
            </span>
            <button
              type="button"
              onClick={onOpenLogs}
              className="text-[11px] text-(--color-text-tertiary) hover:text-(--color-text-primary)"
            >
              Open logs
            </button>
          </div>
          {activity.length > 0 ? (
            <ol className="mt-1.5 space-y-1">
              {activity.map((item) => (
                <li key={item.key} className="grid grid-cols-[72px_1fr] gap-2 text-[11.5px]">
                  <span className="truncate font-mono text-(--color-text-quaternary)">
                    {item.phase}
                  </span>
                  <span className="truncate text-(--color-text-secondary)">
                    {item.text}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <div className="mt-1.5 text-[11.5px] text-(--color-text-tertiary)">
              Waiting for the first agent event from this run.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------- stage detail */

function StageDetail({
  stage,
  project,
  plots,
  nodeEvents,
  codeEvents,
  onBack,
  onRun,
  onRefresh,
  onCancelRun,
}: {
  stage: StageId;
  project: ReturnType<typeof useProject>["project"];
  plots: ReturnType<typeof useProject>["plots"];
  nodeEvents: ReturnType<typeof useProject>["nodeEvents"];
  codeEvents: ReturnType<typeof useProject>["codeEvents"];
  onBack: () => void;
  onRun: (body?: StageRunBody) => void | Promise<void>;
  onRefresh: () => Promise<void>;
  onCancelRun: () => void | Promise<void>;
}) {
  return (
    <div className="h-full flex flex-col">
      <div className="hairline-b flex items-center gap-2 px-4 h-9">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 h-7 px-2 rounded-[6px] text-[12px] text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary) transition-colors"
        >
          <ArrowLeft size={12} strokeWidth={1.75} />
          Back to all stages
        </button>
        <span className="text-[12px] text-(--color-text-quaternary)">/</span>
        <span className="text-[12px] font-medium capitalize text-(--color-text-primary)">
          {stage}
        </span>
      </div>

      <ApprovalCheckpoints
        project={project}
        currentStage={stage}
        onApprove={() => {
          void onRefresh();
        }}
        onReject={() => {}}
        onRefine={() => onRun()}
        onPivot={onBack}
      />

      <div className="flex-1 min-h-0 overflow-hidden">
        <StagePane
          stage={stage}
          project={project}
          plots={plots}
          nodeEvents={nodeEvents}
          codeEvents={codeEvents}
          onRun={onRun}
          onRefresh={onRefresh}
          onCancelRun={onCancelRun}
        />
      </div>
    </div>
  );
}

function StagePane({
  stage,
  project,
  plots,
  nodeEvents,
  codeEvents,
  onRun,
  onRefresh,
  onCancelRun,
}: {
  stage: StageId;
  project: ReturnType<typeof useProject>["project"];
  plots: ReturnType<typeof useProject>["plots"];
  nodeEvents: ReturnType<typeof useProject>["nodeEvents"];
  codeEvents: ReturnType<typeof useProject>["codeEvents"];
  onRun: (body?: StageRunBody) => void | Promise<void>;
  onRefresh: () => Promise<void>;
  onCancelRun: () => void | Promise<void>;
}) {
  switch (stage) {
    case "data":
      return (
        <DataStage
          projectId={project.id}
          origin={project.stages.data.origin}
          lastEditedAt={project.stages.data.lastRunAt}
          onSaved={() => {
            void onRefresh();
          }}
        />
      );
    case "idea":
      return (
        <IdeaStage
          projectId={project.id}
          origin={project.stages.idea.origin}
          lastEditedAt={project.stages.idea.lastRunAt}
          model={project.stages.idea.model}
          onRun={onRun}
        />
      );
    case "results":
      return project.activeRun?.stage === "results" || (plots && plots.length > 0) ? (
        <ResultsStage
          project={project}
          plots={plots}
          nodeEvents={nodeEvents}
          codeEvents={codeEvents}
          onCancelRun={onCancelRun}
        />
      ) : (
        <EmptyStage
          icon={FlaskConical}
          title="Results"
          description="Run experiments and produce plots from the methodology. This stage executes generated Python code via cmbagent."
          onGenerate={() => onRun()}
        />
      );
    case "literature":
      return (
        <GeneratedMarkdownStage
          project={project}
          stage="literature"
          icon={BookMarked}
          title="Literature review"
          description="Discovered papers, novelty verdict, and reasoning trail. Run a Semantic Scholar / FutureHouse novelty check to populate this view."
          onGenerate={() => onRun()}
        />
      );
    case "method":
      return (
        <GeneratedMarkdownStage
          project={project}
          stage="method"
          icon={ClipboardList}
          title="Methodology"
          description="A structured ~500-word methodology describing how the experiment will be performed. Generate from the idea, or upload a markdown file."
          onGenerate={() => onRun()}
        />
      );
    case "paper":
      return project.stages.paper.status === "done" ? (
        <PaperStagePane
          projectId={project.id}
          lastRunAt={project.stages.paper.lastRunAt}
          updatedAt={project.updatedAt}
        />
      ) : (
        <EmptyStage
          icon={Newspaper}
          title="Paper draft"
          description="Three-way LaTeX / markdown / rendered-PDF view. Generate the paper from results once experiments complete."
          onGenerate={() => onRun()}
        />
      );
    case "referee":
      return (
        <GeneratedMarkdownStage
          project={project}
          stage="referee"
          icon={Stamp}
          title="Peer review"
          description="A 0–9 scored review across originality, clarity, methodology, results, and significance — produced from the rendered PDF."
          onGenerate={() => onRun()}
        />
      );
    default:
      return null;
  }
}

function GeneratedMarkdownStage({
  project,
  stage,
  icon: Icon,
  title,
  description,
  onGenerate,
}: {
  project: Project;
  stage: Exclude<StageId, "data" | "idea" | "results" | "paper">;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  title: string;
  description: string;
  onGenerate: () => void | Promise<void>;
}) {
  const [markdown, setMarkdown] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const stageState = project.stages[stage];
  const refetchKey = `${project.id}|${stage}|${stageState.status}|${stageState.lastRunAt ?? ""}|${project.activeRun?.runId ?? "idle"}`;

  React.useEffect(() => {
    if (!project.id) {
      setMarkdown(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const r = await api.readStage(project.id, stage);
        if (cancelled) return;
        const body = r?.markdown?.trim();
        setMarkdown(body ? (r?.markdown ?? null) : null);
      } catch (e: unknown) {
        if (cancelled) return;
        const message = e instanceof Error ? e.message : String(e);
        setError(message.includes("404") ? null : message);
        setMarkdown(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [project.id, stage, refetchKey]);

  if (!markdown) {
    return (
      <EmptyStage
        icon={Icon}
        title={title}
        description={
          error
            ? `Could not load this stage artifact: ${error}`
            : description
        }
        onGenerate={onGenerate}
      />
    );
  }

  return (
    <article className="flex h-full flex-col overflow-auto">
      <header className="hairline-b flex items-baseline gap-3 px-6 pb-4 pt-6">
        <Icon size={20} strokeWidth={1.5} className="text-(--color-brand-hover)" />
        <h2 className="font-h1 tracking-[-0.704px]">{title}</h2>
        <span className="text-[12px] text-(--color-text-tertiary)">
          {loading ? "Refreshing" : stageState.model ? `AI · ${stageState.model}` : "AI generated"}
        </span>
      </header>
      <pre className="whitespace-pre-wrap px-6 py-5 text-[13.5px] leading-[1.7] text-(--color-text-primary)">
        {markdown}
      </pre>
    </article>
  );
}

function PaperStagePane({
  projectId,
  lastRunAt,
  updatedAt,
}: {
  projectId: string;
  lastRunAt?: string;
  updatedAt: string;
}) {
  const [artifacts, setArtifacts] = React.useState<{
    pdfUrl?: string;
    sections: import("@/components/stages/paper-preview").PaperSection[];
  }>({ sections: [] });
  const [scores, setScores] = React.useState<ScientificScores | undefined>();

  // Re-fetch when the paper stage's lastRunAt changes — the worker writes
  // paper/main.{tex,pdf} as the last step of the run, so the new artifacts
  // appear shortly after the run completes.
  React.useEffect(() => {
    let cancelled = false;
    api
      .getPaperArtifacts(projectId)
      .then((r) => {
        if (cancelled) return;
        setArtifacts({
          pdfUrl: r.pdfUrl,
          sections: r.sections.map((s) => ({
            id: s.id,
            name: s.name,
            status: s.status,
            markdown: s.markdown,
            tex: s.tex,
          })),
        });
      })
      .catch(() => {
        if (!cancelled) setArtifacts({ sections: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, lastRunAt]);

  React.useEffect(() => {
    let cancelled = false;
    api
      .getScientificScores(projectId)
      .then((r) => {
        if (!cancelled) setScores(r);
      })
      .catch(() => {
        if (!cancelled) setScores(undefined);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, lastRunAt]);

  // Single synthesized version pill — the file route doesn't expose git
  // history and parsing it would be overkill for this view. Keyed on
  // updatedAt so the pill identity changes when the project changes.
  const versions = React.useMemo(
    () => [{ id: `latest-${updatedAt}`, label: "Latest", current: true }],
    [updatedAt],
  );

  return (
    <PaperPreview
      pdfUrl={artifacts.pdfUrl}
      sections={artifacts.sections}
      scores={scores}
      versions={versions}
    />
  );
}

function OfflineBanner() {
  return (
    <div className="hairline-b bg-(--color-status-amber)/10 px-4 py-1.5 flex items-center gap-3 text-[12px]">
      <Lightbulb size={13} strokeWidth={1.5} className="text-(--color-status-amber)" />
      <span className="font-medium text-(--color-text-primary)">
        API offline · showing sample data
      </span>
      <span className="text-(--color-text-tertiary)">
        Start the backend with{" "}
        <code className="font-mono text-(--color-text-secondary) px-1 py-0.5 rounded bg-(--color-ghost-bg)">
          plato dashboard
        </code>
      </span>
    </div>
  );
}
