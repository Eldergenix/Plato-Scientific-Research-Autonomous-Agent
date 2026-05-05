"use client";

import * as React from "react";
import { Lightbulb, Loader2, RefreshCw, Sparkles, Edit3, History, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { ModelPicker } from "@/components/ui/model-picker";
import { api } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";

interface Turn {
  agent: "idea_maker" | "idea_hater";
  text: string;
  ts: string;
}

// Iter-22: deleted the hardcoded SAMPLE_TURNS GW231123 ringdown narrative
// that used to ship as the agent transcript for every project (regardless
// of domain or whether anything had actually run). The transcript pane
// now renders an honest empty state until a future iteration plumbs in
// the real ``<stage>_generation_output/idea.log`` reader.
//
// When that reader lands, it should populate a ``Turn[]`` and the
// ``TranscriptPane`` component below will render it without further
// changes.

export interface IdeaStageProps {
  projectId?: string;
  origin?: "ai" | "edited";
  lastEditedAt?: string;
  model?: string;
  onRun?: () => void;
}

export function IdeaStage({
  projectId = "demo",
  origin,
  lastEditedAt,
  model,
  onRun,
}: IdeaStageProps = {}) {
  const [idea, setIdea] = React.useState<string>("");
  const [savedIdea, setSavedIdea] = React.useState<string>("");
  const [loading, setLoading] = React.useState<boolean>(true);
  const [editing, setEditing] = React.useState<boolean>(false);
  const [saving, setSaving] = React.useState<boolean>(false);
  const [liveOrigin, setLiveOrigin] = React.useState<"ai" | "edited" | undefined>(origin);
  const [liveEditedAt, setLiveEditedAt] = React.useState<string | undefined>(lastEditedAt);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const r = await api.readStage(projectId, "idea");
        if (cancelled) return;
        const md = r?.markdown ?? "";
        setIdea(md);
        setSavedIdea(md);
        if (r?.origin === "ai" || r?.origin === "edited") {
          setLiveOrigin(r.origin);
        }
      } catch {
        // Backend offline — show empty state.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const handleSave = React.useCallback(async () => {
    setSaving(true);
    try {
      await api.writeStage(projectId, "idea", idea);
      setSavedIdea(idea);
      setEditing(false);
      setLiveOrigin("edited");
      setLiveEditedAt(new Date().toISOString());
    } catch (err) {
      console.error("Failed to save idea", err);
    } finally {
      setSaving(false);
    }
  }, [projectId, idea]);

  const handleCancelEdit = React.useCallback(() => {
    setIdea(savedIdea);
    setEditing(false);
  }, [savedIdea]);

  const hasIdea = savedIdea.trim().length > 0;

  return (
    <div className="flex h-full">
      <main className="flex-1 overflow-auto">
        <div className="px-6 pt-6 pb-4 hairline-b flex items-baseline gap-3">
          <Lightbulb size={20} strokeWidth={1.5} className="text-(--color-brand-hover)" />
          <h2 className="font-h1 tracking-[-0.704px]">Research idea</h2>
          <IdeaOriginPill
            origin={liveOrigin}
            model={model}
            lastEditedAt={liveEditedAt}
            saving={saving}
          />
          {editing ? (
            <>
              <Button
                variant="primary"
                size="sm"
                className="ml-auto"
                disabled={saving || idea === savedIdea}
                onClick={handleSave}
              >
                {saving ? (
                  <Loader2 size={12} strokeWidth={1.5} className="animate-spin" />
                ) : (
                  <Save size={12} strokeWidth={1.5} />
                )}
                Save
              </Button>
              <Button variant="ghost" size="sm" onClick={handleCancelEdit} disabled={saving}>
                <X size={12} strokeWidth={1.5} />
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto"
                onClick={() => setEditing(true)}
                disabled={loading}
              >
                <Edit3 size={12} strokeWidth={1.5} />
                Edit
              </Button>
              <Button variant="ghost" size="sm">
                <History size={12} strokeWidth={1.5} />
                History
              </Button>
            </>
          )}
        </div>

        <div className="grid grid-cols-2 gap-px bg-(--color-border-standard) min-h-[60vh]">
          <section className="bg-(--color-bg-marketing) p-6 overflow-auto">
            <h3 className="font-label">Final idea</h3>
            {loading ? (
              <div className="mt-3 h-64 surface-card animate-shimmer" aria-label="Loading idea" />
            ) : editing ? (
              <textarea
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                spellCheck={false}
                className="mt-3 w-full min-h-[60vh] surface-card p-3 text-[13px] leading-[1.6] font-mono-body text-(--color-text-primary) resize-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-interactive)"
              />
            ) : hasIdea ? (
              <pre className="mt-3 whitespace-pre-wrap text-[13.5px] leading-[1.65] font-sans text-(--color-text-primary)">
                {savedIdea}
              </pre>
            ) : (
              <EmptyIdeaHint onRun={onRun} />
            )}
          </section>

          <TranscriptPane turns={[]} />
        </div>
      </main>

      <IdeaSidePanel projectId={projectId} onRun={onRun} />
    </div>
  );
}

