"use client";

import * as React from "react";
import { Check, X, Loader2, Eye, EyeOff, Copy, Trash2 } from "lucide-react";
import { api, type HuggingFaceAccountStatus, type KeyState, type KeysStatus } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

type ProviderId = keyof KeysStatus;

interface ProviderSpec {
  id: ProviderId;
  name: string;
  description: string;
  testable: boolean;
  group: "models" | "support";
}

const PROVIDERS: ProviderSpec[] = [
  {
    id: "ANTHROPIC",
    name: "Anthropic",
    description: "Claude models",
    testable: true,
    group: "models",
  },
  {
    id: "OPENAI",
    name: "OpenAI",
    description: "GPT and reasoning models",
    testable: true,
    group: "models",
  },
  {
    id: "GEMINI",
    name: "Google",
    description: "Gemini models",
    testable: true,
    group: "models",
  },
  {
    id: "HUGGINGFACE",
    name: "Hugging Face",
    description: "HF account, models, and Inference Providers",
    testable: true,
    group: "models",
  },
  {
    id: "PERPLEXITY",
    name: "Perplexity",
    description: "Literature search",
    testable: false,
    group: "support",
  },
  {
    id: "SEMANTIC_SCHOLAR",
    name: "Semantic Scholar",
    description: "Novelty checks",
    testable: false,
    group: "support",
  },
  // Langfuse triplet (public/secret/host) — observability backend. Backend
  // surfaces all three fields via /keys/status (see KeysStatus in lib/api.ts);
  // omitting them here meant users could never set them from the UI.
  {
    id: "LANGFUSE_PUBLIC",
    name: "Langfuse public",
    description: "Public key for Langfuse tracing",
    testable: false,
    group: "support",
  },
  {
    id: "LANGFUSE_SECRET",
    name: "Langfuse secret",
    description: "Secret key for Langfuse tracing",
    testable: false,
    group: "support",
  },
  {
    id: "LANGFUSE_HOST",
    name: "Langfuse host",
    description: "Tracing endpoint",
    testable: false,
    group: "support",
  },
];

