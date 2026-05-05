"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";

interface RunDetailNavProps {
  runId: string;
}

interface NavItem {
  // Path segment under /runs/, no leading slash. Empty string is the
  // overview tab at /runs.
  segment: "" | "reviews" | "research" | "clarify" | "literature" | "citations";
  label: string;
  testId: string;
}

const NAV_ITEMS: NavItem[] = [
  { segment: "", label: "Overview", testId: "run-nav-overview" },
  { segment: "reviews", label: "Reviews", testId: "run-nav-reviews" },
  { segment: "research", label: "Research", testId: "run-nav-research" },
  { segment: "clarify", label: "Clarify", testId: "run-nav-clarify" },
  { segment: "literature", label: "Literature", testId: "run-nav-literature" },
  { segment: "citations", label: "Citations", testId: "run-nav-citations" },
];

function buildHref(segment: NavItem["segment"], runId: string): string {
  const base = segment ? `/runs/${segment}` : "/runs";
  return runId ? `${base}?runId=${encodeURIComponent(runId)}` : base;
}

function isActive(
  pathname: string,
  segment: NavItem["segment"],
  currentRunId: string,
  navRunId: string,
): boolean {
  // Only highlight the active tab when we're rendering the nav for the
  // run id that matches the URL's ?runId=. Otherwise multiple tabs
  // could light up if the URL changes underneath us.
  if (currentRunId !== navRunId) return false;
  if (segment === "") return pathname === "/runs" || pathname === "/runs/";
  return pathname.startsWith(`/runs/${segment}`);
}

/**
 * Shared tab nav across the run-detail subroutes.
 *
 * Each tab maps to a sibling page under `src/app/runs/<segment>/page.tsx`.
 * Run id travels in `?runId=` because static export can't enumerate
 * dynamic IDs at build time. Active state checks the URL ?runId= so we
 * don't highlight tabs for an unrelated run.
 */
export function RunDetailNav({ runId }: RunDetailNavProps) {
  const pathname = usePathname() ?? "";
  const sp = useSearchParams();
  const currentRunId = sp?.get("runId") ?? "";

  return (
    <nav
      aria-label="Run detail sections"
      data-testid="run-detail-nav"
      className="surface-linear-card flex flex-nowrap items-center gap-1 overflow-x-auto whitespace-nowrap px-2 py-1.5"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item.segment, currentRunId, runId);
        return (
          <Link
            key={item.label}
            href={buildHref(item.segment, runId)}
            data-testid={item.testId}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-[6px] px-2.5 py-1 text-[12.5px] transition-colors",
              active
                ? "bg-(--color-bg-pill-active) text-(--color-text-primary-strong)"
                : "text-(--color-text-tertiary-spec) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
