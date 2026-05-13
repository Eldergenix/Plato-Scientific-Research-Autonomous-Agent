"use client";

import * as React from "react";
import { api, setActiveRunId } from "./api";
import type { RunEventCodeExecute, StageRunBody } from "./api";
import type { LogLine, Project, Stage, StageId } from "./types";

export interface PlotEntry {
  name: string;
  url: string;
}

// Iter-28 — agent-activity ring buffer entry. Mirrors the
// ``NodeActivityEvent`` type that ResultsStage expects, lifted up
// to the hook surface so any consumer that wants to render swimlanes
// can subscribe via ``useProject().nodeEvents``.
export interface NodeEventEntry {
  name: string;
  stage?: string;
  ts: number;
  kind: "entered" | "exited";
  durationMs?: number;
}

// Iter-30 — per-cell code-execute event entry consumed by CodePane.
// One entry per cell in the executor's artifacts.cells list (for the
// real iter-18 LocalJupyter / iter-20 Modal+E2B / cmbagent backends).
export interface CodeEventEntry {
  index?: number;
  source?: string;
  stdout?: string | null;
  stderr?: string | null;
  executor?: string | null;
  ts: number;
  error?: {
    ename?: string;
    evalue?: string;
  } | null;
}

interface ProjectState {
  project: Project;
  log: LogLine[];
  plots: PlotEntry[];
  /**
   * Iter-28: ring-buffer of node.entered / node.exited events from
   * the active run. Capped at NODE_EVENTS_MAX so a long run can't
   * grow without bound; consumers (AgentSwimlane) snapshot the
   * latest window.
   */
  nodeEvents: NodeEventEntry[];
  /**
   * Iter-30: per-cell code-execute events from the active run.
   * Consumed by CodePane to render the actual source / stdout / error
   * the executor produced. Capped at CODE_EVENTS_MAX since each entry
   * carries the cell's full source string.
   */
  codeEvents: CodeEventEntry[];
  isLive: boolean; // true when fetched from API; false when offline / pre-bootstrap
  loading: boolean; // true until the first ``getProject`` resolves (or fails)
  capabilities: {
    is_demo: boolean;
    allowed_stages: StageId[];
    notes: string[];
  } | null;
  startRun: (stage: StageId, body?: StageRunBody) => Promise<void>;
  cancelRun: () => Promise<void>;
  selectProject: (project: Project) => void;
  refresh: () => Promise<void>;
  refreshPlots: () => Promise<void>;
}

// Iter-23: replaced the SAMPLE_PROJECT first-paint flash. The previous
// hook seeded React state with a hardcoded ``demo-gw231123 / run_8a2f1c``
// project so the UI could render before the backend responded — but
// every dashboard load briefly showed fake astro project data, even on
// completely empty installs and even for biology / ML domains. The
// "is this my data?" flash was confusing and the offline banner showed
// fabricated history.
//
// Now: bootstrap from an EMPTY_PROJECT shape with no fake metadata.
// Consumers consult the new ``loading`` flag (true until the first
// ``getProject`` resolves or fails) to render skeletons / empty states
// instead of the prior phantom run + token totals.
const _emptyStages: Record<StageId, Stage> = {
  data: { id: "data", label: "Data", status: "empty" },
  idea: { id: "idea", label: "Idea", status: "empty" },
  literature: { id: "literature", label: "Literature", status: "empty" },
  method: { id: "method", label: "Method", status: "empty" },
  results: { id: "results", label: "Results", status: "empty" },
  paper: { id: "paper", label: "Paper", status: "empty" },
  referee: { id: "referee", label: "Referee", status: "empty" },
};

export const EMPTY_PROJECT: Project = {
  id: "",
  // Mirror the backend's ``Project.name`` default ("Untitled project"
  // — see ``plato_dashboard.domain.models.Project``). Keeping the name
  // non-empty means the topbar renders something instead of a 0-width
  // h1; matching the backend default means the user can't visually
  // tell whether they're seeing the placeholder or a freshly-created
  // project that they haven't named yet (which is fine — both states
  // present the same affordance: rename it).
  name: "Untitled project",
  createdAt: new Date(0).toISOString(),
  updatedAt: new Date(0).toISOString(),
  journal: "NONE",
  stages: _emptyStages,
  activeRun: null,
  totalTokens: 0,
  totalCostCents: 0,
};

// Cap on retained node.entered/node.exited events. AgentSwimlane only
// needs the recent window; long runs would otherwise grow the array
// without bound.
const NODE_EVENTS_MAX = 500;
// Iter-30: per-cell code.execute events. Lower cap because each entry
// can be sizable (full source + stdout). 200 covers typical results
// runs; older cells fall off the front when exceeded.
const CODE_EVENTS_MAX = 200;
const SELECTED_PROJECT_STORAGE_KEY = "plato:selected-project-id";

