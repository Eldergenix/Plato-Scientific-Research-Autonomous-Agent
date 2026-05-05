"use client";

import * as React from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, ChevronDown, Search } from "lucide-react";
import type { ModelDef, Provider } from "@/lib/types";
import { MODELS, MODEL_GROUPS, MODELS_BY_ID } from "@/lib/models";
import { cn } from "@/lib/utils";

type AvailableProvider = "openai" | "gemini" | "anthropic" | "perplexity" | "semantic_scholar";

export interface ModelPickerProps {
  value: string;
  onChange: (id: string) => void;
  models?: ModelDef[];
  availableProviders?: Set<AvailableProvider>;
  recommendedFor?: "idea" | "method" | "results" | "paper" | "referee" | "literature";
  size?: "sm" | "md";
  label?: string;
  hint?: string;
}

// Per-stage recommendations. Hand-tuned defaults that map cmbagent best-fit
// models to each Plato stage.
const RECOMMENDED_BY_STAGE: Record<NonNullable<ModelPickerProps["recommendedFor"]>, string> = {
  idea: "gpt-4.1",
  method: "claude-4.1-opus",
  results: "gpt-5",
  paper: "gpt-4.1",
  referee: "claude-4.1-opus",
  literature: "gpt-4.1-mini",
};

// Provider dot color → status token. Anthropic uses the brand amber, the
// others mirror their Linear-style data-color tokens.
const PROVIDER_DOT_CLASS: Record<Provider, string> = {
  anthropic: "bg-(--color-status-amber-spec)",
  openai: "bg-(--color-status-green-spec)",
  gemini: "bg-(--color-status-blue)",
  perplexity: "bg-(--color-status-purple)",
  semantic_scholar: "bg-(--color-status-orange)",
};

const PROVIDER_ADD_KEY_LABEL: Record<Provider, string> = {
  anthropic: "Add Anthropic key",
  openai: "Add OpenAI key",
  gemini: "Add Google key",
  perplexity: "Add Perplexity key",
  semantic_scholar: "Add Semantic Scholar key",
};

function isExpensive(m: ModelDef): boolean {
  return (m.costInputPer1k ?? 0) >= 0.01 || (m.costOutputPer1k ?? 0) >= 0.05;
}

function isCheap(m: ModelDef): boolean {
  return (m.costInputPer1k ?? 0) <= 0.0005;
}

function formatCostHint(m: ModelDef): string | null {
  const inp = m.costInputPer1k;
  if (inp === undefined) return null;
  if (inp < 0.001) return `$${(inp * 1000).toFixed(2)}/M in`;
  return `$${inp.toFixed(3)}/1k in`;
}

function ProviderDot({ provider }: { provider: Provider }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-[7px] shrink-0 rounded-full", PROVIDER_DOT_CLASS[provider])}
    />
  );
}

// Badge tone classes mirror the Pill component's tone palette: tinted bg
// at /15-/12 alpha plus fg in the same brand/status token. Tailwind v4's
// arbitrary-property syntax pulls the alpha from the token directly.
const BADGE_TONE_CLASS: Record<"Recommended" | "Cheap" | "Strong", string> = {
  Recommended: "bg-(--color-brand-indigo)/15 text-(--color-brand-hover)",
  Cheap: "bg-(--color-status-green-spec)/12 text-(--color-status-green-spec)",
  Strong: "bg-(--color-status-purple)/12 text-(--color-status-purple)",
};

function ModelBadge({ kind }: { kind: "Recommended" | "Cheap" | "Strong" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[4px] px-1.5 text-[10px] font-medium leading-[16px]",
        BADGE_TONE_CLASS[kind],
      )}
    >
      {kind}
    </span>
  );
}

interface TriggerProps {
  selected: ModelDef | undefined;
  size: "sm" | "md";
  open: boolean;
}

const PickerTrigger = React.forwardRef<HTMLButtonElement, TriggerProps>(function PickerTrigger(
  { selected, size, open },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      data-state={open ? "open" : "closed"}
      className={cn(
        "inline-flex items-center gap-2 surface-ghost rounded-[6px] transition-colors",
        "data-[state=open]:bg-(--color-ghost-bg-hover) data-[state=open]:border-(--color-border-strong)",
        size === "sm" ? "h-7 px-2 text-[12px]" : "h-8 px-2.5 text-[13px]",
      )}
    >
      {selected ? (
        <>
          <ProviderDot provider={selected.provider} />
          <span className="text-(--color-text-primary) truncate max-w-[160px]">{selected.label}</span>
        </>
      ) : (
        <span className="text-(--color-text-tertiary)">Select model…</span>
      )}
      <ChevronDown
        size={12}
        strokeWidth={1.6}
        className="text-(--color-text-tertiary) ml-0.5 shrink-0"
      />
    </button>
  );
});

