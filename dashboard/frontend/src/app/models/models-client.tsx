"use client";

import * as React from "react";
import {
  Search,
  Filter,
  ArrowUpDown,
  ChevronUp,
  ChevronDown,
  Lightbulb,
  BookMarked,
  ClipboardList,
  FlaskConical,
  Newspaper,
  Stamp,
} from "lucide-react";
import { api, type KeysStatus } from "@/lib/api";
import { MODELS, MODEL_GROUPS } from "@/lib/models";
import type { ModelDef, Provider } from "@/lib/types";
import { Pill } from "@/components/ui/pill";
import { TabPills } from "@/components/shell/tab-pills";
import { ModelPickerCompact } from "@/components/ui/model-picker";
import { cn } from "@/lib/utils";

// ----------------------------------------------------------------- constants

const PROVIDER_LABEL: Record<Provider, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  gemini: "Google",
  huggingface: "Hugging Face",
  perplexity: "Perplexity",
  semantic_scholar: "Semantic Scholar",
};

// Per-stage default mapping. The product brief calls these "recommended"; the
// user can override any stage and the override persists to localStorage until
// the backend gains a /api/v1/users/<uid>/model_preferences endpoint analogous
// to executor_preferences.py — at which point this falls back gracefully.
type StageId =
  | "idea"
  | "literature"
  | "method"
  | "results"
  | "paper"
  | "referee";

const RECOMMENDED_BY_STAGE: Record<StageId, string> = {
  idea: "gpt-4.1",
  literature: "gpt-4.1-mini",
  method: "claude-4.1-opus",
  results: "gpt-5",
  paper: "claude-4.1-opus",
  referee: "o3-mini",
};

const STAGE_MODEL_OVERRIDES_KEY = "plato.stageModelOverrides.v1";

function loadStageOverrides(): Partial<Record<StageId, string>> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STAGE_MODEL_OVERRIDES_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    return parsed as Partial<Record<StageId, string>>;
  } catch {
    return {};
  }
}

function saveStageOverrides(overrides: Partial<Record<StageId, string>>) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      STAGE_MODEL_OVERRIDES_KEY,
      JSON.stringify(overrides),
    );
  } catch {
    // localStorage full or disabled — silent fail is acceptable here since
    // the next render will fall back to recommended defaults.
  }
}

// Provider colors per spec (anthropic teal, openai green, google blue).
const PROVIDER_COLOR: Record<Provider, string> = {
  anthropic: "#00738E",
  openai: "#27A644",
  gemini: "#4EA7FC",
  huggingface: "#ff9d00",
  perplexity: "var(--color-status-purple)",
  semantic_scholar: "#ff7236",
};

const PROVIDER_KEY_FIELD: Record<Provider, keyof KeysStatus | undefined> = {
  anthropic: "ANTHROPIC",
  openai: "OPENAI",
  gemini: "GEMINI",
  huggingface: "HUGGINGFACE",
  perplexity: "PERPLEXITY",
  semantic_scholar: "SEMANTIC_SCHOLAR",
};

const FILTER_TABS = [
  { id: "all", label: "All" },
  { id: "premium", label: "Premium" },
  { id: "cheap", label: "Cheap" },
] as const;

type FilterTabId = (typeof FILTER_TABS)[number]["id"];
const SEARCH_FIELD_CLASS = cn(
  "inline-flex h-8 w-full items-center gap-1.5 rounded-[6px] border px-2 sm:h-6 sm:w-[220px]",
  "border-(--color-border-pill) bg-(--color-bg-card) text-(--color-text-primary)",
  "shadow-[var(--shadow-glass)] transition-colors",
  "hover:border-(--color-border-strong) focus-within:border-(--color-brand-indigo)",
);

const STAGE_ROWS: Array<{
  id: keyof typeof RECOMMENDED_BY_STAGE;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
}> = [
  { id: "idea", label: "Idea", icon: Lightbulb },
  { id: "literature", label: "Literature", icon: BookMarked },
  { id: "method", label: "Method", icon: ClipboardList },
  { id: "results", label: "Results", icon: FlaskConical },
  { id: "paper", label: "Paper", icon: Newspaper },
  { id: "referee", label: "Referee", icon: Stamp },
];

