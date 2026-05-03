"use client";

/**
 * Client island for /settings/llm-providers.
 *
 * Owns: keys-status fetch, user-preference fetch, per-stage model
 * select mutation, in-flight pending state, and the toast that
 * surfaces success / failure of a save click. The page.tsx wrapper is
 * a Server Component so it can export `metadata` and emit static
 * chrome without paying the JS-bundle cost.
 *
 * Data-fetching stays on the client — the model catalog (MODELS,
 * MODEL_GROUPS) ships statically in the bundle, and key/preferences
 * fetches need to honor the in-browser auth headers attached by the
 * shared `api` helper.
 */

import * as React from "react";
import Link from "next/link";
import {
  BookMarked,
  CheckCircle2,
  ClipboardList,
  ExternalLink,
  FlaskConical,
  Lightbulb,
  Loader2,
  Newspaper,
  Stamp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api, type KeysStatus } from "@/lib/api";
import { MODELS, MODEL_GROUPS, modelsForProvider } from "@/lib/models";
import type { ModelDef, Provider } from "@/lib/types";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

type StageId = "idea" | "literature" | "method" | "results" | "paper" | "referee";

const STAGE_ROWS: Array<{ id: StageId; label: string; icon: LucideIcon }> = [
  { id: "idea", label: "Idea", icon: Lightbulb },
  { id: "literature", label: "Literature", icon: BookMarked },
  { id: "method", label: "Method", icon: ClipboardList },
  { id: "results", label: "Results", icon: FlaskConical },
  { id: "paper", label: "Paper", icon: Newspaper },
  { id: "referee", label: "Referee", icon: Stamp },
];

// Recommended fallback when the user hasn't picked a model yet. Mirrors
// the table on the /models page.
const RECOMMENDED_BY_STAGE: Record<StageId, string> = {
  idea: "gpt-4.1",
  literature: "gpt-4.1-mini",
  method: "claude-4.1-opus",
  results: "gpt-5",
  paper: "claude-4.1-opus",
  referee: "o3-mini",
};

const PROVIDER_KEY_FIELD: Record<Provider, keyof KeysStatus | undefined> = {
  anthropic: "ANTHROPIC",
  openai: "OPENAI",
  gemini: "GEMINI",
  perplexity: "PERPLEXITY",
  semantic_scholar: "SEMANTIC_SCHOLAR",
};

interface PreferencesResponse {
  default_domain: string | null;
  default_executor: string | null;
  default_models: Record<string, string>;
}

type FetchState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      keysStatus: KeysStatus;
      models: Record<StageId, string>;
    };

function providerHasKey(p: Provider, status: KeysStatus): boolean {
  const field = PROVIDER_KEY_FIELD[p];
  if (!field) return false;
  return status[field] !== "unset";
}

function modelById(id: string): ModelDef | undefined {
  return MODELS.find((m) => m.id === id);
}

