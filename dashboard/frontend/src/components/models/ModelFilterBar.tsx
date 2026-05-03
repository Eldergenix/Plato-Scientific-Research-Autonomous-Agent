import * as React from "react";
import { Filter, Search } from "lucide-react";
import { TabPills } from "@/components/shell/tab-pills";
import { cn } from "@/lib/utils";
import type { FilterTabId } from "./sort";

const FILTER_TABS = [
  { id: "all", label: "All" },
  { id: "premium", label: "Premium" },
  { id: "cheap", label: "Cheap" },
] as const;

export function ModelFilterBar({
  filter,
  onFilterChange,
  query,
  onQueryChange,
}: {
  filter: FilterTabId;
  onFilterChange: (id: FilterTabId) => void;
  query: string;
  onQueryChange: (q: string) => void;
}) {
  return (
    <div className="flex h-8 items-center gap-1.5 px-4">
      <Filter
        size={12}
        strokeWidth={1.6}
        className="text-(--color-text-quaternary-spec) shrink-0"
      />
      <TabPills
        tabs={FILTER_TABS as unknown as ReadonlyArray<{ id: string; label: string }>}
        activeId={filter}
        onSelect={(id) => onFilterChange(id as FilterTabId)}
        ariaLabel="Filter models by tier"
      />
      <div className="ml-auto flex items-center gap-1.5">
        <div className="relative">
          <Search
            size={11}
            strokeWidth={1.6}
            className="absolute left-2 top-1/2 -translate-y-1/2 text-(--color-text-quaternary-spec)"
          />
          <input
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Search model or provider…"
            className={cn(
              "h-6 w-[220px] rounded-[6px] pl-6 pr-2 font-mono text-[12px]",
              "bg-[#141415] border border-[#262628] text-(--color-text-primary)",
              "placeholder:text-(--color-text-quaternary-spec)",
              "focus:outline-none focus:border-(--color-brand-indigo)",
            )}
          />
        </div>
      </div>
    </div>
  );
}