// ----------------------------------------------------------------- helpers

type SortKey = "label" | "provider" | "maxOutputTokens" | "costInputPer1k" | "costOutputPer1k";

function formatTokensShort(n: number): string {
  if (n >= 1000) return `${Math.round(n / 1000)}k`;
  return `${n}`;
}

function formatCostPer1k(v: number | undefined): string {
  if (v === undefined) return "—";
  if (v < 0.001) return `$${v.toFixed(5)} / 1k`;
  if (v < 0.01) return `$${v.toFixed(4)} / 1k`;
  return `$${v.toFixed(3)} / 1k`;
}

function isPremium(m: ModelDef): boolean {
  return (m.costInputPer1k ?? 0) >= 0.01 || (m.costOutputPer1k ?? 0) >= 0.05;
}

function isCheap(m: ModelDef): boolean {
  return (m.costInputPer1k ?? 0) <= 0.0005;
}

function bestForFor(m: ModelDef): { tone: "indigo" | "green" | "lavender" | "amber" | "neutral"; label: string } {
  const note = m.notes?.split(/[·•]/)[0].trim();
  if (note) {
    const lower = note.toLowerCase();
    if (lower.startsWith("recommended")) return { tone: "indigo", label: note };
    if (lower.startsWith("cheap")) return { tone: "green", label: note };
    if (lower.startsWith("strong")) return { tone: "lavender", label: note };
    if (lower.startsWith("premium")) return { tone: "amber", label: note };
  }
  if (isPremium(m)) return { tone: "amber", label: "Premium" };
  if (isCheap(m)) return { tone: "green", label: "Cheap" };
  return { tone: "neutral", label: "General" };
}

function providerHasKey(p: Provider, status: KeysStatus | null): boolean {
  if (!status) return false;
  const field = PROVIDER_KEY_FIELD[p];
  if (!field) return false;
  return status[field] !== "unset";
}

// ----------------------------------------------------------------- subcomponents

function ProviderDot({ provider, size = 8 }: { provider: Provider; size?: number }) {
  return (
    <span
      aria-hidden
      className="inline-block shrink-0 rounded-full"
      style={{ width: size, height: size, backgroundColor: PROVIDER_COLOR[provider] }}
    />
  );
}

function StatusDot({ ok, loading }: { ok: boolean; loading: boolean }) {
  const color = loading ? "#515153" : ok ? "#27A644" : "#515153";
  return (
    <span
      aria-hidden
      title={loading ? "loading" : ok ? "key available" : "no key"}
      className="inline-block shrink-0 rounded-full"
      style={{ width: 8, height: 8, backgroundColor: color }}
    />
  );
}

function SortHeader({
  label,
  sortKey,
  active,
  direction,
  onClick,
  align = "left",
}: {
  label: string;
  sortKey: SortKey | null;
  active: boolean;
  direction: "asc" | "desc";
  onClick?: () => void;
  align?: "left" | "right";
}) {
  const Icon = !sortKey ? null : !active ? ArrowUpDown : direction === "asc" ? ChevronUp : ChevronDown;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!sortKey}
      className={cn(
        "inline-flex items-center gap-1 text-[11px] font-medium uppercase tracking-wider",
        "text-(--color-text-tertiary-spec)",
        sortKey && "hover:text-(--color-text-primary-strong) cursor-pointer",
        align === "right" && "justify-end",
      )}
    >
      <span>{label}</span>
      {Icon && (
        <Icon
          size={11}
          strokeWidth={1.6}
          className={cn("shrink-0", active ? "text-(--color-text-primary-strong)" : "text-(--color-text-quaternary-spec)")}
        />
      )}
    </button>
  );
}