export function persistSelectedProjectId(projectId: string | null): void {
  if (typeof window === "undefined") return;
  if (projectId) {
    window.localStorage.setItem(SELECTED_PROJECT_STORAGE_KEY, projectId);
  } else {
    window.localStorage.removeItem(SELECTED_PROJECT_STORAGE_KEY);
  }
}

function readSelectedProjectId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(SELECTED_PROJECT_STORAGE_KEY);
}

export function pickPreferredProject(projects: Project[]): Project | undefined {
  if (projects.length === 0) return undefined;
  const selectedProjectId = readSelectedProjectId();
  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  if (selectedProject) return selectedProject;

  return projects.reduce((latest, project) => {
    const latestTime = Date.parse(latest.updatedAt);
    const projectTime = Date.parse(project.updatedAt);
    if (!Number.isFinite(projectTime)) return latest;
    if (!Number.isFinite(latestTime)) return project;
    return projectTime > latestTime ? project : latest;
  });
}

function coerceCodeEvent(evt: RunEventCodeExecute): CodeEventEntry {
  const tsMs = (() => {
    const raw = evt.ts;
    if (typeof raw === "number") return raw;
    const parsed = Date.parse(String(raw));
    return Number.isFinite(parsed) ? parsed : Date.now();
  })();
  return {
    index: typeof evt.index === "number" ? evt.index : undefined,
    source: typeof evt.source === "string" ? evt.source : undefined,
    stdout:
      evt.stdout === null || typeof evt.stdout === "string"
        ? evt.stdout
        : undefined,
    stderr:
      evt.stderr === null || typeof evt.stderr === "string"
        ? evt.stderr
        : undefined,
    executor:
      evt.executor === null || typeof evt.executor === "string"
        ? evt.executor
        : undefined,
    ts: tsMs,
    error:
      evt.error === null || typeof evt.error === "object"
        ? (evt.error as CodeEventEntry["error"])
        : undefined,
  };
}

const STEP_RE = /\bStep\s+(\d+)\s*(?:\/|of)\s*(\d+)\b/i;
const ATTEMPT_RE = /\bAttempt\s+(\d+)\s*(?:\/|of)\s*(\d+)\b/i;

function progressFromLogLine(text: string): Pick<
  NonNullable<Project["activeRun"]>,
  "step" | "totalSteps" | "attempt" | "totalAttempts"
> | null {
  const next: Pick<
    NonNullable<Project["activeRun"]>,
    "step" | "totalSteps" | "attempt" | "totalAttempts"
  > = {};
  const step = STEP_RE.exec(text);
  if (step) {
    next.step = Number(step[1]);
    next.totalSteps = Number(step[2]);
  }
  const attempt = ATTEMPT_RE.exec(text);
  if (attempt) {
    next.attempt = Number(attempt[1]);
    next.totalAttempts = Number(attempt[2]);
  }
  return Object.keys(next).length > 0 ? next : null;
}

