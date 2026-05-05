"use client";

import * as React from "react";
import {
  Bell,
  Filter,
  Lightbulb,
  MoreHorizontal,
  PanelRightOpen,
  Pause,
  Play,
  SlidersHorizontal,
  Square,
  Star,
  Wallet,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { TabPills } from "@/components/shell/tab-pills";
import { cn, formatCost, formatTokens } from "@/lib/utils";
import type { Project } from "@/lib/types";

/* -----------------------------------------------------------------------------
 * Types
 * ---------------------------------------------------------------------------*/

export type TopBarFilterTab = "active" | "backlog" | "all";

export interface TopBarProps {
  project: Project;
  filterTab: TopBarFilterTab;
  onChangeFilter: (tab: TopBarFilterTab) => void;
  onCancelRun?: () => void;
  onPauseRun?: () => void;
  onOpenCostMeter?: () => void;
  onAddFilter?: () => void;
  onChangeDisplay?: () => void;
  onToggleDetails?: () => void;
  onMoreActions?: () => void;
  onRunPipeline?: () => void;
  /** Disabled-state tooltip surfaced on the Run-pipeline button when truthy. */
  runPipelineDisabledReason?: string;
  onToggleFavorite?: () => void;
  onOpenNotifications?: () => void;
  isFavorite?: boolean;
  /** Elapsed milliseconds since the active run started, for live duration. */
  elapsedMs?: number;
}

/* -----------------------------------------------------------------------------
 * Constants
 * ---------------------------------------------------------------------------*/

const TABS: ReadonlyArray<{ id: TopBarFilterTab; label: string }> = [
  { id: "active", label: "Active" },
  { id: "backlog", label: "Backlog" },
  { id: "all", label: "All" },
] as const;

const PROJECT_NAME_MAX = 40;

/* -----------------------------------------------------------------------------
 * Subcomponents
 * ---------------------------------------------------------------------------*/

/**
 * 16x16 Plato glyph — a pink (#FF0080) Lightbulb. Sits inside a 16x24
 * container so vertical centering matches Linear's logo alignment.
 */
function PlatoLogoMark() {
  return (
    <span
      aria-hidden
      className="flex items-center justify-center"
      style={{ width: 16, height: 24, color: "var(--color-status-pink)" }}
    >
      <Lightbulb size={16} strokeWidth={1.75} />
    </span>
  );
}

/**
 * 28x28 ghost icon button used in row 1 (favorites, notifications).
 * No background by default; light glass fill on hover.
 */
const Row1IconButton = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    pressed?: boolean;
    icon: React.ReactNode;
  }
>(({ className, pressed, icon, ...props }, ref) => {
  return (
    <button
      ref={ref}
      type="button"
      aria-pressed={pressed}
      className={cn(
        "inline-flex items-center justify-center size-7 rounded-full",
        "text-(--color-text-tertiary-spec) bg-transparent",
        "transition-colors duration-100 ease-out",
        "hover:bg-[rgba(255,255,255,0.05)] hover:text-(--color-text-primary-strong)",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
        pressed && "text-(--color-text-primary-strong)",
        className,
      )}
      {...props}
    >
      {icon}
    </button>
  );
});
Row1IconButton.displayName = "Row1IconButton";

/**
 * 28x28 wrapper containing a 27x27 glass-filled button. Spec calls for a
 * "shadow ring" outside the inner pill — we render the shadow on the inner
 * surface (visible inside the 0.5px gutter created by the wrapper).
 */
const GlassIconButton = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    icon: React.ReactNode;
    label: string;
  }
