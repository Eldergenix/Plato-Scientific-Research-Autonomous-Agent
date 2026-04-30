"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink, Search } from "lucide-react";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

export interface LicenseDistribution {
  name: string;
  version: string;
  license: string | null;
  gpl3_compatible: boolean;
  source_url: string | null;
}

type SortKey = "name" | "version" | "license" | "compatibility";
type SortDirection = "asc" | "desc";

const COLUMN_DEFS: ReadonlyArray<{
  key: SortKey;
  label: string;
  width: string;
  align?: "left" | "right";
}> = [
  { key: "name", label: "Name", width: "32%" },
  { key: "version", label: "Version", width: "14%" },
  { key: "license", label: "License", width: "30%" },
  { key: "compatibility", label: "Compatibility", width: "24%" },
];

function compareNullableString(a: string | null, b: string | null): number {
  // null sorts last regardless of direction toggling — keeps unknowns
  // grouped at the bottom on ascending name+license sorts and at the
  // top on descending. This matches what users expect from "?" rows.
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return a.localeCompare(b);
}

function compareCompatibility(a: LicenseDistribution, b: LicenseDistribution): number {
  // Custom order: compatible (1) > unknown (0) > incompatible (-1).
  // Unknowns sit between the two bools so ascending sort surfaces
  // explicit failures first.
  const score = (d: LicenseDistribution) =>
    d.license === null ? 0 : d.gpl3_compatible ? 1 : -1;
  return score(a) - score(b);
}

function compareDists(
  a: LicenseDistribution,
  b: LicenseDistribution,
  key: SortKey,
): number {
  switch (key) {
    case "name":
      return a.name.localeCompare(b.name);
    case "version":
      // String compare is fine here — version strings are not always
      // semver and a localeCompare with numeric:true gives a usable
      // ordering for both "2.31.0" and "1.0.0a1".
      return a.version.localeCompare(b.version, undefined, { numeric: true });
    case "license":
      return compareNullableString(a.license, b.license);
    case "compatibility":
      return compareCompatibility(a, b);
  }
}

function CompatibilityCell({ dist }: { dist: LicenseDistribution }) {
  if (dist.license === null) {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-(--color-text-tertiary)"
        title="Unknown — license metadata could not be parsed"
      >
        <span aria-hidden className="font-mono text-[14px]">
          ?
        </span>
        <span>Unknown</span>
      </span>
    );
  }
  if (dist.gpl3_compatible) {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-(--color-status-emerald)"
        title="Compatible with GPLv3"
      >
        <span aria-hidden className="font-mono text-[14px]">
          ✓
        </span>
        <span>Compatible</span>
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 text-(--color-status-red)"
      title="Incompatible with GPLv3"
    >
      <span aria-hidden className="font-mono text-[14px]">
        ✗
      </span>
      <span>Incompatible</span>
    </span>
  );
}

function LicenseBadge({ dist }: { dist: LicenseDistribution }) {
  if (dist.license === null) {
    return <Pill tone="neutral">unknown</Pill>;
  }
  return (
    <Pill tone={dist.gpl3_compatible ? "green" : "red"}>{dist.license}</Pill>
  );
}

function SortIcon({
  active,
  direction,
}: {
  active: boolean;
  direction: SortDirection;
}) {
  if (!active) {
    return <ArrowUpDown size={11} className="opacity-50" />;
  }
  return direction === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />;
}