export function LlmProvidersClient() {
  const [state, setState] = React.useState<FetchState>({ kind: "loading" });
  const [pendingStage, setPendingStage] = React.useState<StageId | null>(null);
  const [savedMsg, setSavedMsg] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [keys, prefs] = await Promise.all([
          api.getKeysStatus(),
          fetch(`${API_BASE}/user/preferences`, {
            credentials: "include",
            cache: "no-store",
          }).then(async (r) => {
            if (!r.ok) throw new Error(`/user/preferences ${r.status}`);
            return (await r.json()) as PreferencesResponse;
          }),
        ]);
        if (cancelled) return;
        const persisted = prefs.default_models ?? {};
        const models: Record<StageId, string> = {
          idea: persisted.idea ?? RECOMMENDED_BY_STAGE.idea,
          literature: persisted.literature ?? RECOMMENDED_BY_STAGE.literature,
          method: persisted.method ?? RECOMMENDED_BY_STAGE.method,
          results: persisted.results ?? RECOMMENDED_BY_STAGE.results,
          paper: persisted.paper ?? RECOMMENDED_BY_STAGE.paper,
          referee: persisted.referee ?? RECOMMENDED_BY_STAGE.referee,
        };
        setState({ kind: "ready", keysStatus: keys, models });
      } catch (err) {
        if (cancelled) return;
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Failed to load",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const onModelChange = async (stage: StageId, modelId: string) => {
    if (state.kind !== "ready") return;
    const previous = state.models[stage];
    setState({ ...state, models: { ...state.models, [stage]: modelId } });
    setPendingStage(stage);
    setSavedMsg(null);
    try {
      const r = await fetch(`${API_BASE}/user/preferences`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ default_models: { [stage]: modelId } }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSavedMsg(`Saved ${stage} → ${modelId}.`);
    } catch (err) {
      // Roll back optimistic update so the dropdown reflects truth.
      setState((prev) =>
        prev.kind === "ready"
          ? { ...prev, models: { ...prev.models, [stage]: previous } }
          : prev,
      );
      setSavedMsg(
        err instanceof Error ? `Failed: ${err.message}` : "Failed to save",
      );
    } finally {
      setPendingStage(null);
    }
  };

  if (state.kind === "loading") {
    return (
      <div
        className="surface-linear-card p-5 text-[13px] text-(--color-text-tertiary)"
        data-testid="llm-providers-loading"
      >
        Loading providers…
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div
        className="surface-linear-card p-5 text-[13px] text-(--color-status-red)"
        data-testid="llm-providers-error"
      >
        {state.message}
      </div>
    );
  }

  const { keysStatus, models } = state;

  return (
    <>
      <section
        className="surface-linear-card p-5"
        data-testid="llm-providers-providers"
      >
        <SectionTitle
          title="Providers"
          subtitle="Provider credentials. Add or update keys under /keys."
        />
        <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {MODEL_GROUPS.map((g) => {
            const has = providerHasKey(g.provider, keysStatus);
            const count = modelsForProvider(g.provider).length;
            return (
              <li
                key={g.provider}
                className="flex flex-col gap-1.5 rounded-[10px] border border-(--color-border-card) bg-(--color-bg-card) p-3"
                data-testid={`llm-provider-${g.provider}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-[510] text-(--color-text-primary)">
                    {g.label}
                  </span>
                  <Pill tone={has ? "green" : "neutral"}>
                    {has ? "key set" : "no key"}
                  </Pill>
                </div>
                <div className="text-[12px] text-(--color-text-tertiary)">
                  {count} {count === 1 ? "model" : "models"} available
                </div>
                {!has ? (
                  <Link
                    href="/keys"
                    className="inline-flex items-center gap-1 text-[12px] text-(--color-brand-hover) hover:underline"
                  >
                    Add key
                    <ExternalLink size={11} strokeWidth={1.75} />
                  </Link>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>

      <section className="surface-linear-card p-5">
        <SectionTitle
          title="Per-stage models"
          subtitle="Pick the model Plato uses for each stage. Saves on change."
        />
        <div className="mt-3 grid grid-cols-1 gap-2">
          {STAGE_ROWS.map(({ id, label, icon: Icon }) => {
            const selectedId = models[id];
            const selected = modelById(selectedId);
            const ok = selected
              ? providerHasKey(selected.provider, keysStatus)
              : false;
            const isPending = pendingStage === id;
            return (
              <div
                key={id}
                className="flex flex-col gap-2 rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) p-3 sm:flex-row sm:items-center sm:gap-3"
                data-testid={`llm-stage-row-${id}`}
              >
                <div className="flex items-center gap-2 sm:w-32">
                  <Icon
                    size={14}
                    strokeWidth={1.6}
                    className="shrink-0 text-(--color-text-tertiary)"
                  />
                  <span className="text-[13px] font-[510] text-(--color-text-primary)">
                    {label}
                  </span>
                </div>
                <select
                  value={selectedId}
                  disabled={isPending}
                  onChange={(e) => onModelChange(id, e.target.value)}
                  data-testid={`llm-stage-select-${id}`}
                  className={cn(
                    "h-8 flex-1 rounded-[6px] border px-2 font-mono text-[12px]",
                    "bg-[#141415] border-[#262628] text-(--color-text-primary)",
                    "focus:outline-none focus:border-(--color-brand-indigo)",
                    "disabled:cursor-not-allowed disabled:opacity-60",
                  )}
                >
                  {MODEL_GROUPS.map((g) => (
                    <optgroup key={g.provider} label={g.label}>
                      {modelsForProvider(g.provider).map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.label} ({m.id})
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
                <div className="flex shrink-0 items-center gap-2 sm:w-32 sm:justify-end">
                  {isPending ? (
                    <Loader2
                      size={13}
                      className="animate-spin text-(--color-text-tertiary)"
                    />
                  ) : ok ? (
                    <span className="inline-flex items-center gap-1 text-[11.5px] text-(--color-status-emerald)">
                      <CheckCircle2 size={12} strokeWidth={1.75} />
                      ready
                    </span>
                  ) : (
                    <span className="text-[11.5px] text-(--color-status-red)">
                      key missing
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {savedMsg ? (
          <div
            className="mt-3 text-[12px] text-(--color-text-tertiary)"
            data-testid="llm-providers-saved-msg"
          >
            {savedMsg}
          </div>
        ) : null}
      </section>
    </>
  );
}

function SectionTitle({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <div>
      <h2 className="text-[15px] font-[510] tracking-[-0.2px] text-(--color-text-primary-strong)">
        {title}
      </h2>
      {subtitle ? (
        <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
          {subtitle}
        </p>
      ) : null}
    </div>
  );
}
