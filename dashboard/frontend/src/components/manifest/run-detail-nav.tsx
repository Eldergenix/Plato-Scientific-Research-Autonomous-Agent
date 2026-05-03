"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

interface RunDetailNavProps {
  runId: string;
}

interface NavItem {
  href: (runId: string) => string;
  label: string;
  testId: string;
  matches: (pathname: string, runId: string) => boolean;
}

const NAV_ITEMS: NavItem[] = [
  {
    href: (runId) => `/runs/${runId}`,
    label: "Overview",
    testId: "run-nav-overview",
    matches: (p, runId) => p === `/runs/${runId}`,
  },
  {
    href: (runId) => `/runs/${runId}/reviews`,
    label: "Reviews",
    testId: "run-nav-reviews",
    matches: (p, runId) => p.startsWith(`/runs/${runId}/reviews`),
  },
  {
    href: (runId) => `/runs/${runId}/research`,
    label: "Research",
    testId: "run-nav-research",
    matches: (p, runId) => p.startsWith(`/runs/${runId}/research`),
  },
  {
    href: (runId) => `/runs/${runId}/clarify`,
    label: "Clarify",
    testId: "run-nav-clarify",
    matches: (p, runId) => p.startsWith(`/runs/${runId}/clarify`),
  },
  {
    href: (runId) => `/runs/${runId}/literature`,
    label: "Literature",
    testId: "run-nav-literature",
    matches: (p, runId) => p.startsWith(`/runs/${runId}/literature`),
  },
  {
    href: (runId) => `/runs/${runId}/citations`,
    label: "Citations",
    testId: "run-nav-citations",
    matches: (p, runId) => p.startsWith(`/runs/${runId}/citations`),
  },
];

/**
 * Shared tab nav across the run-detail subroutes.
 *
 * Each tab maps to a sibling page under `src/app/runs/[runId]/<segment>/page.tsx`.
 * The active state is driven by `usePathname()` so users see which view they're on
 * regardless of which entry point they used to land here.
 */
export function RunDetailNav({ runId }: RunDetailNavProps) {
  const pathname = usePathname() ?? "";

  return (
    <nav
      aria-label="Run detail sections"
      data-testid="run-detail-nav"
      className="surface-linear-card flex flex-nowrap items-center gap-1 overflow-x-auto whitespace-nowrap px-2 py-1.5"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      {NAV_ITEMS.map((item) => {
        const active = item.matches(pathname, runId);
        return (
          <Link
            key={item.label}
            href={item.href(runId)}
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
