"use client";

import * as React from "react";
import { api } from "./api";
import { SAMPLE_LOG, SAMPLE_PROJECT } from "./sample-data";
import type { LogLine, Project, StageId } from "./types";

export interface PlotEntry {
  name: string;
  url: string;
}

interface ProjectState {
  project: Project;
  log: LogLine[];
  plots: PlotEntry[];
  isLive: boolean; // true when fetched from API; false when running off sample
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

export function useProject(): ProjectState {
  const [project, setProject] = React.useState<Project>(SAMPLE_PROJECT);
  const [log, setLog] = React.useState<LogLine[]>(SAMPLE_LOG);
  const [plots, setPlots] = React.useState<PlotEntry[]>([]);
  const [isLive, setIsLive] = React.useState(false);
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
        // Backend offline — keep showing the rich sample data so the design
        // remains demo-able as a static page (HuggingFace Spaces fallback).
        setIsLive(false);
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
        sseUnsubRef.current?.();
        sseUnsubRef.current = api.subscribeRunEvents(
          projectIdRef.current,
          run.id,
          (evt) => {
            if (evt.kind === "log.line") {
              setLog((prev) => [
                ...prev,
                {
                  ts: String(evt.ts),
                  source: String(evt.source ?? stage),
                  agent: evt.agent as string | undefined,
                  level: (evt.level as "info" | "warn" | "error" | "tool") ?? "info",
                  text: String(evt.text ?? ""),
                },
              ]);
            } else if (evt.kind === "plot.created") {
              // Live plot file watcher: a new plot file appeared on disk.
              void refreshPlots();
            } else if (evt.kind === "stage.finished") {
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
    isLive,
    capabilities: caps,
    startRun,
    cancelRun,
    refresh,
    refreshPlots,
  };
}
