import * as React from "react";
import { ArrowUpDown, ChevronDown, ChevronUp } from "lucide-react";
import type { KeysStatus } from "@/lib/api";
import type { ModelDef } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ModelTableRow } from "./ModelTableRow";
import { providerHasKey } from "./ProviderStatusHeader";
import type { SortDir, SortKey } from "./sort";

const COLUMNS: Array<{
  label: string;
  key: SortKey | null;
  align: "left" | "right" | "center";
}> = [
  { label: "Model", key: "label", align: "left" },
  { label: "Provider", key: "provider", align: "left" },
  { label: "Max output", key: "maxOutputTokens", align: "right" },
  { label: "Input cost", key: "costInputPer1k", align: "right" },
  { label: "Output cost", key: "costOutputPer1k", align: "right" },
  { label: "Best for", key: null, align: "left" },
  { label: "Status", key: null, align: "center" },
];

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
  direction: SortDir;
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
          className={cn(
            "shrink-0",
            active ? "text-(--color-text-primary-strong)" : "text-(--color-text-quaternary-spec)",
          )}
        />
      )}
    </button>
  );
}

export function ModelTable({
  rows,
  keysStatus,
  keysLoading,
  sortKey,
  sortDir,
  onSort,
}: {
  rows: ReadonlyArray<ModelDef>;
  keysStatus: KeysStatus | null;
  keysLoading: boolean;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
}) {
  return (
    <section className="surface-linear-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full table-fixed border-collapse">
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
              {COLUMNS.map(({ label, key, align }) => (
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
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={COLUMNS.length}
                  className="px-4 py-8 text-center text-[12.5px] text-(--color-text-tertiary-spec)"
                >
                  No models match the current filter.
                </td>
              </tr>
            ) : (
              rows.map((m) => (
                <ModelTableRow
                  key={m.id}
                  model={m}
                  hasKey={providerHasKey(m.provider, keysStatus)}
                  keysLoading={keysLoading}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