export function ModelPicker(props: ModelPickerProps) {
  const {
    value,
    onChange,
    models = MODELS,
    availableProviders,
    recommendedFor,
    size = "md",
    label,
    hint,
  } = props;
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");

  const selected = MODELS_BY_ID[value] as ModelDef | undefined;
  const recommendedId = recommendedFor ? RECOMMENDED_BY_STAGE[recommendedFor] : null;

  const isProviderAvailable = (p: Provider): boolean => {
    if (!availableProviders) return true;
    return availableProviders.has(p as AvailableProvider);
  };

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return models;
    return models.filter(
      (m) =>
        m.label.toLowerCase().includes(q) ||
        m.id.toLowerCase().includes(q) ||
        m.provider.toLowerCase().includes(q),
    );
  }, [models, query]);

  const grouped = React.useMemo(() => {
    return MODEL_GROUPS.map((g) => ({
      ...g,
      items: filtered.filter((m) => m.provider === g.provider),
    })).filter((g) => g.items.length > 0);
  }, [filtered]);

  return (
    <div className={cn("flex flex-col gap-1", size === "sm" && "gap-0.5")}>
      {label && (
        <span
          className={cn(
            "uppercase tracking-wider text-(--color-text-quaternary) font-medium",
            size === "sm" ? "text-[10px]" : "text-[11px]",
          )}
        >
          {label}
        </span>
      )}
      <DropdownMenu.Root open={open} onOpenChange={setOpen}>
        <DropdownMenu.Trigger asChild>
          <PickerTrigger selected={selected} size={size} open={open} />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="start"
            sideOffset={4}
            className="z-50 w-[320px] rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) shadow-(--shadow-dialog) overflow-hidden"
            onCloseAutoFocus={(e) => {
              e.preventDefault();
              setQuery("");
            }}
          >
            {/* Search */}
            <div className="hairline-b flex items-center gap-2 px-2.5 py-2">
              <Search size={12} strokeWidth={1.6} className="text-(--color-text-quaternary)" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search models or providers…"
                className="flex-1 bg-transparent text-[12.5px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary) outline-none"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="text-[10px] text-(--color-text-tertiary) hover:text-(--color-text-primary)"
                >
                  clear
                </button>
              )}
            </div>

            <div className="max-h-[340px] overflow-y-auto py-1">
              {grouped.length === 0 ? (
                <div className="px-3 py-6 text-center text-[12px] text-(--color-text-tertiary)">
                  No models match "{query}"
                </div>
              ) : (
                grouped.map((group) => {
                  const providerEnabled = isProviderAvailable(group.provider);
                  return (
                    <DropdownMenu.Group key={group.provider}>
                      <DropdownMenu.Label className="px-2.5 pt-2 pb-1 text-[10px] uppercase tracking-wider text-(--color-text-quaternary) font-medium flex items-center gap-1.5">
                        <ProviderDot provider={group.provider} />
                        {group.label}
                        {!providerEnabled && (
                          <span className="ml-auto text-[10px] normal-case tracking-normal text-(--color-text-quaternary)">
                            no key
                          </span>
                        )}
                      </DropdownMenu.Label>
                      {group.items.map((m) => {
                        const disabled = !providerEnabled;
                        const isSelected = value === m.id;
                        const isRecommended = recommendedId === m.id || m.notes === "Recommended";
                        const cheap = isCheap(m);
                        const strong = isExpensive(m) && !cheap;
                        return (
                          <DropdownMenu.Item
                            key={m.id}
                            disabled={disabled}
                            onSelect={(e) => {
                              if (disabled) {
                                e.preventDefault();
                                return;
                              }
                              onChange(m.id);
                            }}
                            className={cn(
                              "group/item relative flex items-center gap-2 px-2 py-1.5 mx-1 rounded-[5px] outline-none cursor-pointer",
                              "data-[highlighted]:bg-(--color-ghost-bg-hover)",
                              isSelected && "bg-(--color-bg-row-active)",
                              disabled && "opacity-50 cursor-not-allowed data-[highlighted]:bg-transparent",
                            )}
                          >
                            <span className="flex w-3.5 shrink-0 items-center justify-center">
                              {isSelected && (
                                <Check size={12} strokeWidth={2} className="text-(--color-brand-hover)" />
                              )}
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5">
                                <span className="text-[12.5px] text-(--color-text-primary) truncate">
                                  {m.label}
                                </span>
                                {isRecommended && <ModelBadge kind="Recommended" />}
                                {!isRecommended && cheap && <ModelBadge kind="Cheap" />}
                                {!isRecommended && strong && <ModelBadge kind="Strong" />}
                              </div>
                              {disabled && (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    // Soft hook: dispatch a custom event the host can listen for.
                                    window.dispatchEvent(
                                      new CustomEvent("plato:add-key", {
                                        detail: { provider: m.provider },
                                      }),
                                    );
                                  }}
                                  className="text-[10.5px] text-(--color-brand-hover) hover:underline mt-0.5"
                                >
                                  {PROVIDER_ADD_KEY_LABEL[m.provider]}
                                </button>
                              )}
                            </div>
                            <span className="shrink-0 font-mono text-[10.5px] text-(--color-text-quaternary) tabular-nums">
                              {formatCostHint(m) ?? ""}
                            </span>
                          </DropdownMenu.Item>
                        );
                      })}
                    </DropdownMenu.Group>
                  );
                })
              )}
            </div>

            {hint && (
              <div className="hairline-t px-2.5 py-1.5 text-[11px] text-(--color-text-tertiary)">
                {hint}
              </div>
            )}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  );
}

/**
 * Compact variant — just the trigger button without the field label, suitable
 * for inline tabular use (e.g. per-row model overrides in a config table).
 */
export function ModelPickerCompact(props: Omit<ModelPickerProps, "label">) {
  return <ModelPicker {...props} label={undefined} size={props.size ?? "sm"} />;
}