function MobileModelCard({
  model,
  keysStatus,
  keysLoading,
}: {
  model: ModelDef;
  keysStatus: KeysStatus | null;
  keysLoading: boolean;
}) {
  const best = bestForFor(model);
  const ok = providerHasKey(model.provider, keysStatus);

  return (
    <article className="surface-linear-card p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-[13.5px] font-[510] text-(--color-text-primary-strong)">
            {model.label}
          </h2>
          <p className="truncate font-mono text-[11px] text-(--color-text-row-meta)">
            {model.id}
          </p>
        </div>
        <span className="inline-flex flex-none items-center gap-1.5 text-[12px] text-(--color-text-secondary-spec)">
          <StatusDot ok={ok} loading={keysLoading} />
          {keysLoading ? "..." : ok ? "Ready" : "No key"}
        </span>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="inline-flex min-w-0 items-center gap-2 text-[12.5px] text-(--color-text-secondary-spec)">
          <ProviderDot provider={model.provider} />
          <span className="truncate">{PROVIDER_LABEL[model.provider]}</span>
        </span>
        <Pill tone={best.tone}>{best.label}</Pill>
      </div>

      <dl className="mt-3 grid grid-cols-3 gap-2 text-[11.5px]">
        <div className="rounded-[6px] bg-(--color-bg-pill-inactive) px-2 py-1.5">
          <dt className="text-(--color-text-quaternary-spec)">Max</dt>
          <dd className="mt-0.5 font-mono text-(--color-text-primary)">
            {formatTokensShort(model.maxOutputTokens)}
          </dd>
        </div>
        <div className="rounded-[6px] bg-(--color-bg-pill-inactive) px-2 py-1.5">
          <dt className="text-(--color-text-quaternary-spec)">Input</dt>
          <dd className="mt-0.5 truncate font-mono text-(--color-text-primary)">
            {formatCostPer1k(model.costInputPer1k)}
          </dd>
        </div>
        <div className="rounded-[6px] bg-(--color-bg-pill-inactive) px-2 py-1.5">
          <dt className="text-(--color-text-quaternary-spec)">Output</dt>
          <dd className="mt-0.5 truncate font-mono text-(--color-text-primary)">
            {formatCostPer1k(model.costOutputPer1k)}
          </dd>
        </div>
      </dl>
    </article>
  );
}

// ----------------------------------------------------------------- page

