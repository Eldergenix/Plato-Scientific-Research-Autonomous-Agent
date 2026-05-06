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
import { cn } from "@/lib/utils";

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
import type { StageId, Stage } from "@/lib/types";

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
  const [cancelConfirmOpen, setCancelConfirmOpen] = React.useState(false);

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
        const llmStates = [s.OPENAI, s.GEMINI, s.ANTHROPIC, s.PERPLEXITY];
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

  const requestCancel = React.useCallback(() => {
    if (!project.activeRun) return;
    setCancelConfirmOpen(true);
  }, [project.activeRun]);

  const handleSidebarStage = React.useCallback((stage: string) => {
    if (stage === "history") {
      setLogHeight((h) => (h === 0 ? 30 : 0));
      return;
    }
    if (stage === "stages") {
      setOpenStage("idea");
      return;
    }
    setOpenStage(stage as StageId);
  }, []);

  const [gateToast, setGateToast] = React.useState<{
    target: StageId;
    blockedBy: StageId;
  } | null>(null);

  // Wrap startRun so all callers (sidebar, palette, list, detail) respect approval gates.
  const guardedStartRun = React.useCallback<typeof startRun>(
    async (stage, body) => {
      const blockedBy = getBlockingApproval(project, stage);
      if (blockedBy) {
        setGateToast({ target: stage, blockedBy });
        // Auto-dismiss after 4s
        setTimeout(() => setGateToast(null), 4000);
        return;
      }
      await startRun(stage, body);
    },
    [project, startRun],
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
          activeStage={openStage ?? undefined}
          onSelectStage={handleSidebarStage}
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
          activeStage={openStage ?? undefined}
          onSelectStage={(stage) => {
            setMobileNavOpen(false);
            handleSidebarStage(stage);
          }}
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
              onRunPipeline={() => guardedStartRun("idea")}
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

            <div className="flex-1 min-h-0 overflow-hidden">
              {openStage ? (
                <StageDetail
                  stage={openStage}
                  project={project}
                  plots={plots}
                  nodeEvents={nodeEvents}
                  codeEvents={codeEvents}
                  onBack={() => setOpenStage(null)}
                  onRun={() => guardedStartRun(openStage)}
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
            onOpenHistory={() => setLogHeight((h) => (h === 0 ? 30 : 0))}
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

      <CreateProjectModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(createdProject) => {
          selectProject(createdProject);
          setCreateOpen(false);
        }}
      />

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
  onRun: () => void | Promise<void>;
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
        onRefine={onRun}
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
  onRun: () => void | Promise<void>;
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
          onGenerate={onRun}
        />
      );
    case "literature":
      return (
        <EmptyStage
          icon={BookMarked}
          title="Literature review"
          description="Discovered papers, novelty verdict, and reasoning trail. Run a Semantic Scholar / FutureHouse novelty check to populate this view."
          onGenerate={onRun}
        />
      );
    case "method":
      return (
        <EmptyStage
          icon={ClipboardList}
          title="Methodology"
          description="A structured ~500-word methodology describing how the experiment will be performed. Generate from the idea, or upload a markdown file."
          onGenerate={onRun}
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
          onGenerate={onRun}
        />
      );
    case "referee":
      return (
        <EmptyStage
          icon={Stamp}
          title="Peer review"
          description="A 0–9 scored review across originality, clarity, methodology, results, and significance — produced from the rendered PDF."
          onGenerate={onRun}
        />
      );
    default:
      return null;
  }
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

  // Single synthesized version pill — the file route doesn't expose git
  // history and parsing it would be overkill for this view. Keyed on
  // updatedAt so the pill identity changes when the project changes.
  const versions = React.useMemo(
    () => [{ id: `latest-${updatedAt}`, label: "Latest", current: true }],
    [updatedAt],
  );

  return <PaperPreview pdfUrl={artifacts.pdfUrl} sections={artifacts.sections} versions={versions} />;
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
