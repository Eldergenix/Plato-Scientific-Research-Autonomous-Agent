"use client";

import * as React from "react";
import {
  BooksIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  ClockCounterClockwiseIcon,
  CodeIcon,
  CoinsIcon,
  CrownIcon,
  DatabaseIcon,
  FileTextIcon,
  FunnelIcon,
  ListChecksIcon,
  MicroscopeIcon,
  NewspaperIcon,
  PlugsConnectedIcon,
  RowsIcon,
  SparkleIcon,
  StampIcon,
  StackIcon,
  TestTubeIcon,
  WarningCircleIcon,
  WrenchIcon,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

export interface TabPillItem {
  id: string;
  label: string;
  icon?: Icon;
}

const TAB_ICON_BY_KEY: Record<string, Icon> = {
  active: CircleNotchIcon,
  "all events": RowsIcon,
  "all time": ClockCounterClockwiseIcon,
  all: StackIcon,
  backlog: ListChecksIcon,
  cheap: CoinsIcon,
  completed: CheckCircleIcon,
  "custom mcp": CodeIcon,
  data: DatabaseIcon,
  edits: SparkleIcon,
  errors: WarningCircleIcon,
  experiments: TestTubeIcon,
  mcp: PlugsConnectedIcon,
  month: ClockCounterClockwiseIcon,
  papers: FileTextIcon,
  premium: CrownIcon,
  references: BooksIcon,
  research: MicroscopeIcon,
  runs: CircleNotchIcon,
  stamp: StampIcon,
  summary: NewspaperIcon,
  today: ClockCounterClockwiseIcon,
  tools: WrenchIcon,
  week: ClockCounterClockwiseIcon,
};

function resolveTabIcon(tab: TabPillItem): Icon {
  return (
    tab.icon ??
    TAB_ICON_BY_KEY[tab.id] ??
    TAB_ICON_BY_KEY[tab.label.toLowerCase()] ??
    FunnelIcon
  );
}

export interface TabPillsProps {
  tabs: ReadonlyArray<TabPillItem>;
  activeId: string;
  onSelect: (id: string) => void;
  className?: string;
  ariaLabel?: string;
}

/**
 * TabPills — Linear.app-style horizontal tab pills.
 *
 * Visual spec (per Linear Figma export):
 * - Each pill: height 27px, padding 6.25px 10px, border-radius 9999px,
 *   font Inter 500 12px / 15px line-height.
 * - Inactive: bg #141415 (var(--color-bg-pill-inactive)), text #949496
 *   (var(--color-text-row-meta)), shadow-glass.
 * - Active: bg #202021 (var(--color-bg-pill-active)), text #ffffff
 *   (var(--color-text-primary-strong)), shadow-glass-active.
 * - Hover (inactive): brighten text to #ffffff.
 *
 * Behavior: roving-tabindex tablist with arrow-key navigation; calls
 * `onSelect(id)` on click or Enter/Space. Each pill renders as a button
 * with role="tab" and aria-selected reflecting active state.
 */
export function TabPills({
  tabs,
  activeId,
  onSelect,
  className,
  ariaLabel = "Filter tabs",
}: TabPillsProps) {
  const refs = React.useRef<Array<HTMLButtonElement | null>>([]);

  const handleKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const dir = event.key === "ArrowRight" ? 1 : -1;
    const next = (index + dir + tabs.length) % tabs.length;
    refs.current[next]?.focus();
    onSelect(tabs[next].id);
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn("flex items-center gap-1.5", className)}
    >
      {tabs.map((tab, i) => {
        const isActive = tab.id === activeId;
        const Icon = resolveTabIcon(tab);
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            aria-selected={isActive}
            data-state={isActive ? "active" : "inactive"}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onSelect(tab.id)}
            onKeyDown={(e) => handleKeyDown(e, i)}
            className={cn(
              "inline-flex items-center justify-center select-none",
              "h-[27px] px-2.5 rounded-full",
              "text-[12px] leading-[15px] font-medium tracking-[-0.01em]",
              "transition-[background-color,color,box-shadow] duration-100 ease-out",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
              isActive
                ? "bg-(--color-bg-pill-active) text-(--color-text-primary-strong) shadow-[var(--shadow-glass-active)]"
                : "bg-(--color-bg-pill-inactive) text-(--color-text-row-meta) shadow-[var(--shadow-glass)] hover:text-(--color-text-primary-strong)",
            )}
            style={{ paddingTop: "6.25px", paddingBottom: "6.25px" }}
          >
            <Icon
              aria-hidden
              size={12}
              weight={isActive ? "fill" : "regular"}
              className="mr-1.5 shrink-0"
            />
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
