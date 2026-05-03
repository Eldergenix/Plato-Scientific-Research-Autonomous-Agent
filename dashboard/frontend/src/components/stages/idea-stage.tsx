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

      <IdeaSidePanel onRun={onRun} />
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

function IdeaSidePanel({ onRun }: { onRun?: () => void }) {
  // TODO: Phase 5 — these models will pass through to a real
  // api.startRun(projectId, "idea", { mode, models: { idea_maker: maker, idea_hater: hater, ... } })
  const [mode, setMode] = React.useState<"fast" | "cmbagent">("fast");
  const [iterations, setIterations] = React.useState(4);
  const [maker, setMaker] = React.useState("gpt-5");
  const [hater, setHater] = React.useState("o3-mini");
  const [planner, setPlanner] = React.useState("gpt-4.1");
  const [reviewer, setReviewer] = React.useState("o3-mini");
  const [orchestration, setOrchestration] = React.useState("gpt-4.1");
  const [formatter, setFormatter] = React.useState("o3-mini");

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

      <Button variant="primary" size="md" className="mt-4 w-full" onClick={onRun}>
        <Sparkles size={13} strokeWidth={1.5} />
        Generate new idea
      </Button>
      <Button variant="ghost" size="md" className="mt-2 w-full" onClick={onRun}>
        <RefreshCw size={12} strokeWidth={1.5} />
        Refine current
      </Button>

      <div className="mt-6 hairline-t pt-4">
        <h3 className="font-label">Run history</h3>
        {/* Iter-22: deleted the hardcoded "12m ago / yesterday / 2 days ago"
            mock list that misled users into thinking historical runs were
            being shown. Until ``.history/idea_*.md`` is exposed via a real
            endpoint, render an empty state pointing at the runs page
            (which DOES carry real history). */}
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
            No history captured yet. Past runs will appear here once the
            <code className="font-mono"> .history/idea_*.md</code> reader
            ships; meanwhile, see <code className="font-mono">/runs</code>
            for the full per-run manifest log.
          </p>
        </div>
      </div>
    </aside>
  );
}