>(({ className, icon, label, ...props }, ref) => {
  return (
    <span
      className="inline-flex items-center justify-center size-7 rounded-full p-[0.5px]"
      style={{ flex: "none" }}
    >
      <button
        ref={ref}
        type="button"
        aria-label={label}
        className={cn(
          "inline-flex items-center justify-center rounded-full",
          "size-[27px] bg-(--color-bg-button-glass)",
          "text-(--color-text-row-meta)",
          "shadow-[var(--shadow-glass)]",
          "transition-colors duration-100 ease-out",
          "hover:bg-[#232325] hover:text-(--color-text-primary-strong)",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
          className,
        )}
        {...props}
      >
        {icon}
      </button>
    </span>
  );
});
GlassIconButton.displayName = "GlassIconButton";

/**
 * Cost meter pill — Wallet icon + $X.XX · Yk tok.
 */
function CostMeter({
  costCents,
  tokens,
  onClick,
}: {
  costCents: number;
  tokens: number;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Open cost meter"
      className={cn(
        "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full",
        "bg-(--color-bg-button-glass) text-(--color-text-row-meta)",
        "shadow-[var(--shadow-glass)]",
        "text-[12px] font-medium leading-none",
        "transition-colors duration-100 ease-out",
        "hover:bg-[#232325] hover:text-(--color-text-primary-strong)",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
      )}
    >
      <Wallet size={12} strokeWidth={1.5} />
      <span className="font-mono tabular-nums text-(--color-text-secondary-spec)">
        {formatCost(costCents)}
      </span>
      <span className="text-(--color-text-quaternary-spec)">·</span>
      <span className="font-mono tabular-nums">
        {formatTokens(tokens)} tok
      </span>
    </button>
  );
}

/**
 * Pill-shaped "Run pipeline" primary button using brand indigo.
 *
 * Pass ``disabledReason`` to render the button in a disabled state with
 * the reason surfaced as a native ``title`` tooltip — used by callers
 * that detect missing API keys, demo-mode budget exhaustion, etc.
 */
function RunPipelineButton({
  onClick,
  disabledReason,
}: {
  onClick?: () => void;
  disabledReason?: string;
}) {
  const disabled = Boolean(disabledReason);
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      title={disabledReason}
      aria-disabled={disabled || undefined}
      data-testid="run-pipeline-button"
      className={cn(
        "inline-flex items-center gap-1.5 h-7 px-3 rounded-full",
        "bg-(--color-brand-indigo) text-white",
        "text-[12px] font-medium leading-none",
        "shadow-[var(--shadow-elevated)]",
        "transition-colors duration-100 ease-out",
        "hover:bg-(--color-brand-interactive)",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
        "focus-visible:ring-offset-2 focus-visible:ring-offset-(--color-bg-page)",
        "disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-(--color-brand-indigo)",
      )}
    >
      <Play size={12} strokeWidth={1.75} />
      Run pipeline
    </button>
  );
}

/* -----------------------------------------------------------------------------
 * TopBar
 * ---------------------------------------------------------------------------*/

/**
 * Linear-style two-row top bar.
 *
 * Row 1 (h=44): logo + project name + favorites/notifications | cost meter +
 *   run controls + more.
 * Row 2 (h=43.5): filter tab pills + flexible spacer | filter / display /
 *   details glass icon buttons.
 *
 * Total height ≈ 87.5px. Sticks to the top of the viewport.
 */
