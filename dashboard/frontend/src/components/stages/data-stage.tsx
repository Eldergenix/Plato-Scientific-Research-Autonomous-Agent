"use client";

import * as React from "react";
import { FileSearch, Loader2, Save, Sparkles, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { api } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";

const AUTOSAVE_DEBOUNCE_MS = 1500;

export interface DataStageProps {
  projectId?: string;
  initialMarkdown?: string;
  origin?: "ai" | "edited";
  lastEditedAt?: string;
  onSaved?: () => void;
}

export function DataStage({
  projectId = "demo",
  initialMarkdown,
  origin,
  lastEditedAt,
  onSaved,
}: DataStageProps = {}) {
  const [content, setContent] = React.useState<string>(initialMarkdown ?? "");
  const [savedContent, setSavedContent] = React.useState<string>(initialMarkdown ?? "");
  const [loading, setLoading] = React.useState<boolean>(true);
  const [saving, setSaving] = React.useState<boolean>(false);
  const [enhanceToast, setEnhanceToast] = React.useState<boolean>(false);
  const [liveOrigin, setLiveOrigin] = React.useState<"ai" | "edited" | undefined>(origin);
  const [liveEditedAt, setLiveEditedAt] = React.useState<string | undefined>(lastEditedAt);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const dirty = content !== savedContent;

  // Mount: fetch existing data description.
  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const r = await api.readStage(projectId, "data");
        if (cancelled) return;
        const md = r?.markdown ?? "";
        setContent(md);
        setSavedContent(md);
        if (r?.origin === "ai" || r?.origin === "edited") {
          setLiveOrigin(r.origin);
        }
      } catch {
        // Backend offline — remain empty so the empty state shows.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const performSave = React.useCallback(
    async (next: string) => {
      if (next === savedContent) return;
      setSaving(true);
      try {
        await api.writeStage(projectId, "data", next);
        setSavedContent(next);
        setLiveOrigin("edited");
        setLiveEditedAt(new Date().toISOString());
        onSaved?.();
      } catch (err) {
        console.error("Failed to save data description", err);
      } finally {
        setSaving(false);
      }
    },
    [projectId, savedContent, onSaved],
  );

  // Debounced auto-save: 1500ms after the last keystroke, persist.
  React.useEffect(() => {
    if (!dirty || loading) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void performSave(content);
    }, AUTOSAVE_DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [content, dirty, loading, performSave]);

  const handleManualSave = React.useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    void performSave(content);
  }, [content, performSave]);

  const handleEnhanceClick = React.useCallback(() => {
    setEnhanceToast(true);
    if (toastRef.current) clearTimeout(toastRef.current);
    toastRef.current = setTimeout(() => setEnhanceToast(false), 2400);
  }, []);

  const showEmptyHint = !loading && content.length === 0;

  return (
    <div className="flex h-full">
      <main className="flex-1 overflow-auto">
        <div className="px-6 pt-6 pb-4 hairline-b">
          <div className="flex items-baseline gap-3">
            <h2 className="font-h1 tracking-[-0.704px]">Data description</h2>
            <OriginPill origin={liveOrigin} lastEditedAt={liveEditedAt} saving={saving} dirty={dirty} />
          </div>
          <p className="mt-1.5 text-[13px] text-(--color-text-tertiary)">
            What data and tools should the agents use? This becomes the seed for idea, method,
            and results generation.
          </p>
        </div>

        <div className="px-6 py-4 relative">
          {loading ? (
            <div
              className="w-full min-h-[420px] surface-card animate-shimmer"
              aria-label="Loading data description"
            />
          ) : showEmptyHint ? (
            <EmptyDataHint
              value={content}
              onChange={setContent}
            />
          ) : (
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              spellCheck={false}
              className="w-full min-h-[420px] surface-card p-4 text-[13px] leading-[1.6] font-mono-body text-(--color-text-primary) resize-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-interactive)"
            />
          )}
        </div>

        <div className="px-6 pb-6 flex items-center gap-3">
          <Button variant="ghost" size="md">
            <FileSearch size={13} strokeWidth={1.5} />
            Validate paths
          </Button>
          <Button variant="ghost" size="md">
            <Upload size={13} strokeWidth={1.5} />
            Attach data files
          </Button>
          <Button
            variant="primary"
            size="md"
            className="ml-auto"
            disabled={!dirty || saving || loading}
            onClick={handleManualSave}
          >
            {saving ? (
              <Loader2 size={13} strokeWidth={1.5} className="animate-spin" />
            ) : (
              <Save size={13} strokeWidth={1.5} />
            )}
            {saving ? "Saving…" : dirty ? "Save" : "Saved"}
          </Button>
        </div>
      </main>

      <SidePanel onEnhanceClick={handleEnhanceClick} enhanceToast={enhanceToast} />
    </div>
  );
}