export function useProject(): ProjectState {
  const [project, setProject] = React.useState<Project>(EMPTY_PROJECT);
  const [log, setLog] = React.useState<LogLine[]>([]);
  const [plots, setPlots] = React.useState<PlotEntry[]>([]);
  const [nodeEvents, setNodeEvents] = React.useState<NodeEventEntry[]>([]);
  const [codeEvents, setCodeEvents] = React.useState<CodeEventEntry[]>([]);
  const [isLive, setIsLive] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [caps, setCaps] = React.useState<ProjectState["capabilities"]>(null);
  const sseUnsubRef = React.useRef<(() => void) | null>(null);
  const projectIdRef = React.useRef<string | null>(null);

  const refresh = React.useCallback(async () => {
    if (projectIdRef.current) {
      try {
        const p = await api.getProject(projectIdRef.current);
        setProject(p);
      } catch {
        // ignore — keep last known state
      }
    }
  }, []);

  const refreshPlots = React.useCallback(async () => {
    if (!projectIdRef.current) return;
    try {
      const r = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1"}/projects/${projectIdRef.current}/plots`,
      );
      if (!r.ok) return;
      const list = (await r.json()) as PlotEntry[];
      setPlots(list);
    } catch {
      // ignore
    }
  }, []);

  const refreshHistoricalResultsEvents = React.useCallback(async (pid: string) => {
    try {
      const runs = await api.listRuns(pid);
      const resultRuns = runs
        .filter((run) => run.stage === "results" && run.status === "succeeded")
        .sort((a, b) => {
          const aTime = Date.parse(a.finishedAt ?? a.startedAt ?? "");
          const bTime = Date.parse(b.finishedAt ?? b.startedAt ?? "");
          return (
            (Number.isFinite(aTime) ? aTime : 0) -
            (Number.isFinite(bTime) ? bTime : 0)
          );
        });
      const latest = resultRuns[resultRuns.length - 1];
      if (!latest) {
        if (projectIdRef.current === pid) setCodeEvents([]);
        return;
      }
      const events = await api.listRunEvents(pid, latest.id);
      const entries = events
        .filter((evt): evt is RunEventCodeExecute => evt.kind === "code.execute")
        .map(coerceCodeEvent)
        .slice(-CODE_EVENTS_MAX);
      if (projectIdRef.current === pid) setCodeEvents(entries);
    } catch {
      // Keep the live buffer. Historical replay is best-effort for reloads.
    }
  }, []);

  const selectProject = React.useCallback((nextProject: Project) => {
    projectIdRef.current = nextProject.id;
    persistSelectedProjectId(nextProject.id);
    setProject(nextProject);
    setLog([]);
    setPlots([]);
    setNodeEvents([]);
    setCodeEvents([]);
    setActiveRunId(null);
    sseUnsubRef.current?.();
    sseUnsubRef.current = null;
    void refreshHistoricalResultsEvents(nextProject.id);
  }, [refreshHistoricalResultsEvents]);

  // Bootstrap: ping API, load caps + first project (or create one).
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await api.health();
        const c = await api.capabilities();
        if (cancelled) return;
        setCaps({
          is_demo: c.is_demo,
          allowed_stages: c.allowed_stages,
          notes: c.notes,
        });

        const list = await api.listProjects();
        let active: Project;
        if (list.length > 0) {
          const preferred = pickPreferredProject(list);
          if (!preferred) throw new Error("No project available.");
          active = preferred;
        } else {
          active = await api.createProject("New project");
          persistSelectedProjectId(active.id);
        }
        if (cancelled) return;
        projectIdRef.current = active.id;
        setProject(active);
        setLog([]);
        setIsLive(true);
        // Initial plots fetch.
        try {
          const plotsRes = await fetch(
            `${process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1"}/projects/${active.id}/plots`,
          );
          if (plotsRes.ok) {
            const list = (await plotsRes.json()) as PlotEntry[];
            if (!cancelled) setPlots(list);
          }
        } catch {
          // ignore
        }
        if (!cancelled) void refreshHistoricalResultsEvents(active.id);
      } catch {
        // Iter-23: backend offline → stay on EMPTY_PROJECT instead of
        // SAMPLE_PROJECT. The offline banner is the right place to tell
        // the user the backend is unreachable; rendering fake astro
        // data underneath made every offline state look like a live
        // (but stale) GW231123 session.
        setIsLive(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      sseUnsubRef.current?.();
    };
  }, [refreshHistoricalResultsEvents]);

  const startRun = React.useCallback<ProjectState["startRun"]>(
    async (stage, body) => {
      if (!isLive || !projectIdRef.current) return;
      try {
        const run = await api.startRun(projectIdRef.current, stage, body);
        // Set the module-level run-id so every subsequent fetchJson
        // call carries X-Plato-Run-Id for backend log correlation.
        // Cleared in the SSE close handler below.
        setActiveRunId(run.id);
        // Iter-28: clear any node events from the previous run so the
        // swimlane doesn't show stale lanes from a different run.
        setNodeEvents([]);
        // Iter-30: same logic for code events.
        setCodeEvents([]);
        setProject((prev) => {
          const currentStage = prev.stages[stage];
          return {
            ...prev,
            activeRun: {
              runId: run.id,
              stage,
              startedAt: run.started_at ?? new Date().toISOString(),
            },
            stages: {
              ...prev.stages,
              [stage]: currentStage
                ? {
                    ...currentStage,
                    status: "running",
                    progressLabel: "Running",
                  }
                : currentStage,
            },
          };
        });
        sseUnsubRef.current?.();
        sseUnsubRef.current = api.subscribeRunEvents(
          projectIdRef.current,
          run.id,
          (evt) => {
            if (evt.kind === "log.line") {
              const text = String(evt.text ?? "");
              // Ring-buffer cap: keep at most LOG_MAX entries so a long
              // run can't grow the log array (and the rendered DOM)
              // without bound. Visualization layer should still pair
              // this with virtualization for full safety.
              const LOG_MAX = 2000;
              setLog((prev) => {
                const next = [
                  ...prev,
                  {
                    ts: String(evt.ts),
                    source: String(evt.source ?? stage),
                    agent: evt.agent as string | undefined,
                    level:
                      (evt.level as "info" | "warn" | "error" | "tool") ??
                      "info",
                    text,
                  },
                ];
                return next.length > LOG_MAX ? next.slice(-LOG_MAX) : next;
              });
              const progress = progressFromLogLine(text);
              if (progress) {
                setProject((prev) =>
                  prev.activeRun?.runId === run.id
                    ? {
                        ...prev,
                        activeRun: { ...prev.activeRun, ...progress },
                      }
                    : prev,
                );
              }
            } else if (evt.kind === "error") {
              const text = String(evt.message ?? "Run failed");
              setLog((prev) => {
                const next = [
                  ...prev,
                  {
                    ts: String(evt.ts),
                    source: String(evt.stage ?? stage),
                    level: "error" as const,
                    text,
                  },
                ];
                return next.length > 2000 ? next.slice(-2000) : next;
              });
            } else if (evt.kind === "plot.created") {
              // Live plot file watcher: a new plot file appeared on disk.
              void refreshPlots();
            } else if (evt.kind === "stage.heartbeat") {
              setProject((prev) =>
                prev.activeRun?.runId === run.id
                  ? {
                      ...prev,
                      activeRun: {
                        ...prev.activeRun,
                        step:
                          typeof evt.step === "number"
                            ? evt.step
                            : prev.activeRun.step,
                        totalSteps:
                          typeof evt.total_steps === "number"
                            ? evt.total_steps
                            : prev.activeRun.totalSteps,
                        attempt:
                          typeof evt.attempt === "number"
                            ? evt.attempt
                            : prev.activeRun.attempt,
                        totalAttempts:
                          typeof evt.total_attempts === "number"
                            ? evt.total_attempts
                            : prev.activeRun.totalAttempts,
                      },
                    }
                  : prev,
              );
            } else if (evt.kind === "code.execute") {
              // Iter-30: fan out to CodePane via codeEvents. Same ring-
              // buffer treatment as nodeEvents — bounded so a long run
              // can't accumulate unbounded source-string allocations.
              const entry = coerceCodeEvent(evt as RunEventCodeExecute);
              setCodeEvents((prev) => {
                const next = [...prev, entry];
                return next.length > CODE_EVENTS_MAX
                  ? next.slice(-CODE_EVENTS_MAX)
                  : next;
              });
            } else if (
              evt.kind === "node.entered" || evt.kind === "node.exited"
            ) {
              // Iter-28: AgentSwimlane consumer. Coerce ts to ms
              // (backend emits ISO-8601 strings; Date.parse handles
              // both string + number forms).
              const tsMs = (() => {
                const raw = evt.ts;
                if (typeof raw === "number") return raw;
                const parsed = Date.parse(String(raw));
                return Number.isFinite(parsed) ? parsed : Date.now();
              })();
              const entry: NodeEventEntry = {
                name: String((evt as { name?: unknown }).name ?? "unknown"),
                stage: (evt as { stage?: string }).stage,
                ts: tsMs,
                kind: evt.kind === "node.entered" ? "entered" : "exited",
                durationMs:
                  evt.kind === "node.exited"
                    ? (evt as { duration_ms?: number }).duration_ms
                    : undefined,
              };
              setNodeEvents((prev) => {
                const next = [...prev, entry];
                return next.length > NODE_EVENTS_MAX
                  ? next.slice(-NODE_EVENTS_MAX)
                  : next;
              });
            } else if (evt.kind === "stage.finished") {
              // Clear the run-id correlation header so post-run
              // requests (refresh, plot fetches) aren't tagged with
              // a stale run id.
              setActiveRunId(null);
              void refresh();
              void refreshPlots();
              if (stage === "results" && projectIdRef.current) {
                void refreshHistoricalResultsEvents(projectIdRef.current);
              }
            }
          },
        );
      } catch (e) {
        console.error("Failed to start run", e);
        throw e;
      }
    },
    [isLive, refresh, refreshHistoricalResultsEvents, refreshPlots],
  );

  const cancelRun = React.useCallback<ProjectState["cancelRun"]>(async () => {
    if (!isLive || !projectIdRef.current || !project.activeRun) return;
    const cancelledStage = project.activeRun.stage;
    await api.cancelRun(projectIdRef.current, project.activeRun.runId);
    setActiveRunId(null);
    sseUnsubRef.current?.();
    sseUnsubRef.current = null;
    setProject((prev) => {
      if (prev.activeRun?.stage !== cancelledStage) return prev;
      const currentStage = prev.stages[cancelledStage];
      return {
        ...prev,
        activeRun: null,
        stages: {
          ...prev.stages,
          [cancelledStage]: currentStage
            ? {
                ...currentStage,
                status: "empty",
                progressLabel: undefined,
              }
            : currentStage,
        },
      };
    });
    await refresh();
  }, [isLive, project.activeRun, refresh]);

  return {
    project,
    log,
    plots,
    nodeEvents,
    codeEvents,
    isLive,
    loading,
    capabilities: caps,
    startRun,
    cancelRun,
    selectProject,
    refresh,
    refreshPlots,
  };
}
