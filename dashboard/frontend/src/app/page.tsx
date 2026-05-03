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
import { PaperPreview, type PaperSection } from "@/components/stages/paper-preview";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useProject } from "@/lib/use-project";
import { api } from "@/lib/api";

// Hoisted to module scope so PaperPreview's `versions` prop has a stable
// identity across renders — re-rendering StagePane (which fires every
// second during an active run via the elapsed-timer interval) no longer
// allocates a fresh array. Pairs with the section list below.
const DEFAULT_PAPER_VERSIONS = [
  { id: "v1", label: "v1" },
  { id: "v2", label: "v2" },
  { id: "v3", label: "v3" },
  { id: "v4", label: "v4", current: true },
];

const DEFAULT_PAPER_SECTIONS: PaperSection[] = [
  { id: "abstract", name: "Abstract", status: "compiled", markdown: "## Abstract\n\nWe present a hierarchical Bayesian pipeline for joint extraction of (2,2,0) and (3,3,0) ringdown modes from GW231123…" },
  { id: "introduction", name: "Introduction", status: "compiled" },
  { id: "methods", name: "Methods", status: "warning", errorMessage: "Citation key 'Cornish2023' not found in references.bib" },
  { id: "results", name: "Results", status: "compiled" },
  { id: "conclusions", name: "Conclusions", status: "pending" },
  { id: "references", name: "References", status: "compiled" },
];
import {
  ArrowLeft,
  BookMarked,
  ClipboardList,
  FlaskConical,
  Lightbulb,
  Newspaper,
  Stamp,
} from "lucide-react";
import type { StageId, Stage } from "@/lib/types";

export default function Home() {
  const [collapsed, setCollapsed] = React.useState(false);
  const [cmdOpen, setCmdOpen] = React.useState(false);
  const [openStage, setOpenStage] = React.useState<StageId | null>(null);
  const [logHeight, setLogHeight] = React.useState<0 | 30 | 60>(0);
  const [paused, setPaused] = React.useState(false);
  const [elapsedMs, setElapsedMs] = React.useState(0);
  const [filterTab, setFilterTab] = React.useState<"active" | "backlog" | "all">(
    "active",
  );

  const { project, log, plots, isLive, capabilities, startRun, cancelRun, refresh } = useProject();
  const cost = useCostMeter();
  const [createOpen, setCreateOpen] = React.useState(false);
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
    <div className="flex h-screen w-screen overflow-hidden bg-(--color-bg-page) text-(--color-text-primary)">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
        onOpenCommand={() => setCmdOpen(true)}
        onCreateProject={() => setCreateOpen(true)}
        projectName={project.name}
        activeStage={openStage ?? undefined}
        onSelectStage={(stage) => {
          // Sidebar TEAM_LINKS uses pseudo-ids: "stages" → idea (jump to first stage),
          // "history" → toggle log drawer, "referee" → real referee stage.
          if (stage === "history") {
            setLogHeight((h) => (h === 0 ? 30 : 0));
            return;
          }
          if (stage === "stages") {
            setOpenStage("idea");
            return;
          }
          setOpenStage(stage as StageId);
        }}
      />

      {/* Outer canvas with the Linear-style inset card */}
      <div className="flex-1 min-w-0 flex flex-col">
        {capabilities?.is_demo && (
          <CapabilitiesBanner isDemo notes={capabilities.notes} />
        )}
        {!isLive && capabilities === null && <OfflineBanner />}

        <div className="flex-1 min-h-0 flex flex-col p-1.5 pl-0">
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
              project={project}
              elapsedMs={elapsedMs}
              filterTab={filterTab}
              onChangeFilter={setFilterTab}
              onCancelRun={requestCancel}
              onRunPipeline={() => guardedStartRun("idea")}
              runPipelineDisabledReason={runPipelineDisabledReason}
              onOpenCostMeter={cost.openMeter}
              onAddFilter={() =>
                setFilterTab((t) =>
                  t === "active" ? "backlog" : t === "backlog" ? "all" : "active",
                )
              }
              onChangeDisplay={() => setLogHeight((h) => (h === 0 ? 30 : h === 30 ? 60 : 0))}
              onToggleDetails={cost.openMeter}
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
                  onBack={() => setOpenStage(null)}
                  onRun={() => guardedStartRun(openStage)}
                  onRefresh={refresh}
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

      <CreateProjectModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => {
          setCreateOpen(false);
          void refresh();
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

/* -------------------------------------------------------------- stage detail */

function StageDetail({
  stage,
  project,
  plots,
  onBack,
  onRun,
  onRefresh,
}: {
  stage: StageId;
  project: ReturnType<typeof useProject>["project"];
  plots: ReturnType<typeof useProject>["plots"];
  onBack: () => void;
  onRun: () => void | Promise<void>;
  onRefresh: () => Promise<void>;
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
          /* approval state persisted by the component itself */
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
          onRun={onRun}
          onRefresh={onRefresh}
        />
      </div>
    </div>
  );
}

function StagePane({
  stage,
  project,
  plots,
  onRun,
  onRefresh,
}: {
  stage: StageId;
  project: ReturnType<typeof useProject>["project"];
  plots: ReturnType<typeof useProject>["plots"];
  onRun: () => void | Promise<void>;
  onRefresh: () => Promise<void>;
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
        <ResultsStage project={project} plots={plots} />
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
        <PaperPreview
          sections={DEFAULT_PAPER_SECTIONS}
          versions={DEFAULT_PAPER_VERSIONS}
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