function OriginPill({
  origin,
  lastEditedAt,
  saving,
  dirty,
}: {
  origin?: "ai" | "edited";
  lastEditedAt?: string;
  saving: boolean;
  dirty: boolean;
}) {
  if (saving) {
    return (
      <Pill tone="indigo" className="gap-1">
        <Loader2 size={10} strokeWidth={1.5} className="animate-spin" />
        Saving…
      </Pill>
    );
  }
  if (dirty) {
    return (
      <Pill tone="amber" className="gap-1">
        Unsaved changes
      </Pill>
    );
  }
  const label = origin === "ai" ? "AI" : origin === "edited" ? "Edited" : "Empty";
  const tone = origin === "ai" ? "indigo" : origin === "edited" ? "green" : "neutral";
  const ts = lastEditedAt ? ` · ${formatRelativeTime(lastEditedAt)}` : "";
  return (
    <Pill tone={tone} className="gap-1">
      {label}
      {ts}
    </Pill>
  );
}

function EmptyDataHint({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="relative">
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center">
        <div className="surface-card border-dashed border-(--color-border-standard) px-5 py-4 max-w-md w-full pointer-events-auto">
          <div className="text-[13px] font-medium text-(--color-text-primary)">
            Describe your data and tools
          </div>
          <p className="mt-1 text-[12px] text-(--color-text-tertiary) leading-[1.55]">
            Tell the agents what files exist, what columns are in them, and which Python tools
            are available. The first ~200 words seeds every other stage.
          </p>
          <div className="mt-3 flex items-center gap-2 text-[11.5px] text-(--color-text-quaternary)">
            <Upload size={12} strokeWidth={1.5} />
            <span>Drop a CSV here to auto-summarize (coming soon)</span>
          </div>
        </div>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        placeholder=""
        className="w-full min-h-[420px] surface-card p-4 text-[13px] leading-[1.6] font-mono-body text-(--color-text-primary) resize-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-interactive)"
      />
    </div>
  );
}

function SidePanel({
  onEnhanceClick,
  enhanceToast,
}: {
  onEnhanceClick: () => void;
  enhanceToast: boolean;
}) {
  return (
    <aside className="w-[320px] hairline-l bg-(--color-bg-marketing) p-4 overflow-auto">
      <h3 className="font-label">Enhance description</h3>
      <p className="text-[12px] text-(--color-text-tertiary) mt-1.5">
        Use cmbagent&rsquo;s preprocess_task to summarize and structure your data description.
      </p>
      <div className="mt-3 space-y-2">
        <Field label="Summarizer model" value="gpt-4.1-mini" />
        <Field label="Formatter model" value="o3-mini" />
      </div>
      <Button variant="ghost" size="md" className="mt-3 w-full" onClick={onEnhanceClick}>
        <Sparkles size={13} strokeWidth={1.5} />
        Run enhance
      </Button>
      <div
        role="status"
        aria-live="polite"
        className={cn(
          "mt-2 text-[11.5px] text-(--color-status-amber) transition-opacity",
          enhanceToast ? "opacity-100" : "opacity-0",
        )}
      >
        Coming soon — enhance_data_description requires a real Plato install in the worker venv.
      </div>

      <h3 className="font-label mt-6">Presets</h3>
      <div className="mt-2 space-y-1">
        {["Astro / GW data starter", "Tabular ML starter", "Biology omics starter"].map((p) => (
          <button
            key={p}
            type="button"
            className="w-full surface-ghost h-8 px-2 text-left text-[12px] text-(--color-text-secondary)"
          >
            {p}
          </button>
        ))}
      </div>
    </aside>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-[11px] uppercase tracking-wider text-(--color-text-quaternary) font-medium">
        {label}
      </span>
      <button
        type="button"
        className="mt-1 w-full surface-ghost h-8 px-2 text-left text-[12px] flex items-center justify-between"
      >
        <span className="text-(--color-text-primary)">{value}</span>
        <span className="text-(--color-text-quaternary)">▾</span>
      </button>
    </div>
  );
}
