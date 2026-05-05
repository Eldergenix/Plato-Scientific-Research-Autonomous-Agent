"use client";

import * as React from "react";
import { Check, X, Loader2, Eye, EyeOff, Copy, Trash2 } from "lucide-react";
import { api, type KeyState, type KeysStatus } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

type ProviderId = keyof KeysStatus;

interface ProviderSpec {
  id: ProviderId;
  name: string;
  description: string;
  testable: boolean;
}

const PROVIDERS: ProviderSpec[] = [
  {
    id: "ANTHROPIC",
    name: "Anthropic",
    description: "Claude (claude-3.7-sonnet, claude-4-opus, claude-4.1-opus)",
    testable: true,
  },
  {
    id: "OPENAI",
    name: "OpenAI",
    description: "GPT-4o, GPT-4.1, GPT-5, o3-mini",
    testable: true,
  },
  {
    id: "GEMINI",
    name: "Google",
    description: "Gemini 2.0 / 2.5",
    testable: true,
  },
  {
    id: "PERPLEXITY",
    name: "Perplexity",
    description: "Literature search via FutureHouse",
    testable: false,
  },
  {
    id: "SEMANTIC_SCHOLAR",
    name: "Semantic Scholar",
    description: "Literature novelty checks",
    testable: false,
  },
  // Langfuse triplet (public/secret/host) — observability backend. Backend
  // surfaces all three fields via /keys/status (see KeysStatus in lib/api.ts);
  // omitting them here meant users could never set them from the UI.
  {
    id: "LANGFUSE_PUBLIC",
    name: "Langfuse public",
    description: "Public key for Langfuse tracing",
    testable: false,
  },
  {
    id: "LANGFUSE_SECRET",
    name: "Langfuse secret",
    description: "Secret key for Langfuse tracing",
    testable: false,
  },
  {
    id: "LANGFUSE_HOST",
    name: "Langfuse host",
    description: "e.g. https://cloud.langfuse.com",
    testable: false,
  },
];

function pillToneFor(state: KeyState): "neutral" | "indigo" | "green" {
  if (state === "from_env") return "green";
  if (state === "in_app") return "indigo";
  return "neutral";
}

function pillLabelFor(state: KeyState): string {
  if (state === "from_env") return "from_env";
  if (state === "in_app") return "in_app";
  return "unset";
}

interface TestResult {
  ok: boolean;
  latencyMs?: number;
  error?: string;
}