export function LicenseTable({
  distributions,
}: {
  distributions: LicenseDistribution[];
}) {
  const [query, setQuery] = React.useState("");
  const [sortKey, setSortKey] = React.useState<SortKey>("name");
  const [sortDir, setSortDir] = React.useState<SortDirection>("asc");

  const onHeaderClick = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const filteredAndSorted = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? distributions.filter((d) => d.name.toLowerCase().includes(q))
      : distributions;
    const sorted = [...filtered].sort((a, b) => compareDists(a, b, sortKey));
    return sortDir === "asc" ? sorted : sorted.reverse();
  }, [distributions, query, sortKey, sortDir]);

  if (distributions.length === 0) {
    return (
      <section
        className="surface-linear-card flex flex-col items-center justify-center gap-2 py-12 px-6 text-center"
        data-testid="license-table-empty"
        style={{ border: "1px solid var(--color-border-card)" }}
      >
        <p className="text-[13px] text-(--color-text-row-meta) max-w-md">
          No distributions found — the license audit returned an empty set.
        </p>
      </section>
    );
  }

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="license-table"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="flex items-center gap-3">
          <h2
            className="text-(--color-text-primary-strong) text-[15px]"
            style={{ fontWeight: 510 }}
          >
            Distributions
          </h2>
          <span className="text-[12px] text-(--color-text-row-meta) tabular-nums">
            {filteredAndSorted.length} of {distributions.length}
          </span>
        </div>
        <label className="relative flex items-center">
          <Search
            size={12}
            className="pointer-events-none absolute left-2.5 text-(--color-text-tertiary)"
          />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by name…"
            data-testid="license-table-search"
            className={cn(
              "h-7 rounded-[6px] border bg-(--color-bg-card) pl-7 pr-2 text-[12px]",
              "border-(--color-border-card) text-(--color-text-primary)",
              "placeholder:text-(--color-text-tertiary)",
              "focus:outline-none focus:ring-2 focus:ring-(--color-brand-interactive) focus:ring-offset-1 focus:ring-offset-(--color-bg-card)",
            )}
          />
        </label>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr
              className="text-left text-(--color-text-tertiary)"
              style={{ borderBottom: "1px solid var(--color-border-standard)" }}
            >
              {COLUMN_DEFS.map((col) => {
                const active = sortKey === col.key;
                return (
                  <th
                    key={col.key}
                    style={{ width: col.width }}
                    className="font-label px-4 py-2"
                  >
                    <button
                      type="button"
                      onClick={() => onHeaderClick(col.key)}
                      data-testid={`license-table-sort-${col.key}`}
                      aria-sort={
                        active
                          ? sortDir === "asc"
                            ? "ascending"
                            : "descending"
                          : "none"
                      }
                      className={cn(
                        "inline-flex items-center gap-1.5 transition-colors",
                        active
                          ? "text-(--color-text-primary)"
                          : "hover:text-(--color-text-secondary)",
                      )}
                    >
                      {col.label}
                      <SortIcon active={active} direction={sortDir} />
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {filteredAndSorted.length === 0 ? (
              <tr>
                <td
                  colSpan={COLUMN_DEFS.length}
                  className="px-4 py-8 text-center text-[12px] text-(--color-text-row-meta)"
                  data-testid="license-table-no-matches"
                >
                  No distributions match “{query}”.
                </td>
              </tr>
            ) : (
              filteredAndSorted.map((d) => (
                <tr
                  key={`${d.name}@${d.version}`}
                  className="text-(--color-text-row-title) hover:bg-(--color-ghost-bg-hover)"
                  style={{ borderBottom: "1px solid var(--color-border-standard)" }}
                  data-testid="license-table-row"
                >
                  <td className="px-4 py-2 align-middle">
                    {d.source_url ? (
                      <a
                        href={d.source_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className={cn(
                          "inline-flex items-center gap-1 font-mono",
                          "text-(--color-brand-interactive) hover:underline",
                        )}
                      >
                        {d.name}
                        <ExternalLink size={10} />
                      </a>
                    ) : (
                      <span className="font-mono">{d.name}</span>
                    )}
                  </td>
                  <td className="px-4 py-2 align-middle font-mono tabular-nums text-(--color-text-row-meta)">
                    {d.version}
                  </td>
                  <td className="px-4 py-2 align-middle">
                    <LicenseBadge dist={d} />
                  </td>
                  <td className="px-4 py-2 align-middle">
                    <CompatibilityCell dist={d} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
