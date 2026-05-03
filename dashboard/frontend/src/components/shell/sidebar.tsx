"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Inbox,
  LayoutList,
  Compass,
  Folder,
  Eye,
  PlusCircle,
  HelpCircle,
  Plus,
  Search,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  History,
  Stamp,
  Lightbulb,
  BookMarked,
  ClipboardList,
  Newspaper,
  Activity,
  KeyRound,
  Moon,
  Sun,
  Monitor,
  Repeat,
  Settings as SettingsIcon,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/components/shell/theme-provider";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  onOpenCommand: () => void;
  projectName?: string;
  activeStage?: string;
  onSelectStage?: (stage: string) => void;
  onCreateProject?: () => void;
}

interface NavLink {
  href: string;
  label: string;
  icon: LucideIcon;
}

const TOP_LINKS: NavLink[] = [
  { href: "/", label: "Workspace", icon: Inbox },
  { href: "/projects", label: "My projects", icon: LayoutList },
];

const WORKSPACE_LINKS: NavLink[] = [
  { href: "/projects", label: "Projects", icon: Compass },
  { href: "/models", label: "Models", icon: Folder },
  { href: "/costs", label: "Costs", icon: Eye },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/loop", label: "Autonomous loop", icon: Repeat },
  { href: "/keys", label: "Keys", icon: KeyRound },
  // Settings is also reachable via the bottom-bar gear, but keeping a
  // labelled nav entry here ensures /settings can be a destination
  // search results route to and that the active-state highlighting in
  // the workspace list doesn't disappear once the user lands there.
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

const TEAM_LINKS: { id: string; label: string; icon: LucideIcon }[] = [
  { id: "stages", label: "Stages", icon: FlaskConical },
  { id: "history", label: "Run history", icon: History },
  { id: "referee", label: "Referee", icon: Stamp },
];

// Suppress unused-import warnings — these are part of the public icon set referenced by the spec.
void Lightbulb;
void BookMarked;
void ClipboardList;
void Newspaper;

// Cycle order: dark → light → system → dark.
function nextTheme(t: "dark" | "light" | "system"): "dark" | "light" | "system" {
  if (t === "dark") return "light";
  if (t === "light") return "system";
  return "dark";
}

// Pick the indicator icon for a given resolved theme.
// Note: when theme is "system" we still want to show the icon for the
// currently-resolved appearance so the user can see what's active.
function themeIcon(theme: "dark" | "light" | "system", resolved: "dark" | "light"): LucideIcon {
  if (theme === "system") return Monitor;
  return resolved === "dark" ? Moon : Sun;
}

export function Sidebar({
  collapsed,
  onToggle,
  onOpenCommand,
  projectName,
  activeStage,
  onSelectStage,
  onCreateProject,
}: SidebarProps) {
  const pathname = usePathname();
  const { theme, resolvedTheme, setTheme } = useTheme();
  const [workspaceOpen, setWorkspaceOpen] = React.useState(true);
  const [teamOpen, setTeamOpen] = React.useState(true);

  // Suppress unused warning while keeping the public API stable.
  void onToggle;

  const ThemeIcon = themeIcon(theme, resolvedTheme);
  const themeLabel =
    theme === "system" ? "Theme: system" : theme === "dark" ? "Theme: dark" : "Theme: light";
  const onCycleTheme = () => setTheme(nextTheme(theme));

  if (collapsed) {
    return (
      <CollapsedSidebar
        pathname={pathname}
        onOpenCommand={onOpenCommand}
        onCreateProject={onCreateProject}
        onCycleTheme={onCycleTheme}
        ThemeIcon={ThemeIcon}
        themeLabel={themeLabel}
      />
    );
  }

  const teamName = projectName ?? "Nexis Foundation - Development";

  return (
    <aside
      className="relative flex h-screen flex-col bg-(--color-bg-marketing) text-[#E2E3E4] transition-[width] duration-150"
      style={{ width: 244 }}
      aria-label="Primary navigation"
    >
      {/* Top row */}
      <div
        className="flex items-center"
        style={{ height: 52, padding: "8px 12px 0px", gap: 8 }}
      >
        <button
          type="button"
          className="flex items-center rounded-[10px] hover:bg-(--color-ghost-bg-hover) transition-colors"
          style={{ width: 152, height: 28, padding: "0 7px", gap: 6 }}
          aria-label="Workspace menu"
        >
          <span
            className="flex items-center justify-center rounded-[5px] text-white shrink-0"
            style={{
              width: 20,
              height: 20,
              backgroundColor: "#00738E",
              fontSize: 11,
              fontWeight: 400,
            }}
            aria-hidden
          >
            N
          </span>
          <span
            className="truncate"
            style={{
              fontSize: 14,
              fontWeight: 550,
              letterSpacing: "-0.1px",
              color: "#E2E3E4",
            }}
          >
            Plato
          </span>
          <ChevronDown size={8} strokeWidth={2} color="#919193" className="ml-auto shrink-0" />
        </button>

        <div className="flex items-center" style={{ width: 60, height: 28, gap: 4 }}>
          <button
            type="button"
            onClick={onOpenCommand}
            aria-label="Search"
            className="flex items-center justify-center rounded-full hover:bg-(--color-ghost-bg-hover) transition-colors"
            style={{ width: 28, height: 28 }}
          >
            <Search size={14} strokeWidth={1.75} color="#919193" />
          </button>
          <button
            type="button"
            onClick={onCreateProject}
            aria-label="New project"
            className="flex items-center justify-center rounded-full transition-colors"
            style={{
              width: 28,
              height: 28,
              backgroundColor: "#1D1D1E",
              boxShadow:
                "0 0 0 1px #202122, 0 4px 4px -1px rgba(0,0,0,0.04), 0 1px 1px rgba(0,0,0,0.08)",
            }}
          >
            <Plus size={14} strokeWidth={1.75} color="#FFFFFF" />
          </button>
        </div>
      </div>

      {/* Margin / overlay region */}
      <div className="flex-1 overflow-y-auto" style={{ padding: "7.5px 0px 2px" }}>
        <div
          className="flex flex-col"
          style={{
            padding: "0 12px",
            backgroundColor: "rgba(0, 0, 0, 0.004)",
            borderRadius: 8,
          }}
        >
          {/* Top section: 57px, gap 1px */}
          <div className="flex flex-col" style={{ height: 57, gap: 1 }}>
            {TOP_LINKS.map((item) => (
              <SidebarLink key={item.href} item={item} pathname={pathname} />
            ))}
          </div>

          {/* Spacer */}
          <div style={{ height: 17 }} />

          {/* Workspace section */}
          <SectionHeader
            label="Workspace"
            open={workspaceOpen}
            onToggle={() => setWorkspaceOpen((o) => !o)}
          />
          {workspaceOpen && (
            <div className="flex flex-col" style={{ gap: 1 }}>
              {WORKSPACE_LINKS.map((item) => (
                <SidebarLink key={item.href} item={item} pathname={pathname} />
              ))}
              <button
                type="button"
                className="flex items-center rounded-[8px] text-[#919193] hover:bg-(--color-ghost-bg-hover) transition-colors"
                style={{
                  width: 220,
                  height: 30,
                  padding: "0 9px 0 10px",
                  gap: 8,
                }}
              >
                <PlusCircle size={14} strokeWidth={1.75} color="#919193" />
                <span style={{ fontSize: 13, fontWeight: 500 }}>More</span>
              </button>
            </div>
          )}

          {/* Spacer */}
          <div style={{ height: 8 }} />

          {/* Your teams */}
          <div className="group/teams flex items-center justify-between">
            <SectionHeader
              label="Your teams"
              open={teamOpen}
              onToggle={() => setTeamOpen((o) => !o)}
              fill
            />
            <button
              type="button"
              aria-label="Join a team"
              className="flex items-center justify-center rounded-full opacity-0 group-hover/teams:opacity-100 hover:bg-(--color-ghost-bg-hover) transition-opacity"
              style={{ width: 28, height: 28 }}
            >
              <Plus size={14} strokeWidth={1.75} color="#919193" />
            </button>
          </div>

          {/* Team row */}
          <button
            type="button"
            onClick={() => setTeamOpen((o) => !o)}
            className="flex items-center rounded-[10px] hover:bg-(--color-ghost-bg-hover) transition-colors"
            style={{ height: 28, padding: "6.25px 9px 5.5px", gap: 6 }}
          >
            <span
              className="inline-flex items-center justify-center shrink-0"
              style={{ width: 14, height: 14 }}
              aria-hidden
            >
              <span
                style={{
                  width: 4,
                  height: 4,
                  backgroundColor: "#FF0080",
                  borderRadius: 9999,
                  display: "block",
                }}
              />
            </span>
            <span
              className="truncate"
              style={{
                flex: 1,
                textAlign: "left",
                fontSize: 13,
                fontWeight: 500,
                color: "#919193",
              }}
            >
              {teamName}
            </span>
            <ChevronRight
              size={16}
              strokeWidth={1.75}
              color="#919193"
              className="shrink-0 transition-transform"
              style={{ transform: teamOpen ? "rotate(90deg)" : "rotate(0deg)" }}
            />
          </button>

          {teamOpen && (
            <div className="flex flex-col" style={{ paddingLeft: 19, gap: 1, marginTop: 1 }}>
              {TEAM_LINKS.map((item) => {
                const Icon = item.icon;
                const active = activeStage === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onSelectStage?.(item.id)}
                    className={cn(
                      "flex items-center rounded-[8px] transition-colors",
                      active
                        ? "bg-[#191A1A] text-white"
                        : "text-[#919193] hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)",
                    )}
                    style={{
                      width: 201,
                      height: 28,
                      padding: "0 9px 0 6px",
                      gap: 6,
                    }}
                  >
                    <Icon
                      size={14}
                      strokeWidth={1.75}
                      color={active ? "#FFFFFF" : "#919193"}
                    />
                    <span
                      className="truncate"
                      style={{
                        fontSize: 13,
                        fontWeight: 500,
                      }}
                    >
                      {item.label}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Bottom bar */}
      <div className="flex items-center" style={{ height: 45, padding: 10, gap: 4 }}>
        {/* Anchor styled like SidebarIconButton — using <a> directly so
            the link semantics survive (right-click → "open in new tab"
            etc.). The Help button used to be a no-op <button>; now it
            ships the user to the README. */}
        <a
          href="https://github.com/AstroPilot-AI/Plato"
          target="_blank"
          rel="noreferrer noopener"
          aria-label="Help — open Plato documentation"
          className="flex items-center justify-center rounded-[12px] transition-colors hover:bg-(--color-ghost-bg-hover)"
          style={{
            width: 24,
            height: 25,
            backgroundColor: "var(--color-bg-button-glass)",
            boxShadow: "var(--shadow-icon-button)",
          }}
        >
          <HelpCircle size={14} strokeWidth={1.75} className="text-(--color-text-tertiary)" />
        </a>
        <span
          className="ml-1 mr-auto"
          style={{ fontSize: 12, fontWeight: 500 }}
          aria-hidden
        >
          <span className="text-(--color-text-tertiary)">Help</span>
        </span>
        <SidebarIconButton
          aria-label="Toggle theme"
          title={themeLabel}
          onClick={onCycleTheme}
        >
          <ThemeIcon
            size={14}
            strokeWidth={1.75}
            className="text-(--color-text-tertiary)"
          />
        </SidebarIconButton>
        <Link
          href="/settings"
          aria-label="Settings"
          className={cn(
            "flex items-center justify-center rounded-[12px] transition-colors hover:bg-(--color-ghost-bg-hover)",
            pathname === "/settings" || pathname.startsWith("/settings/")
              ? "bg-(--color-ghost-bg-hover)"
              : "",
          )}
          style={{ width: 24, height: 25 }}
        >
          <SettingsIcon
            size={14}
            strokeWidth={1.75}
            className="text-(--color-text-tertiary)"
          />
        </Link>
      </div>

      {/* Right-edge resize handle */}
      <div
        aria-hidden
        className="absolute top-0 right-0 h-full opacity-0 hover:opacity-100 transition-opacity"
        style={{ width: "0.5px", backgroundColor: "#515153" }}
      />
    </aside>
  );
}

function SidebarLink({ item, pathname }: { item: NavLink; pathname: string }) {
  const Icon = item.icon;
  const active =
    item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(`${item.href}/`);
  return (
    <Link
      href={item.href}
      className={cn(
        "flex items-center rounded-[8px] transition-colors",
        active
          ? "bg-[#191A1A] text-white"
          : "text-[#919193] hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)",
      )}
      style={{ width: 220, height: 28, padding: "0 9px 0 10px", gap: 8 }}
      aria-current={active ? "page" : undefined}
    >
      <Icon
        size={14}
        strokeWidth={1.75}
        color={active ? "#FFFFFF" : "#919193"}
      />
      <span style={{ fontSize: 13, fontWeight: 500 }}>{item.label}</span>
    </Link>
  );
}

function SectionHeader({
  label,
  open,
  onToggle,
  fill,
}: {
  label: string;
  open: boolean;
  onToggle: () => void;
  fill?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "flex items-center rounded-[6px] hover:bg-(--color-ghost-bg-hover) transition-colors",
        fill ? "flex-1" : "",
      )}
      style={{ height: 28, padding: "0 6px", gap: 4 }}
    >
      <span style={{ fontSize: 12, fontWeight: 500, color: "#919193" }}>
        {label}
      </span>
      <ChevronDown
        size={16}
        strokeWidth={1.75}
        color="#919193"
        className="transition-transform"
        style={{ transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}
      />
    </button>
  );
}

/**
 * Reusable square icon button for the sidebar bottom row. Shares its
 * background-and-shadow treatment with the help/theme/settings buttons so
 * the bottom utility row reads as a single visual cluster.
 */
const SidebarIconButton = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement>
>(function SidebarIconButton({ className, children, ...rest }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      className={cn(
        "flex items-center justify-center rounded-[12px] transition-colors hover:bg-(--color-ghost-bg-hover)",
        className,
      )}
      style={{
        width: 24,
        height: 25,
        backgroundColor: "var(--color-bg-button-glass)",
        boxShadow: "var(--shadow-icon-button)",
      }}
      {...rest}
    >
      {children}
    </button>
  );
});

function CollapsedSidebar({
  pathname,
  onOpenCommand,
  onCreateProject,
  onCycleTheme,
  ThemeIcon,
  themeLabel,
}: {
  pathname: string;
  onOpenCommand: () => void;
  onCreateProject?: () => void;
  onCycleTheme: () => void;
  ThemeIcon: LucideIcon;
  themeLabel: string;
}) {
  return (
    <aside
      className="flex h-screen flex-col items-center bg-(--color-bg-marketing) hairline-r"
      style={{ width: 56 }}
      aria-label="Primary navigation"
    >
      <div
        className="flex items-center justify-center"
        style={{ height: 52, paddingTop: 8 }}
      >
        <span
          className="flex items-center justify-center rounded-[5px] text-white"
          style={{
            width: 20,
            height: 20,
            backgroundColor: "#00738E",
            fontSize: 11,
          }}
          aria-hidden
        >
          N
        </span>
      </div>

      <div className="flex flex-col items-center" style={{ gap: 4, marginTop: 4 }}>
        <button
          type="button"
          onClick={onOpenCommand}
          aria-label="Search"
          className="flex items-center justify-center rounded-full hover:bg-(--color-ghost-bg-hover) transition-colors"
          style={{ width: 28, height: 28 }}
        >
          <Search size={14} strokeWidth={1.75} color="#919193" />
        </button>
        <button
          type="button"
          onClick={onCreateProject}
          aria-label="New project"
          className="flex items-center justify-center rounded-full transition-colors"
          style={{
            width: 28,
            height: 28,
            backgroundColor: "#1D1D1E",
            boxShadow:
              "0 0 0 1px #202122, 0 4px 4px -1px rgba(0,0,0,0.04), 0 1px 1px rgba(0,0,0,0.08)",
          }}
        >
          <Plus size={14} strokeWidth={1.75} color="#FFFFFF" />
        </button>
      </div>

      <nav
        className="flex flex-col items-center"
        style={{ gap: 4, marginTop: 12 }}
      >
        {[...TOP_LINKS, ...WORKSPACE_LINKS].map((item) => {
          const Icon = item.icon;
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={`${item.href}-${item.label}`}
              href={item.href}
              aria-label={item.label}
              className={cn(
                "flex items-center justify-center rounded-[8px] transition-colors",
                active
                  ? "bg-[#191A1A] text-white"
                  : "text-[#919193] hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)",
              )}
              style={{ width: 32, height: 32 }}
            >
              <Icon
                size={14}
                strokeWidth={1.75}
                color={active ? "#FFFFFF" : "#919193"}
              />
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto flex flex-col items-center gap-1.5 pb-3">
        <Link
          href="/settings"
          aria-label="Settings"
          className={cn(
            "flex items-center justify-center rounded-[12px] transition-colors hover:bg-(--color-ghost-bg-hover)",
            pathname === "/settings" || pathname.startsWith("/settings/")
              ? "bg-(--color-ghost-bg-hover)"
              : "",
          )}
          style={{
            width: 24,
            height: 25,
            backgroundColor: "var(--color-bg-button-glass)",
            boxShadow: "var(--shadow-icon-button)",
          }}
        >
          <SettingsIcon
            size={14}
            strokeWidth={1.75}
            className="text-(--color-text-tertiary)"
          />
        </Link>
        <SidebarIconButton
          aria-label="Toggle theme"
          title={themeLabel}
          onClick={onCycleTheme}
        >
          <ThemeIcon
            size={14}
            strokeWidth={1.75}
            className="text-(--color-text-tertiary)"
          />
        </SidebarIconButton>
        <a
          href="https://github.com/AstroPilot-AI/Plato"
          target="_blank"
          rel="noreferrer noopener"
          aria-label="Help — open Plato documentation"
          className="flex items-center justify-center rounded-[12px] transition-colors hover:bg-(--color-ghost-bg-hover)"
          style={{
            width: 24,
            height: 25,
            backgroundColor: "var(--color-bg-button-glass)",
            boxShadow: "var(--shadow-icon-button)",
          }}
        >
          <HelpCircle size={14} strokeWidth={1.75} className="text-(--color-text-tertiary)" />
        </a>
      </div>
    </aside>
  );
}
