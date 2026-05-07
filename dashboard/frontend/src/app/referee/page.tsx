"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  RefreshCw,
  Save,
  Sparkles,
  Stamp,
} from "lucide-react";
import { DashboardShell } from "@/components/shell/dashboard-shell";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import {
  EMPTY_PROJECT,
  persistSelectedProjectId,
  pickPreferredProject,
} from "@/lib/use-project";
import type { Project } from "@/lib/types";
import { cn, formatDuration, formatRelativeTime } from "@/lib/utils";

interface ParsedScore {
  label: string;
  value: number | null;
}

const SCORE_LABELS = [
  "Originality",
  "Clarity",
  "Methodology",
  "Results",
  "Significance",
  "Overall",
];

function parseScores(markdown: string): ParsedScore[] {
  return SCORE_LABELS.map((label) => {
    const pattern = new RegExp(`${label}[^\\n\\d]{0,48}(10|[0-9](?:\\.[0-9])?)\\s*(?:/\\s*10)?`, "i");
    const match = markdown.match(pattern);
    const value = match ? Number(match[1]) : Number.NaN;
    return {
      label,
      value: Number.isFinite(value) ? value : null,
    };
  });
}

function parseSeverity(markdown: string): number | null {
  const match = markdown.match(/\bseverity\b[^\n0-3]{0,32}([0-3])\b/i);
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? value : null;
}

