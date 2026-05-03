import type { ModelDef, Provider } from "@/lib/types";

export type SortKey =
  | "label"
  | "provider"
  | "maxOutputTokens"
  | "costInputPer1k"
  | "costOutputPer1k";

export type SortDir = "asc" | "desc";

export type FilterTabId = "all" | "premium" | "cheap";

export const PROVIDER_LABEL: Record<Provider, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  gemini: "Google",
  perplexity: "Perplexity",
  semantic_scholar: "Semantic Scholar",
};

export const PROVIDER_COLOR: Record<Provider, string> = {
  anthropic: "#00738E",
  openai: "#27A644",
  gemini: "#4EA7FC",
  perplexity: "#bb87fc",
  semantic_scholar: "#ff7236",
};

export function isPremium(m: ModelDef): boolean {
  return (m.costInputPer1k ?? 0) >= 0.01 || (m.costOutputPer1k ?? 0) >= 0.05;
}

export function isCheap(m: ModelDef): boolean {
  return (m.costInputPer1k ?? 0) <= 0.0005;
}

export function formatTokensShort(n: number): string {
  if (n >= 1000) return `${Math.round(n / 1000)}k`;
  return `${n}`;
}

export function formatCostPer1k(v: number | undefined): string {
  if (v === undefined) return "—";
  if (v < 0.001) return `$${v.toFixed(5)} / 1k`;
  if (v < 0.01) return `$${v.toFixed(4)} / 1k`;
  return `$${v.toFixed(3)} / 1k`;
}

export function bestForFor(m: ModelDef): {
  tone: "indigo" | "green" | "lavender" | "amber" | "neutral";
  label: string;
} {
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

function compareModels(a: ModelDef, b: ModelDef, key: SortKey, dir: SortDir): number {
  const sign = dir === "asc" ? 1 : -1;
  switch (key) {
    case "label":
      return a.label.localeCompare(b.label) * sign;
    case "provider":
      return (
        (PROVIDER_LABEL[a.provider].localeCompare(PROVIDER_LABEL[b.provider]) ||
          a.label.localeCompare(b.label)) * sign
      );
    case "maxOutputTokens":
      return (a.maxOutputTokens - b.maxOutputTokens) * sign;
    case "costInputPer1k":
      return ((a.costInputPer1k ?? 0) - (b.costInputPer1k ?? 0)) * sign;
    case "costOutputPer1k":
      return ((a.costOutputPer1k ?? 0) - (b.costOutputPer1k ?? 0)) * sign;
    default:
      return 0;
  }
}

export function filterAndSortModels(
  models: ReadonlyArray<ModelDef>,
  filter: FilterTabId,
  query: string,
  sortKey: SortKey,
  sortDir: SortDir,
): ModelDef[] {
  const q = query.trim().toLowerCase();
  let list = models.slice();
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
  list.sort((a, b) => compareModels(a, b, sortKey, sortDir));
  return list;
}
