"use client";

import * as React from "react";
import {
  Lightbulb,
  BookMarked,
  ClipboardList,
  FlaskConical,
  Newspaper,
  Stamp,
} from "lucide-react";
import { api, type KeysStatus } from "@/lib/api";
import { MODELS } from "@/lib/models";
import { ModelPickerCompact } from "@/components/ui/model-picker";
import { ModelFilterBar } from "@/components/models/ModelFilterBar";
import { ModelTable } from "@/components/models/ModelTable";
import { ProviderStatusHeader } from "@/components/models/ProviderStatusHeader";
import {
  filterAndSortModels,
  type FilterTabId,
  type SortDir,
  type SortKey,
} from "@/components/models/sort";

// Per-stage default mapping. Mirrors RECOMMENDED_BY_STAGE in model-picker.tsx
// but tuned per the dashboard product brief for the Models settings page.
const RECOMMENDED_BY_STAGE: Record<
  "idea" | "literature" | "method" | "results" | "paper" | "referee",
  string
> = {
  idea: "gpt-4.1",
  literature: "gpt-4.1-mini",
  method: "claude-4.1-opus",
  results: "gpt-5",
  paper: "claude-4.1-opus",
  referee: "o3-mini",
};

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

export default function ModelsPage() {
  const [keysStatus, setKeysStatus] = React.useState<KeysStatus | null>(null);
  const [keysLoading, setKeysLoading] = React.useState(true);
  const [filter, setFilter] = React.useState<FilterTabId>("all");
  const [query, setQuery] = React.useState("");
  const [sortKey, setSortKey] = React.useState<SortKey>("provider");
  const [sortDir, setSortDir] = React.useState<SortDir>("asc");

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

  const onSort = React.useCallback(
    (key: SortKey) => {
      if (key === sortKey) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("asc");
      }
    },
    [sortKey],
  );

  const sortedRows = React.useMemo(
    () => filterAndSortModels(MODELS, filter, query, sortKey, sortDir),
    [filter, query, sortKey, sortDir],
  );

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-7xl space-y-4">
        <ProviderStatusHeader keysStatus={keysStatus} keysLoading={keysLoading} />
        <ModelFilterBar
          filter={filter}
          onFilterChange={setFilter}
          query={query}
          onQueryChange={setQuery}
        />
        <ModelTable
          rows={sortedRows}
          keysStatus={keysStatus}
          keysLoading={keysLoading}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={onSort}
        />

        <section className="surface-linear-card p-4">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
              Recommended assignment
            </h2>
            <span className="text-[11.5px] text-(--color-text-tertiary-spec)">
              Default model per Plato stage
            </span>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {STAGE_ROWS.map(({ id, label, icon: Icon }) => {
              const modelId = RECOMMENDED_BY_STAGE[id];
              return (
                <div
                  key={id}
                  className="flex items-center gap-2 rounded-[6px] px-2 py-1.5 hover:bg-[rgba(255,255,255,0.02)]"
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
                  <ModelPickerCompact value={modelId} onChange={() => {}} />
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