export function TopBar({
  project,
  filterTab,
  onChangeFilter,
  onCancelRun,
  onPauseRun,
  onOpenCostMeter,
  onAddFilter,
  onChangeDisplay,
  onToggleDetails,
  onMoreActions,
  onRunPipeline,
  runPipelineDisabledReason,
  onToggleFavorite,
  onOpenNotifications,
  isFavorite,
  elapsedMs: _elapsedMs,
}: TopBarProps) {
  const running = project.activeRun;
  const t = useTranslations("topbar");

  const truncatedName =
    project.name.length > PROJECT_NAME_MAX
      ? `${project.name.slice(0, PROJECT_NAME_MAX - 1)}…`
      : project.name;

  return (
    <header
      role="banner"
      className="sticky top-0 z-30 bg-(--color-bg-page)"
    >
      {/* -------------------------- Row 1 -------------------------- */}
      <div
        className={cn(
          "flex items-center justify-between gap-1.5",
          "h-11 px-2",
          "border-b border-[#1D1D1F]",
        )}
        style={{ borderBottomWidth: "0.5px" }}
      >
        {/* Left: logo + name + favorites + notifications */}
        <div className="flex items-center gap-1.5 min-w-0">
          <PlatoLogoMark />

          <h1
            className={cn(
              "truncate min-w-0",
              "text-[13px] leading-4 font-medium tracking-[-0.01em]",
              "text-(--color-text-workspace)",
            )}
            title={project.name}
            style={{ maxWidth: 320 }}
          >
            {truncatedName}
          </h1>

          <Row1IconButton
            aria-label={isFavorite ? "Remove favorite" : "Add favorite"}
            pressed={isFavorite}
            onClick={onToggleFavorite}
            icon={
              <Star
                size={14}
                strokeWidth={1.5}
                fill={isFavorite ? "currentColor" : "none"}
              />
            }
          />

          <Row1IconButton
            aria-label={t("notifications")}
            onClick={onOpenNotifications}
            icon={<Bell size={14} strokeWidth={1.5} />}
          />
        </div>

        {/* Right: cost meter + run controls + more.
            Note: Linear's spec leaves this side empty (breadcrumb/share),
            but Plato's pipeline-runner UX needs run controls visible at all
            times, so we surface them here. */}
        <div className="flex items-center gap-1.5">
          <CostMeter
            costCents={project.totalCostCents}
            tokens={project.totalTokens}
            onClick={onOpenCostMeter}
          />

          {running ? (
            <>
              {onPauseRun && (
                <Button
                  variant="ghost"
                  size="iconSm"
                  aria-label="Pause run"
                  onClick={onPauseRun}
                >
                  <Pause size={13} strokeWidth={1.5} />
                </Button>
              )}
              {onCancelRun && (
                <Button
                  variant="danger"
                  size="iconSm"
                  aria-label="Cancel run"
                  onClick={onCancelRun}
                >
                  <Square size={12} strokeWidth={1.5} />
                </Button>
              )}
            </>
          ) : (
            <RunPipelineButton
              onClick={onRunPipeline}
              disabledReason={runPipelineDisabledReason}
            />
          )}

          <Row1IconButton
            aria-label="More actions"
            onClick={onMoreActions}
            icon={<MoreHorizontal size={14} strokeWidth={1.5} />}
          />
        </div>
      </div>

      {/* -------------------------- Row 2 -------------------------- */}
      <div
        className={cn(
          "flex items-center justify-between gap-1.5",
          "px-2",
        )}
        style={{ height: "43.5px", paddingTop: "2px", paddingBottom: "2px" }}
      >
        {/* Left: tab pills + flexible spacer */}
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          <TabPills
            tabs={TABS}
            activeId={filterTab}
            onSelect={(id) => onChangeFilter(id as TopBarFilterTab)}
            ariaLabel="Issue list filter"
          />
          <div aria-hidden className="flex-1" />
        </div>

        {/* Right: 3 glass icon buttons */}
        <div className="flex items-center gap-1.5">
          <GlassIconButton
            label="Add filter"
            onClick={onAddFilter}
            icon={
              <Filter
                size={14}
                strokeWidth={1.5}
                className="text-(--color-text-row-meta)"
              />
            }
          />
          <GlassIconButton
            label="Display options"
            onClick={onChangeDisplay}
            icon={
              <SlidersHorizontal
                size={14}
                strokeWidth={1.5}
                className="text-(--color-text-row-meta)"
              />
            }
          />
          <GlassIconButton
            label="Open details panel"
            onClick={onToggleDetails}
            icon={
              <PanelRightOpen
                size={14}
                strokeWidth={1.5}
                className="text-(--color-text-row-meta)"
              />
            }
          />
        </div>
      </div>
    </header>
  );
}