const PROVIDER_SECTIONS: Array<{
  id: ProviderSpec["group"];
  title: string;
  description: string;
}> = [
  {
    id: "models",
    title: "Model providers",
    description: "Keys used for reasoning, drafting, and execution.",
  },
  {
    id: "support",
    title: "Search & tracing",
    description: "Retrieval, novelty, and observability integrations.",
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
  account?: string;
}

export default function KeysPage() {
  const [status, setStatus] = React.useState<KeysStatus | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState(false);
  const [drafts, setDrafts] = React.useState<Partial<Record<ProviderId, string>>>({});
  const [overrides, setOverrides] = React.useState<Partial<Record<ProviderId, boolean>>>({});
  const [saving, setSaving] = React.useState<Partial<Record<ProviderId, boolean>>>({});
  const [testing, setTesting] = React.useState<Partial<Record<ProviderId, boolean>>>({});
  const [tests, setTests] = React.useState<Partial<Record<ProviderId, TestResult>>>({});
  const [huggingFaceAccount, setHuggingFaceAccount] =
    React.useState<HuggingFaceAccountStatus | null>(null);
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
      setLoadError(false);
    } catch (err) {
      setLoadError(true);
      console.error("getKeysStatus failed", err);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  React.useEffect(() => {
    if (!status || status.HUGGINGFACE === "unset") {
      setHuggingFaceAccount(null);
      return;
    }
    let cancelled = false;
    api
      .getHuggingFaceAccount()
      .then((account) => {
        if (!cancelled) setHuggingFaceAccount(account);
      })
      .catch((err) => {
        console.error("getHuggingFaceAccount failed", err);
        if (!cancelled) {
          setHuggingFaceAccount({
            connected: false,
            account: null,
            error: err instanceof Error ? err.message : "account lookup failed",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

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
    if (
      id !== "OPENAI" &&
      id !== "GEMINI" &&
      id !== "ANTHROPIC" &&
      id !== "HUGGINGFACE"
    ) return;
    setTesting((t) => ({ ...t, [id]: true }));
    setTests((t) => ({ ...t, [id]: undefined }));
    try {
      const r = await api.testKey(id);
      if (id === "HUGGINGFACE" && r.ok) {
        void api.getHuggingFaceAccount().then(setHuggingFaceAccount).catch(() => undefined);
      }
      setTests((t) => ({
        ...t,
        [id]: {
          ok: r.ok,
          latencyMs: r.latency_ms,
          error: r.error,
          account: r.account,
        },
      }));
    } finally {
      setTesting((t) => ({ ...t, [id]: false }));
    }
  };

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-3 py-4 sm:px-6 sm:py-8">
      <div className="mx-auto max-w-6xl space-y-5">
        <header className="surface-linear-card p-4 sm:p-5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div className="min-w-0">
              <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
                API keys
              </h1>
              <p className="mt-1 max-w-2xl text-[13px] text-(--color-text-tertiary-spec)">
                Configure provider credentials. Local <code className="font-mono text-[12px]">~/.env</code> keys are detected; in-app keys override them.
              </p>
            </div>
            <Pill
              tone={loading ? "neutral" : loadError ? "amber" : "green"}
              className="self-start sm:self-auto"
            >
              {loading ? "Loading" : loadError ? "Offline" : "Ready"}
            </Pill>
          </div>
        </header>

        {PROVIDER_SECTIONS.map((section) => (
          <section key={section.id} className="space-y-2">
            <div className="flex flex-col gap-0.5 px-1 sm:flex-row sm:items-baseline sm:justify-between">
              <h2 className="text-[14px] font-[510] text-(--color-text-primary-strong)">
                {section.title}
              </h2>
              <p className="text-[12px] text-(--color-text-tertiary-spec)">
                {section.description}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
              {PROVIDERS.filter((p) => p.group === section.id).map((p) => {
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
                  <article key={p.id} className="surface-linear-card flex min-w-0 flex-col gap-3 p-3 sm:p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-[15px] font-[510] text-(--color-text-primary-strong)">
                          {p.name}
                        </div>
                        <div className="mt-0.5 truncate text-[12px] leading-snug text-(--color-text-tertiary-spec)">
                          {p.description}
                        </div>
                      </div>
                      <Pill tone={pillToneFor(state)} className="shrink-0">
                        {loading ? "..." : pillLabelFor(state)}
                      </Pill>
                    </div>

                    <div className="flex flex-col gap-2">
                      <div className="relative flex items-center">
                        <input
                          type={revealed[p.id] ? "text" : "password"}
                          value={draft}
                          disabled={inputDisabled}
                          onChange={(e) =>
                            setDrafts((d) => ({ ...d, [p.id]: e.target.value }))
                          }
                          placeholder={
                            inputDisabled
                              ? "Override key"
                              : state === "in_app"
                                ? "Replace key"
                                : "Paste key"
                          }
                          className={cn(
                            "h-9 w-full rounded-[6px] border px-2.5 pr-24 font-mono text-[12px]",
                            "border-(--color-border-card) bg-(--color-bg-pill-inactive) text-(--color-text-primary)",
                            "placeholder:text-(--color-text-quaternary-spec)",
                            "focus:outline-none focus:border-(--color-brand-indigo)",
                            "disabled:cursor-not-allowed disabled:opacity-60",
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
                            className="inline-flex size-7 items-center justify-center rounded text-(--color-text-tertiary-spec) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary) disabled:cursor-not-allowed disabled:opacity-40"
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
                            className="inline-flex size-7 items-center justify-center rounded text-(--color-text-tertiary-spec) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary) disabled:cursor-not-allowed disabled:opacity-40"
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
                              className="inline-flex size-7 items-center justify-center rounded text-(--color-text-tertiary-spec) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-status-red-spec) disabled:cursor-not-allowed disabled:opacity-40"
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
                          <span>Override</span>
                        </label>
                      )}
                    </div>

                    {p.id === "HUGGINGFACE" && huggingFaceAccount?.account ? (
                      <div className="rounded-[6px] border border-(--color-border-card) bg-(--color-bg-pill-inactive) p-2 text-[11px] text-(--color-text-tertiary-spec)">
                        <div className="truncate text-(--color-text-primary)">
                          {huggingFaceAccount.account.fullname ||
                            huggingFaceAccount.account.name ||
                            "Connected account"}
                        </div>
                        {huggingFaceAccount.account.email ? (
                          <div className="mt-0.5 truncate">{huggingFaceAccount.account.email}</div>
                        ) : null}
                        {huggingFaceAccount.account.orgs.length ? (
                          <div className="mt-1 truncate">
                            {huggingFaceAccount.account.orgs
                              .map((org) => org.name)
                              .filter(Boolean)
                              .join(", ")}
                          </div>
                        ) : null}
                      </div>
                    ) : null}

                    <div className="flex flex-wrap items-center gap-2 pt-1">
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
                          Stored
                        </span>
                      )}
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
                      {test ? (
                        test.ok ? (
                          <span className="inline-flex min-w-0 items-center gap-1 text-[11px] text-(--color-status-emerald)">
                            <Check className="size-3" />
                            {test.account ?? (test.latencyMs ? `${test.latencyMs}ms` : "ok")}
                          </span>
                        ) : (
                          <span
                            className="inline-flex min-w-0 items-center gap-1 truncate text-[11px] text-(--color-status-red)"
                            title={test.error}
                          >
                            <X className="size-3 flex-none" />
                            {test.error ?? "failed"}
                          </span>
                        )
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
