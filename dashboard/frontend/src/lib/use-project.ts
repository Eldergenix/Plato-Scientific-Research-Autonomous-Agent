"use client";

import * as React from "react";
import { api, setActiveRunId } from "./api";
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
  isLive: boolean; // true when fetched from API; false when offline / pre-bootstrap
  loading: boolean; // true until the first ``getProject`` resolves (or fails)
  capabilities: {
    is_demo: boolean;
    allowed_stages: StageId[];
    notes: string[];
  } | null;
  startRun: (stage: StageId, body?: { mode?: "fast" | "cmbagent" }) => Promise<void>;
  cancelRun: () => Promise<void>;
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

export function useProject(): ProjectState {
  const [project, setProject] = React.useState<Project>(EMPTY_PROJECT);
  const [log, setLog] = React.useState<LogLine[]>([]);
  const [plots, setPlots] = React.useState<PlotEntry[]>([]);
  const [nodeEvents, setNodeEvents] = React.useState<NodeEventEntry[]>([]);
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
        `${process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1"}/projects/${projectIdRef.current}/plots`,
      );
      if (!r.ok) return;
      const list = (await r.json()) as PlotEntry[];
      setPlots(list);
    } catch {
      // ignore
    }
  }, []);

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
          active = list[list.length - 1];
        } else {
          active = await api.createProject("New project");
        }
        if (cancelled) return;
        projectIdRef.current = active.id;
        setProject(active);
        setLog([]);
        setIsLive(true);
        // Initial plots fetch.
        try {
          const plotsRes = await fetch(
            `${process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1"}/projects/${active.id}/plots`,
          );
          if (plotsRes.ok) {
            const list = (await plotsRes.json()) as PlotEntry[];
            if (!cancelled) setPlots(list);
          }
        } catch {
          // ignore
        }
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
  }, []);

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
        sseUnsubRef.current?.();
        sseUnsubRef.current = api.subscribeRunEvents(
          projectIdRef.current,
          run.id,
          (evt) => {
            if (evt.kind === "log.line") {
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
                    text: String(evt.text ?? ""),
                  },
                ];
                return next.length > LOG_MAX ? next.slice(-LOG_MAX) : next;
              });
            } else if (evt.kind === "plot.created") {
              // Live plot file watcher: a new plot file appeared on disk.
              void refreshPlots();
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
            }
          },
        );
      } catch (e) {
        console.error("Failed to start run", e);
      }
    },
    [isLive, refresh, refreshPlots],
  );

  const cancelRun = React.useCallback<ProjectState["cancelRun"]>(async () => {
    if (!isLive || !projectIdRef.current || !project.activeRun) return;
    await api.cancelRun(projectIdRef.current, project.activeRun.runId);
  }, [isLive, project.activeRun]);

  return {
    project,
    log,
    plots,
    nodeEvents,
    isLive,
    loading,
    capabilities: caps,
    startRun,
    cancelRun,
    refresh,
    refreshPlots,
  };
}