export default function ModelsPage() {
  const [keysStatus, setKeysStatus] = React.useState<KeysStatus | null>(null);
  const [keysLoading, setKeysLoading] = React.useState(true);
  const [filter, setFilter] = React.useState<FilterTabId>("all");
  const [query, setQuery] = React.useState("");
  const [sortKey, setSortKey] = React.useState<SortKey>("provider");
  const [sortDir, setSortDir] = React.useState<"asc" | "desc">("asc");
  const [stageOverrides, setStageOverrides] = React.useState<
    Partial<Record<StageId, string>>
  >({});

  React.useEffect(() => {
    setStageOverrides(loadStageOverrides());
  }, []);

  const setStageModel = React.useCallback((stage: StageId, model: string) => {
    setStageOverrides((prev) => {
      const next: Partial<Record<StageId, string>> =
        model === RECOMMENDED_BY_STAGE[stage]
          ? // Reverting to the recommended default — clear the override entry
            // so the user's preference structure stays minimal.
            (() => {
              const { [stage]: _drop, ...rest } = prev;
              return rest;
            })()
          : { ...prev, [stage]: model };
      saveStageOverrides(next);
      return next;
    });
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    api
      .getKeysStatus()
      .then((s) => {
        if (!cancelled) setKeysStatus(s);
      })
      .catch((err) => {
        console.error("getKeysStatus failed", err);
      })
      .finally(() => {
        if (!cancelled) setKeysLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const visibleModels = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = MODELS.slice();
    if (filter === "premium") list = list.filter(isPremium);
    if (filter === "cheap") list = list.filter(isCheap);
    if (q) {
      list = list.filter(
        (m) =>
          m.label.toLowerCase().includes(q) ||
          m.id.toLowerCase().includes(q) ||
          PROVIDER_LABEL[m.provider].toLowerCase().includes(q),
      );
    }
    list.sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      switch (sortKey) {
        case "label":
          return a.label.localeCompare(b.label) * dir;
        case "provider":
          return (
            (PROVIDER_LABEL[a.provider].localeCompare(PROVIDER_LABEL[b.provider]) ||
              a.label.localeCompare(b.label)) * dir
          );
        case "maxOutputTokens":
          return (a.maxOutputTokens - b.maxOutputTokens) * dir;
        case "costInputPer1k":
          return ((a.costInputPer1k ?? 0) - (b.costInputPer1k ?? 0)) * dir;
        case "costOutputPer1k":
          return ((a.costOutputPer1k ?? 0) - (b.costOutputPer1k ?? 0)) * dir;
        default:
          return 0;
      }
    });
    return list;
  }, [filter, query, sortKey, sortDir]);

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-3 py-4 sm:px-6 sm:py-8">
      <div className="mx-auto max-w-7xl space-y-4">
        {/* ------------------------------------------------------- header */}
        <header className="surface-linear-card flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <h1
              className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong) sm:text-[24px]"
            >
              Models
            </h1>
            <p className="mt-0.5 text-[13px] text-(--color-text-tertiary-spec)">
              {MODELS.length} models across {MODEL_GROUPS.length} providers. Pricing in USD per 1K tokens.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {MODEL_GROUPS.map((g) => {
              const has = providerHasKey(g.provider, keysStatus);
              const dataColor =
                g.provider === "anthropic" ? "teal" : g.provider === "openai" ? "green" : "blue";
              return (
                <span
                  key={g.provider}
                  className="tag-pill border-(--color-border-pill)"
                  data-color={dataColor}
                  title={keysLoading ? "Loading key status…" : has ? `${g.label} key available` : `${g.label} key missing`}
                >
                  <span>
                    {g.label}{" "}
                    <span className="text-(--color-text-row-meta)">
                      {keysLoading ? "…" : has ? "✓" : "✗"}
                    </span>
                  </span>
                </span>
              );
            })}
          </div>
        </header>

        {/* ------------------------------------------------------- filter bar */}
        <div className="flex h-auto flex-wrap items-center gap-2 px-0 sm:px-4">
          <Filter size={12} strokeWidth={1.6} className="text-(--color-text-quaternary-spec) shrink-0" />
          <TabPills
            tabs={FILTER_TABS as unknown as ReadonlyArray<{ id: string; label: string }>}
            activeId={filter}
            onSelect={(id) => setFilter(id as FilterTabId)}
            ariaLabel="Filter models by tier"
          />
          <div className="flex w-full items-center gap-1.5 sm:ml-auto sm:w-auto">
            <label className={SEARCH_FIELD_CLASS}>
              <Search
                size={11}
                strokeWidth={1.6}
                className="shrink-0 text-(--color-text-quaternary-spec)"
              />
              <input
                type="search"
                aria-label="Search for model or provider"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search for model or provider"
                className={cn(
                  "min-w-0 flex-1 bg-transparent font-mono text-[12px] text-(--color-text-primary)",
                  "placeholder:text-(--color-text-quaternary-spec)",
                  "focus:outline-none",
                )}
              />
            </label>
          </div>
        </div>

        {/* ------------------------------------------------------- table */}
        <section className="surface-linear-card hidden overflow-hidden md:block">
          <div className="overflow-x-auto">
            <table className="min-w-[900px] w-full table-fixed border-collapse">
              <colgroup>
                <col style={{ width: "26%" }} />
                <col style={{ width: "13%" }} />
                <col style={{ width: "10%" }} />
                <col style={{ width: "13%" }} />
                <col style={{ width: "13%" }} />
                <col style={{ width: "17%" }} />
                <col style={{ width: "8%" }} />
              </colgroup>
              <thead>
                <tr className="hairline-b" style={{ height: 36 }}>
                  {(
                    [
                      ["Model", "label", "left"],
                      ["Provider", "provider", "left"],
                      ["Max output", "maxOutputTokens", "right"],
                      ["Input cost", "costInputPer1k", "right"],
                      ["Output cost", "costOutputPer1k", "right"],
                      ["Best for", null, "left"],
                      ["Status", null, "center"],
                    ] as Array<[string, SortKey | null, "left" | "right" | "center"]>
                  ).map(([label, key, align]) => (
                    <th
                      key={label}
                      className={cn(
                        "px-4",
                        align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left",
                      )}
                    >
                      <SortHeader
                        label={label}
                        sortKey={key}
                        active={key !== null && sortKey === key}
                        direction={sortDir}
                        onClick={key ? () => onSort(key) : undefined}
                        align={align === "right" ? "right" : "left"}
                      />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleModels.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-[12.5px] text-(--color-text-tertiary-spec)">
                      No models match the current filter.
                    </td>
                  </tr>
                ) : (
                  visibleModels.map((m) => {
                    const best = bestForFor(m);
                    const ok = providerHasKey(m.provider, keysStatus);
                    const cost = "font-mono text-[12px] tabular-nums text-(--color-text-primary)";
                    return (
                      <tr
                        key={m.id}
                        className="transition-colors hover:bg-[rgba(255,255,255,0.02)]"
                        style={{ height: 44 }}
                      >
                        <td className="px-4">
                          <div className="flex flex-col">
                            <span className="text-[13px] text-(--color-text-primary-strong)">{m.label}</span>
                            <span className="font-mono text-[10.5px] text-[#949496]">{m.id}</span>
                          </div>
                        </td>
                        <td className="px-4">
                          <span className="inline-flex items-center gap-2 text-[12.5px] text-(--color-text-secondary-spec)">
                            <ProviderDot provider={m.provider} />
                            {PROVIDER_LABEL[m.provider]}
                          </span>
                        </td>
                        <td className="px-4 text-right">
                          <span className={cost}>{formatTokensShort(m.maxOutputTokens)}</span>
                        </td>
                        <td className="px-4 text-right">
                          <span className={cost}>{formatCostPer1k(m.costInputPer1k)}</span>
                        </td>
                        <td className="px-4 text-right">
                          <span className={cost}>{formatCostPer1k(m.costOutputPer1k)}</span>
                        </td>
                        <td className="px-4">
                          <Pill tone={best.tone}>{best.label}</Pill>
                        </td>
                        <td className="px-4 text-center">
                          <StatusDot ok={ok} loading={keysLoading} />
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-2 md:hidden" aria-label="Models">
          {visibleModels.length === 0 ? (
            <div className="surface-linear-card px-4 py-8 text-center text-[12.5px] text-(--color-text-tertiary-spec)">
              No models match the current filter.
            </div>
          ) : (
            visibleModels.map((model) => (
              <MobileModelCard
                key={model.id}
                model={model}
                keysStatus={keysStatus}
                keysLoading={keysLoading}
              />
            ))
          )}
        </section>

        {/* ------------------------------------------------------- recommended assignment */}
        <section className="surface-linear-card p-4">
          <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
            <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
              Recommended assignment
            </h2>
            <span className="text-[11.5px] text-(--color-text-tertiary-spec)">
              Default model per Plato stage
            </span>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {STAGE_ROWS.map(({ id, label, icon: Icon }) => {
              const modelId =
                stageOverrides[id] ?? RECOMMENDED_BY_STAGE[id];
              return (
                <div
                  key={id}
                  className="flex flex-wrap items-center gap-2 rounded-[6px] px-2 py-1.5 hover:bg-[rgba(255,255,255,0.02)]"
                >
                  <Icon
                    size={13}
                    strokeWidth={1.6}
                    className="shrink-0 text-(--color-text-tertiary-spec)"
                  />
                  <span className="w-20 shrink-0 text-[12.5px] text-(--color-text-secondary-spec)">
                    {label}
                  </span>
                  <span className="text-[12px] text-(--color-text-quaternary-spec)">→</span>
                  <div className="min-w-0 flex-1">
                    <ModelPickerCompact
                      value={modelId}
                      onChange={(next) => setStageModel(id, next)}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