function averageScore(scores: ParsedScore[]): number | null {
  const values = scores
    .map((score) => score.value)
    .filter((value): value is number => value !== null);
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function updateProject(projects: Project[], next: Project): Project[] {
  const index = projects.findIndex((project) => project.id === next.id);
  if (index < 0) return [next, ...projects];
  return projects.map((project) => (project.id === next.id ? next : project));
}

export default function RefereePage() {
  return (
    <DashboardShell>
      <RefereeContent />
    </DashboardShell>
  );
}

function RefereeContent() {
  const [projects, setProjects] = React.useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = React.useState("");
  const [markdown, setMarkdown] = React.useState("");
  const [savedMarkdown, setSavedMarkdown] = React.useState("");
  const [origin, setOrigin] = React.useState<string | null>(null);
  const [loadingProjects, setLoadingProjects] = React.useState(true);
  const [loadingStage, setLoadingStage] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);

  const selectedProject =
    projects.find((project) => project.id === selectedProjectId) ?? null;
  const refereeStage = selectedProject?.stages.referee ?? EMPTY_PROJECT.stages.referee;
  const paperStage = selectedProject?.stages.paper ?? EMPTY_PROJECT.stages.paper;
  const canRunReferee = Boolean(selectedProject?.id) && paperStage.status === "done";
  const dirty = markdown !== savedMarkdown;
  const scores = React.useMemo(() => parseScores(markdown), [markdown]);
  const severity = React.useMemo(() => parseSeverity(markdown), [markdown]);
  const scoreAverage = React.useMemo(() => averageScore(scores), [scores]);

  const refreshProjects = React.useCallback(async () => {
    setLoadingProjects(true);
    setError(null);
    try {
      const nextProjects = await api.listProjects();
      setProjects(nextProjects);
      if (nextProjects.length === 0) {
        setSelectedProjectId("");
        return;
      }
      const preferred = pickPreferredProject(nextProjects);
      if (!preferred) return;
      setSelectedProjectId((current) => {
        const stillExists = nextProjects.some((project) => project.id === current);
        return stillExists ? current : preferred.id;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects.");
    } finally {
      setLoadingProjects(false);
    }
  }, []);

  React.useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  React.useEffect(() => {
    if (!selectedProjectId) {
      setMarkdown("");
      setSavedMarkdown("");
      setOrigin(null);
      return;
    }

    let cancelled = false;
    setLoadingStage(true);
    setError(null);
    api
      .readStage(selectedProjectId, "referee")
      .then((stage) => {
        if (cancelled) return;
        const nextMarkdown = stage?.markdown ?? "";
        setMarkdown(nextMarkdown);
        setSavedMarkdown(nextMarkdown);
        setOrigin(stage?.origin ?? null);
      })
      .catch((err) => {
        if (cancelled) return;
        setMarkdown("");
        setSavedMarkdown("");
        setOrigin(null);
        setError(err instanceof Error ? err.message : "Failed to load referee review.");
      })
      .finally(() => {
        if (!cancelled) setLoadingStage(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedProjectId]);

  const onSelectProject = React.useCallback((projectId: string) => {
    persistSelectedProjectId(projectId);
    setSelectedProjectId(projectId);
    setNotice(null);
    setError(null);
  }, []);

  const saveReview = React.useCallback(async () => {
    if (!selectedProjectId) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await api.writeStage(selectedProjectId, "referee", markdown);
      setSavedMarkdown(markdown);
      const latest = await api.getProject(selectedProjectId);
      setProjects((current) => updateProject(current, latest));
      setNotice("Referee review saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save referee review.");
    } finally {
      setSaving(false);
    }
  }, [markdown, selectedProjectId]);

  const runReferee = React.useCallback(async () => {
    if (!selectedProjectId || !canRunReferee) return;
    setRunning(true);
    setError(null);
    setNotice(null);
    try {
      const run = await api.startRun(selectedProjectId, "referee");
      const latest = await api.getProject(selectedProjectId);
      setProjects((current) => updateProject(current, latest));
      setNotice(`Referee run queued: ${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start referee run.");
    } finally {
      setRunning(false);
    }
  }, [canRunReferee, selectedProjectId]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <header className="hairline-b flex flex-none items-center justify-between gap-3 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Stamp size={17} strokeWidth={1.75} className="text-(--color-brand-hover)" />
          <div className="min-w-0">
            <h1 className="text-[18px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
              Referee
            </h1>
            <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
              Peer review, score extraction, and reviewer notes for the selected project.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void refreshProjects()}
            disabled={loadingProjects}
          >
            <RefreshCw size={13} className={cn(loadingProjects && "animate-spin")} />
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void runReferee()}
            disabled={!canRunReferee || running}
            title={!canRunReferee ? "Complete the paper stage before running referee." : undefined}
          >
            <Sparkles size={13} />
            Run referee
          </Button>
        </div>
      </header>

      <section className="hairline-b flex flex-none flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <label className="flex min-w-0 items-center gap-2 text-[12px] text-(--color-text-tertiary)">
          <span>Project</span>
          <select
            value={selectedProjectId}
            onChange={(event) => onSelectProject(event.target.value)}
            className="h-8 min-w-[240px] rounded-[6px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2 text-[12px] text-(--color-text-primary) focus:outline-none"
            disabled={loadingProjects || projects.length === 0}
          >
            {projects.length === 0 ? (
              <option value="">No projects</option>
            ) : (
              projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))
            )}
          </select>
        </label>

        <div className="flex flex-wrap gap-2">
          <StagePill label="Paper" value={paperStage.status} />
          <StagePill label="Referee" value={refereeStage.status} />
          <StagePill
            label="Origin"
            value={origin ?? refereeStage.origin ?? "none"}
          />
          <StagePill
            label="Updated"
            value={refereeStage.lastRunAt ? formatRelativeTime(refereeStage.lastRunAt) : "never"}
          />
        </div>
      </section>

      {error ? (
        <Banner tone="error" message={error} />
      ) : notice ? (
        <Banner tone="success" message={notice} />
      ) : !canRunReferee && selectedProject ? (
        <Banner
          tone="warning"
          message="Complete the paper stage before queueing a referee run."
        />
      ) : null}

      <section className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-y-auto p-4 xl:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col gap-3">
          <div className="surface-linear-card p-3">
            <div className="flex items-center gap-2">
              <FileText size={14} className="text-(--color-text-tertiary)" />
              <h2 className="text-[13px] font-medium text-(--color-text-primary-strong)">
                Review signal
              </h2>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <ScoreMetric
                label="Average"
                value={scoreAverage === null ? "n/a" : scoreAverage.toFixed(1)}
              />
              <ScoreMetric
                label="Severity"
                value={severity === null ? "n/a" : String(severity)}
                tone={severity !== null && severity >= 2 ? "danger" : "default"}
              />
            </div>
            <div className="mt-3 space-y-2">
              {scores.map((score) => (
                <ScoreRow key={score.label} score={score} />
              ))}
            </div>
          </div>

          <div className="surface-linear-card p-3 text-[12px] text-(--color-text-tertiary)">
            <h2 className="text-[13px] font-medium text-(--color-text-primary-strong)">
              Inputs
            </h2>
            <dl className="mt-3 space-y-2">
              <DetailRow label="Project" value={selectedProject?.name ?? "None"} />
              <DetailRow label="Paper status" value={paperStage.status} />
              <DetailRow
                label="Referee model"
                value={refereeStage.model ?? "Not recorded"}
              />
              <DetailRow
                label="Duration"
                value={refereeStage.durationMs ? formatDuration(refereeStage.durationMs) : "n/a"}
              />
            </dl>
            <Button asChild variant="ghost" size="sm" className="mt-3 w-full">
              <Link href="/">Open stages</Link>
            </Button>
          </div>
        </aside>

        <div className="grid min-h-[640px] grid-cols-1 gap-3 xl:grid-cols-2">
          <section className="surface-linear-card flex min-h-0 flex-col overflow-hidden">
            <div className="hairline-b flex h-10 flex-none items-center justify-between px-3">
              <h2 className="text-[13px] font-medium text-(--color-text-primary-strong)">
                Referee markdown
              </h2>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void saveReview()}
                disabled={!selectedProjectId || !dirty || saving}
              >
                <Save size={13} />
                Save
              </Button>
            </div>
            {loadingStage ? (
              <div className="m-3 h-72 animate-shimmer rounded-[8px]" />
            ) : (
              <textarea
                value={markdown}
                onChange={(event) => setMarkdown(event.target.value)}
                aria-label="Referee markdown"
                spellCheck
                className="min-h-0 flex-1 resize-none bg-transparent p-3 font-mono text-[12px] leading-6 text-(--color-text-primary) outline-none placeholder:text-(--color-text-quaternary)"
                placeholder="Run the referee stage or write reviewer notes here."
              />
            )}
          </section>

          <section className="surface-linear-card flex min-h-0 flex-col overflow-hidden">
            <div className="hairline-b flex h-10 flex-none items-center justify-between px-3">
              <h2 className="text-[13px] font-medium text-(--color-text-primary-strong)">
                Review preview
              </h2>
              {dirty ? (
                <span className="font-mono text-[11px] text-(--color-status-amber)">
                  unsaved
                </span>
              ) : (
                <span className="font-mono text-[11px] text-(--color-text-quaternary)">
                  saved
                </span>
              )}
            </div>
            <MarkdownPreview markdown={markdown} />
          </section>
        </div>
      </section>
    </div>
  );
}

function StagePill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex h-7 items-center gap-1.5 rounded-full border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2.5 text-[11px]">
      <span className="text-(--color-text-quaternary)">{label}</span>
      <span className="font-mono text-(--color-text-secondary-spec)">{value}</span>
    </span>
  );
}

function ScoreMetric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "danger";
}) {
  return (
    <div className="rounded-[8px] border border-(--color-border-card) bg-(--color-bg-page) px-3 py-2">
      <div className="text-[11px] uppercase tracking-[0.04em] text-(--color-text-quaternary)">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 font-mono text-[20px] text-(--color-text-primary-strong)",
          tone === "danger" && "text-(--color-status-red-spec)",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function ScoreRow({ score }: { score: ParsedScore }) {
  const pct = score.value === null ? 0 : Math.max(0, Math.min(100, score.value * 10));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-[12px]">
        <span className="text-(--color-text-secondary-spec)">{score.label}</span>
        <span className="font-mono text-(--color-text-tertiary)">
          {score.value === null ? "n/a" : `${score.value}/10`}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-(--color-bg-pill-inactive)">
        <div
          className="h-full rounded-full bg-(--color-brand-hover)"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-(--color-text-quaternary)">{label}</dt>
      <dd className="min-w-0 text-right text-(--color-text-secondary-spec)">
        {value}
      </dd>
    </div>
  );
}

function Banner({ tone, message }: { tone: "error" | "success" | "warning"; message: string }) {
  const Icon = tone === "success" ? CheckCircle2 : AlertTriangle;
  return (
    <div
      className={cn(
        "mx-4 mt-3 flex flex-none items-center gap-2 rounded-[8px] border px-3 py-2 text-[12px]",
        tone === "success" && "border-(--color-status-green)/30 text-(--color-status-green)",
        tone === "warning" && "border-(--color-status-amber-spec) text-(--color-status-amber-spec)",
        tone === "error" && "border-(--color-status-red)/30 text-(--color-status-red)",
      )}
    >
      <Icon size={13} />
      <span>{message}</span>
    </div>
  );
}

function MarkdownPreview({ markdown }: { markdown: string }) {
  const trimmed = markdown.trim();
  if (!trimmed) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-center text-[13px] text-(--color-text-tertiary)">
        No referee review has been written yet.
      </div>
    );
  }

  const blocks = trimmed.split(/\n{2,}/);
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-2xl space-y-3 text-[13px] leading-6 text-(--color-text-secondary-spec)">
        {blocks.map((block, index) => (
          <PreviewBlock key={`${index}-${block.slice(0, 24)}`} block={block} />
        ))}
      </div>
    </div>
  );
}

function PreviewBlock({ block }: { block: string }) {
  const text = block.trim();
  if (text.startsWith("#")) {
    const level = text.match(/^#+/)?.[0].length ?? 1;
    const label = text.replace(/^#+\s*/, "");
    return (
      <h3
        className={cn(
          "font-medium text-(--color-text-primary-strong)",
          level <= 1 ? "text-[18px]" : "text-[15px]",
        )}
      >
        {label}
      </h3>
    );
  }

  const lines = text.split("\n");
  if (lines.every((line) => /^\s*[-*]\s+/.test(line))) {
    return (
      <ul className="list-disc space-y-1 pl-5">
        {lines.map((line, index) => (
          <li key={`${index}-${line.slice(0, 16)}`}>{line.replace(/^\s*[-*]\s+/, "")}</li>
        ))}
      </ul>
    );
  }

  return <p className="whitespace-pre-wrap">{text}</p>;
}