function IdeaOriginPill({
  origin,
  model,
  lastEditedAt,
  saving,
}: {
  origin?: "ai" | "edited";
  model?: string;
  lastEditedAt?: string;
  saving: boolean;
}) {
  if (saving) {
    return (
      <Pill tone="indigo" className="gap-1">
        <Loader2 size={10} strokeWidth={1.5} className="animate-spin" />
        Saving…
      </Pill>
    );
  }
  if (!origin) {
    return (
      <Pill tone="neutral" className="gap-1">
        Empty
      </Pill>
    );
  }
  const tone = origin === "ai" ? "indigo" : "green";
  const label = origin === "ai" ? "AI" : "Edited";
  const parts = [label];
  if (model && origin === "ai") parts.push(model);
  if (lastEditedAt) parts.push(formatRelativeTime(lastEditedAt));
  return (
    <Pill tone={tone} className="gap-1">
      {parts.join(" · ")}
    </Pill>
  );
}

function TranscriptPane({ turns }: { turns: Turn[] }) {
  // Iter-22: shipped as an honest empty state. The original
  // implementation hardcoded SAMPLE_TURNS — a 5-turn GW231123 ringdown
  // narrative — and rendered it for every project. Now that the data
  // source isn't wired up yet (see TODO above), we render an empty
  // state instead of fake data. When ``<stage>_generation_output/idea.log``
  // becomes available, the parent will pass a populated ``turns`` and
  // this component renders them without further changes.
  if (turns.length === 0) {
    return (
      <section
        className="bg-(--color-bg-marketing) p-6 overflow-auto"
        data-testid="idea-transcript-pane"
      >
        <h3 className="font-label flex items-center gap-2">
          <span>Agent transcript</span>
          <span className="text-[11px] text-(--color-text-quaternary) normal-case font-mono">
            no transcript yet
          </span>
        </h3>
        <div className="mt-6 surface-card border-dashed border-(--color-border-standard) p-5 text-center">
          <Sparkles
            size={20}
            strokeWidth={1.5}
            className="mx-auto text-(--color-text-quaternary)"
          />
          <div className="mt-2 text-[13px] font-medium text-(--color-text-primary)">
            No agent transcript captured
          </div>
          <p className="mt-1 text-[12px] text-(--color-text-tertiary) leading-[1.55] max-w-sm mx-auto">
            Run idea generation to see the live debate between the
            idea-maker and idea-hater agents.
          </p>
        </div>
      </section>
    );
  }
  return (
    <section
      className="bg-(--color-bg-marketing) p-6 overflow-auto"
      data-testid="idea-transcript-pane"
    >
      <h3 className="font-label flex items-center gap-2">
        <span>Agent transcript</span>
        <span className="text-[11px] text-(--color-text-quaternary) normal-case font-mono">
          {turns.length} iterations
        </span>
      </h3>
      <ol className="mt-3 space-y-3">
        {turns.map((t, i) => (
          <li
            key={i}
            className={cn(
              "surface-card p-3",
              t.agent === "idea_maker"
                ? "border-(--color-brand-indigo)/20"
                : "border-(--color-status-amber)/20",
            )}
          >
            <div className="flex items-baseline gap-2 mb-1.5">
              <span
                className={cn(
                  "text-[11px] font-mono font-medium",
                  t.agent === "idea_maker"
                    ? "text-(--color-brand-hover)"
                    : "text-(--color-status-amber)",
                )}
              >
                {t.agent}
              </span>
              <span className="text-[11px] text-(--color-text-quaternary) tabular-nums">
                {t.ts}
              </span>
            </div>
            <p className="text-[12.5px] leading-[1.6] text-(--color-text-secondary)">
              {t.text}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}


function EmptyIdeaHint({ onRun }: { onRun?: () => void }) {
  return (
    <div className="mt-6 surface-card border-dashed border-(--color-border-standard) p-5 text-center">
      <Lightbulb size={20} strokeWidth={1.5} className="mx-auto text-(--color-text-quaternary)" />
      <div className="mt-2 text-[13px] font-medium text-(--color-text-primary)">
        No idea yet
      </div>
      <p className="mt-1 text-[12px] text-(--color-text-tertiary) leading-[1.55] max-w-sm mx-auto">
        Run the idea generator to seed a research direction, or click Edit to write one yourself.
      </p>
      {onRun && (
        <Button variant="primary" size="sm" className="mt-3" onClick={onRun}>
          <Sparkles size={12} strokeWidth={1.5} />
          Run idea generation
        </Button>
      )}
    </div>
  );
}

function IdeaSidePanel({
  projectId,
  onRun,
}: {
  projectId?: string;
  onRun?: () => void;
}) {
  // Iter-23: 7 model-picker selects (+ mode + iterations) now thread
  // through to ``api.startRun(projectId, "idea", { mode, models })``
  // when ``projectId`` is set. Falls back to the legacy no-op
  // ``onRun()`` callback otherwise (e.g. when rendered from the empty
  // EMPTY_PROJECT first-paint state where no project exists yet).
  const [mode, setMode] = React.useState<"fast" | "cmbagent">("fast");
  const [iterations, setIterations] = React.useState(4);
  const [maker, setMaker] = React.useState("gpt-5");
  const [hater, setHater] = React.useState("o3-mini");
  const [planner, setPlanner] = React.useState("gpt-4.1");
  const [reviewer, setReviewer] = React.useState("o3-mini");
  const [orchestration, setOrchestration] = React.useState("gpt-4.1");
  const [formatter, setFormatter] = React.useState("o3-mini");
  const [submitting, setSubmitting] = React.useState(false);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  // Iter-23: real run-history list driven by GET /projects/{pid}/idea_history.
  const [history, setHistory] = React.useState<
    import("@/lib/api").IdeaHistoryResponse["entries"] | null
  >(null);
  const [historyError, setHistoryError] = React.useState<string | null>(null);

  const refreshHistory = React.useCallback(async () => {
    if (!projectId) {
      setHistory(null);
      return;
    }
    try {
      const r = await api.listIdeaHistory(projectId);
      setHistory(r.entries);
      setHistoryError(null);
    } catch (e: unknown) {
      setHistoryError(e instanceof Error ? e.message : "Failed to load history");
    }
  }, [projectId]);

  React.useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  const handleRun = React.useCallback(async () => {
    setSubmitError(null);
    if (projectId) {
      const models: Record<string, string> = {
        idea_maker: maker,
        idea_hater: hater,
        planner,
        plan_reviewer: reviewer,
        orchestration,
        formatter,
      };
      try {
        setSubmitting(true);
        // Iter-3: forward the iteration budget the user picked. Backend
        // StageRunRequest accepts the field; previously it was collected
        // and dropped, making the +/- control decorative.
        await api.startRun(projectId, "idea", { mode, models, iterations });
        // Fire the legacy callback too for parents that listen for
        // post-submit refreshes (e.g. switching panes).
        onRun?.();
        // Refresh history once the run is acknowledged so the user
        // sees their new entry pending in the list.
        void refreshHistory();
      } catch (e: unknown) {
        setSubmitError(
          e instanceof Error ? e.message : "Failed to start run",
        );
      } finally {
        setSubmitting(false);
      }
    } else {
      // Without projectId we can't dispatch — preserve the original
      // no-op behaviour so the button still feels responsive.
      onRun?.();
    }
  }, [
    projectId,
    mode,
    maker,
    hater,
    planner,
    reviewer,
    orchestration,
    formatter,
    iterations,
    onRun,
    refreshHistory,
  ]);

  return (
    <aside className="w-[320px] hairline-l bg-(--color-bg-marketing) p-4 overflow-auto">
      <h3 className="font-label">Run controls</h3>

      <div className="mt-3 space-y-3">
        <div>
          <span className="text-[11px] uppercase tracking-wider text-(--color-text-quaternary) font-medium">
            Mode
          </span>
          <div className="mt-1 grid grid-cols-2 gap-1 surface-ghost p-1">
            <button
              type="button"
              onClick={() => setMode("fast")}
              className={cn(
                "h-7 rounded-[4px] text-[12px] font-medium transition-colors",
                mode === "fast"
                  ? "bg-(--color-ghost-bg-hover) text-(--color-text-primary)"
                  : "text-(--color-text-tertiary) hover:text-(--color-text-primary)",
              )}
            >
              fast
            </button>
            <button
              type="button"
              onClick={() => setMode("cmbagent")}
              className={cn(
                "h-7 rounded-[4px] text-[12px] font-medium transition-colors",
                mode === "cmbagent"
                  ? "bg-(--color-ghost-bg-hover) text-(--color-text-primary)"
                  : "text-(--color-text-tertiary) hover:text-(--color-text-primary)",
              )}
            >
              cmbagent
            </button>
          </div>
        </div>

        <div>
          <span className="text-[11px] uppercase tracking-wider text-(--color-text-quaternary) font-medium">
            Iterations
          </span>
          <input
            type="number"
            min={1}
            max={20}
            value={iterations}
            onChange={(e) => setIterations(Math.max(1, Math.min(20, parseInt(e.target.value, 10) || 1)))}
            className="mt-1 w-full surface-ghost h-8 px-2 text-[12px] font-mono text-(--color-text-primary) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-interactive)"
          />
        </div>

        <ModelPicker label="Idea maker" value={maker} onChange={setMaker} recommendedFor="idea" size="sm" />
        <ModelPicker label="Idea hater" value={hater} onChange={setHater} size="sm" />
      </div>

      <details className="mt-4 group">
        <summary className="text-[11px] uppercase tracking-wider text-(--color-text-quaternary) font-medium cursor-pointer hover:text-(--color-text-tertiary)">
          Advanced
        </summary>
        <div className="mt-2 space-y-2">
          <ModelPicker label="Planner" value={planner} onChange={setPlanner} size="sm" />
          <ModelPicker label="Plan reviewer" value={reviewer} onChange={setReviewer} size="sm" />
          <ModelPicker label="Orchestration" value={orchestration} onChange={setOrchestration} size="sm" />
          <ModelPicker label="Formatter" value={formatter} onChange={setFormatter} size="sm" />
        </div>
      </details>

      <Button
        variant="primary"
        size="md"
        className="mt-4 w-full"
        onClick={handleRun}
        disabled={submitting}
        data-testid="idea-generate-button"
      >
        {submitting ? (
          <Loader2 size={13} strokeWidth={1.5} className="animate-spin" />
        ) : (
          <Sparkles size={13} strokeWidth={1.5} />
        )}
        Generate new idea
      </Button>
      <Button
        variant="ghost"
        size="md"
        className="mt-2 w-full"
        onClick={handleRun}
        disabled={submitting}
      >
        <RefreshCw size={12} strokeWidth={1.5} />
        Refine current
      </Button>
      {submitError ? (
        <p
          className="mt-2 text-[11px] text-(--color-status-red)"
          data-testid="idea-submit-error"
        >
          {submitError}
        </p>
      ) : null}

      <div className="mt-6 hairline-t pt-4">
        <h3 className="font-label">Run history</h3>
        {/* Iter-23: history is populated from GET /idea_history. When no
            past runs exist (or the project hasn't loaded yet) we render
            the empty state. Errors fall through to the empty state too;
            they're surfaced inline so a transient backend hiccup
            doesn't blank the panel. */}
        {history && history.length > 0 ? (
          <ul
            className="mt-2 space-y-1"
            data-testid="idea-history-list"
          >
            {history.map((r) => {
              const dur =
                r.duration_seconds !== null && r.duration_seconds !== undefined
                  ? formatRelativeDuration(r.duration_seconds)
                  : "—";
              const model =
                r.models["idea_maker"] ||
                r.models["idea"] ||
                Object.values(r.models)[0] ||
                r.workflow;
              return (
                <li
                  key={r.run_id}
                  className="surface-ghost px-2 py-1.5 text-[11.5px]"
                  data-testid={`idea-history-row-${r.run_id}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-(--color-text-primary)">
                      {r.started_at
                        ? formatRelativeTime(r.started_at)
                        : "unknown"}
                    </span>
                    <span className="font-mono text-(--color-text-quaternary) tabular-nums">
                      {dur}
                    </span>
                  </div>
                  <span className="text-(--color-text-tertiary) font-mono text-[10.5px]">
                    {model} · {r.status}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <div
            className="mt-2 surface-card border-dashed border-(--color-border-standard) px-3 py-3 text-center"
            data-testid="idea-history-empty"
          >
            <History
              size={16}
              strokeWidth={1.5}
              className="mx-auto text-(--color-text-quaternary)"
            />
            <p className="mt-1 text-[11.5px] text-(--color-text-tertiary) leading-[1.5]">
              No idea-generation runs yet. Click
              <strong> Generate new idea </strong> above to start your
              first one — it'll appear here automatically when the run
              kicks off. See <code className="font-mono">/runs</code>
              for the full per-run manifest log.
            </p>
            {historyError ? (
              <p
                className="mt-2 text-[11px] text-(--color-status-amber)"
                data-testid="idea-history-error"
              >
                {historyError}
              </p>
            ) : null}
          </div>
        )}
      </div>
    </aside>
  );
}


/** Iter-23: tiny duration formatter used by the run-history list.
 * Renders ``Ns`` / ``Nm Ss`` / ``Nh Mm`` for sub-min / sub-hour /
 * multi-hour spans. Intentionally compact — the side panel column is
 * narrow, so we avoid the ``durationFormat`` helper from utils which
 * pads to "11m 04s" form.
 */
function formatRelativeDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remSeconds = Math.round(seconds - minutes * 60);
  if (minutes < 60) return `${minutes}m ${remSeconds.toString().padStart(2, "0")}s`;
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes - hours * 60;
  return `${hours}h ${remMinutes.toString().padStart(2, "0")}m`;
}