export default function KeysPage() {
  const [status, setStatus] = React.useState<KeysStatus | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [drafts, setDrafts] = React.useState<Partial<Record<ProviderId, string>>>({});
  const [overrides, setOverrides] = React.useState<Partial<Record<ProviderId, boolean>>>({});
  const [saving, setSaving] = React.useState<Partial<Record<ProviderId, boolean>>>({});
  const [testing, setTesting] = React.useState<Partial<Record<ProviderId, boolean>>>({});
  const [tests, setTests] = React.useState<Partial<Record<ProviderId, TestResult>>>({});
  const [revealed, setRevealed] = React.useState<Partial<Record<ProviderId, boolean>>>({});
  const [copied, setCopied] = React.useState<Partial<Record<ProviderId, boolean>>>({});

  const onCopyDraft = React.useCallback(async (id: ProviderId, value: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied((c) => ({ ...c, [id]: true }));
      // Reset the "Copied" affordance after 1.5s — long enough for the user
      // to register the click landed, short enough that two consecutive
      // copies of different fields don't blur together.
      window.setTimeout(() => {
        setCopied((c) => ({ ...c, [id]: false }));
      }, 1500);
    } catch {
      // Fallback for browsers without clipboard permission. We don't surface
      // an error toast since copy is a convenience action, not load-bearing.
    }
  }, []);

  const onClearKey = React.useCallback(
    async (id: ProviderId) => {
      // Sending an empty string to /keys is the canonical "delete this stored
      // key" signal in storage/key_store.py:set_key (empty value is treated
      // as a deletion). We send a single-key body to avoid clobbering peers.
      setSaving((s) => ({ ...s, [id]: true }));
      try {
        const next = await api.updateKeys({ [id]: "" });
        setStatus(next);
        setDrafts((d) => ({ ...d, [id]: "" }));
        setOverrides((o) => ({ ...o, [id]: false }));
      } catch (e) {
        console.error(`clear key ${id} failed`, e);
      } finally {
        setSaving((s) => ({ ...s, [id]: false }));
      }
    },
    [],
  );

  const refresh = React.useCallback(async () => {
    try {
      const s = await api.getKeysStatus();
      setStatus(s);
    } catch (err) {
      console.error("getKeysStatus failed", err);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const onSave = async (id: ProviderId) => {
    const value = drafts[id];
    if (!value) return;
    setSaving((s) => ({ ...s, [id]: true }));
    try {
      const next = await api.updateKeys({ [id]: value } as Partial<Record<ProviderId, string>>);
      setStatus(next);
      setDrafts((d) => ({ ...d, [id]: "" }));
      setOverrides((o) => ({ ...o, [id]: false }));
    } catch (err) {
      console.error("updateKeys failed", err);
    } finally {
      setSaving((s) => ({ ...s, [id]: false }));
    }
  };

  const onTest = async (id: ProviderId) => {
    if (id !== "OPENAI" && id !== "GEMINI" && id !== "ANTHROPIC") return;
    setTesting((t) => ({ ...t, [id]: true }));
    setTests((t) => ({ ...t, [id]: undefined }));
    try {
      const r = await api.testKey(id);
      setTests((t) => ({
        ...t,
        [id]: { ok: r.ok, latencyMs: r.latency_ms, error: r.error },
      }));
    } finally {
      setTesting((t) => ({ ...t, [id]: false }));
    }
  };

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="surface-linear-card p-5">
          <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
            API keys
          </h1>
          <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
            Configure provider credentials. Local desktop reads <code className="font-mono text-[12px]">~/.env</code> automatically; in-app keys take precedence.
          </p>
        </header>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {PROVIDERS.map((p) => {
            const state: KeyState = status?.[p.id] ?? "unset";
            const draft = drafts[p.id] ?? "";
            const isOverride = overrides[p.id] ?? false;
            const isFromEnv = state === "from_env";
            const inputDisabled = isFromEnv && !isOverride;
            const isDirty = draft.length > 0;
            const test = tests[p.id];
            const isTesting = testing[p.id];
            const isSaving = saving[p.id];

            return (
              <article key={p.id} className="surface-linear-card flex flex-col gap-3 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[15px] font-[510] text-(--color-text-primary-strong)">
                      {p.name}
                    </div>
                    <div className="mt-0.5 text-[12px] leading-snug text-(--color-text-tertiary-spec)">
                      {p.description}
                    </div>
                  </div>
                  <Pill tone={pillToneFor(state)} className="shrink-0">
                    {loading ? "…" : pillLabelFor(state)}
                  </Pill>
                </div>

                <div className="flex flex-col gap-2">
                  <div className="relative flex items-center gap-1">
                    <input
                      type={revealed[p.id] ? "text" : "password"}
                      value={draft}
                      disabled={inputDisabled}
                      onChange={(e) =>
                        setDrafts((d) => ({ ...d, [p.id]: e.target.value }))
                      }
                      placeholder={
                        inputDisabled
                          ? "Override with in-app key…"
                          : state === "in_app"
                            ? "Replace stored key…"
                            : "Paste API key"
                      }
                      className={cn(
                        "w-full rounded-[6px] border px-2 py-2 pr-20 font-mono text-[12px]",
                        "bg-[#141415] border-[#262628] text-(--color-text-primary)",
                        "placeholder:text-(--color-text-quaternary-spec)",
                        "focus:outline-none focus:border-(--color-brand-indigo)",
                        "disabled:opacity-60 disabled:cursor-not-allowed",
                      )}
                    />
                    <div className="absolute right-1 flex items-center gap-0.5">
                      <button
                        type="button"
                        onClick={() =>
                          setRevealed((r) => ({ ...r, [p.id]: !r[p.id] }))
                        }
                        disabled={!draft || inputDisabled}
                        aria-label={
                          revealed[p.id] ? "Hide key" : "Show key"
                        }
                        title={revealed[p.id] ? "Hide" : "Show"}
                        className="inline-flex size-7 items-center justify-center rounded text-(--color-text-tertiary-spec) hover:bg-[rgba(255,255,255,0.06)] hover:text-(--color-text-primary) disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {revealed[p.id] ? (
                          <EyeOff className="size-3.5" />
                        ) : (
                          <Eye className="size-3.5" />
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => onCopyDraft(p.id, draft)}
                        disabled={!draft}
                        aria-label="Copy key"
                        title={copied[p.id] ? "Copied" : "Copy"}
                        className="inline-flex size-7 items-center justify-center rounded text-(--color-text-tertiary-spec) hover:bg-[rgba(255,255,255,0.06)] hover:text-(--color-text-primary) disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {copied[p.id] ? (
                          <Check className="size-3.5 text-(--color-status-emerald)" />
                        ) : (
                          <Copy className="size-3.5" />
                        )}
                      </button>
                      {state === "in_app" ? (
                        <button
                          type="button"
                          onClick={() => onClearKey(p.id)}
                          disabled={Boolean(saving[p.id])}
                          aria-label="Delete stored key"
                          title="Delete stored key"
                          className="inline-flex size-7 items-center justify-center rounded text-(--color-text-tertiary-spec) hover:bg-[rgba(255,255,255,0.06)] hover:text-(--color-status-red-spec) disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      ) : null}
                    </div>
                  </div>
                  {isFromEnv && (
                    <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-(--color-text-tertiary-spec)">
                      <input
                        type="checkbox"
                        checked={isOverride}
                        onChange={(e) =>
                          setOverrides((o) => ({ ...o, [p.id]: e.target.checked }))
                        }
                        className="h-3 w-3"
                      />
                      <span>(Override)</span>
                    </label>
                  )}
                </div>

                <div className="flex flex-col gap-2 pt-1">
                  <div className="flex items-center gap-2">
                    {p.testable ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={isTesting || state === "unset"}
                        onClick={() => onTest(p.id)}
                      >
                        {isTesting ? (
                          <Loader2 className="size-3 animate-spin" />
                        ) : null}
                        Test
                      </Button>
                    ) : (
                      <span className="text-[11px] text-(--color-text-quaternary-spec)">
                        No test endpoint
                      </span>
                    )}
                    {test ? (
                      test.ok ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-(--color-status-emerald)">
                          <Check className="size-3" />
                          {test.latencyMs ? `${test.latencyMs}ms` : "ok"}
                        </span>
                      ) : (
                        <span
                          className="inline-flex items-center gap-1 truncate text-[11px] text-(--color-status-red)"
                          title={test.error}
                        >
                          <X className="size-3" />
                          {test.error ?? "failed"}
                        </span>
                      )
                    ) : null}
                  </div>
                  {isDirty && (
                    <Button
                      variant="primary"
                      size="sm"
                      disabled={isSaving}
                      onClick={() => onSave(p.id)}
                    >
                      {isSaving ? <Loader2 className="size-3 animate-spin" /> : null}
                      Save
                    </Button>
                  )}
                </div>
              </article>
            );
          })}
        </section>
      </div>
    </div>
  );
}
