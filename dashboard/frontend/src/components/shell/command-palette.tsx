"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  Activity,
  Atom,
  FolderKanban,
  KeyRound,
  Layers,
  Play,
  Plus,
  Settings,
  Wallet,
  FileText,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface CommandAction {
  label: string;
  hint?: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  /** Either a route to push, or a custom handler (handler wins). */
  href?: string;
  onSelect?: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Optional custom action handlers (e.g., wire "Run idea" to startRun()). */
  onRunStage?: (stage: "idea" | "method" | "literature" | "results" | "paper" | "referee") => void;
  onCreateProject?: () => void;
}

export function CommandPalette({
  open,
  onOpenChange,
  onRunStage,
  onCreateProject,
}: CommandPaletteProps) {
  const router = useRouter();

  React.useEffect(() => {
    function down(e: KeyboardEvent) {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
      if (e.key === "Escape" && open) {
        e.preventDefault();
        onOpenChange(false);
      }
    }
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [open, onOpenChange]);

  const dispatch = React.useCallback(
    (action: CommandAction) => {
      onOpenChange(false);
      if (action.onSelect) {
        action.onSelect();
      } else if (action.href) {
        router.push(action.href);
      }
    },
    [onOpenChange, router],
  );

  const navigateActions: CommandAction[] = [
    { label: "Workspace", icon: Atom, href: "/" },
    { label: "Projects", icon: FolderKanban, href: "/projects" },
    { label: "Models", icon: Layers, href: "/models" },
    { label: "Keys", icon: KeyRound, href: "/keys" },
    { label: "Costs", icon: Wallet, href: "/costs" },
    { label: "Activity", icon: Activity, href: "/activity" },
  ];

  const runActions: CommandAction[] = onRunStage
    ? [
        {
          label: "Run idea generation",
          hint: "fast mode",
          icon: Play,
          onSelect: () => onRunStage("idea"),
        },
        {
          label: "Run method generation",
          icon: Play,
          onSelect: () => onRunStage("method"),
        },
        {
          label: "Run literature novelty check",
          icon: Play,
          onSelect: () => onRunStage("literature"),
        },
        {
          label: "Run results experiment",
          hint: "cmbagent · long",
          icon: Play,
          onSelect: () => onRunStage("results"),
        },
        {
          label: "Generate paper",
          hint: "LaTeX",
          icon: FileText,
          onSelect: () => onRunStage("paper"),
        },
        {
          label: "Run referee review",
          icon: RefreshCw,
          onSelect: () => onRunStage("referee"),
        },
      ]
    : [];

  const projectActions: CommandAction[] = onCreateProject
    ? [
        {
          label: "Create new project",
          icon: Plus,
          onSelect: onCreateProject,
        },
      ]
    : [];

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/40 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onOpenChange(false)}
      role="presentation"
    >
      <Command
        label="Command palette"
        className={cn(
          "w-[640px] max-w-[90vw] surface-card shadow-[var(--shadow-dialog)]",
          "rounded-[12px] overflow-hidden",
        )}
      >
        <Command.Input
          placeholder="Search projects, run a stage, switch model…"
          className="w-full h-12 px-4 bg-transparent text-[14px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary) focus-visible:outline-none hairline-b"
        />
        <Command.List className="max-h-[400px] overflow-y-auto p-2">
          <Command.Empty className="px-3 py-6 text-center text-[13px] text-(--color-text-tertiary)">
            No matches.
          </Command.Empty>

          {projectActions.length > 0 && (
            <Command.Group
              heading="Project"
              className="text-[11px] text-(--color-text-quaternary) px-3 py-1.5 uppercase tracking-wider"
            >
              {projectActions.map((action) => (
                <PaletteItem key={action.label} action={action} dispatch={dispatch} />
              ))}
            </Command.Group>
          )}

          <Command.Group
            heading="Navigate"
            className="text-[11px] text-(--color-text-quaternary) px-3 py-1.5 uppercase tracking-wider mt-2"
          >
            {navigateActions.map((action) => (
              <PaletteItem key={action.label} action={action} dispatch={dispatch} />
            ))}
            <PaletteItem
              action={{ label: "Settings", icon: Settings, href: "/settings" }}
              dispatch={dispatch}
            />
          </Command.Group>

          {runActions.length > 0 && (
            <Command.Group
              heading="Run"
              className="text-[11px] text-(--color-text-quaternary) px-3 py-1.5 uppercase tracking-wider mt-2"
            >
              {runActions.map((action) => (
                <PaletteItem key={action.label} action={action} dispatch={dispatch} />
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </div>
  );
}

function PaletteItem({
  action,
  dispatch,
}: {
  action: CommandAction;
  dispatch: (action: CommandAction) => void;
}) {
  const Icon = action.icon;
  return (
    <Command.Item
      value={action.label}
      onSelect={() => dispatch(action)}
      className={cn(
        "flex items-center gap-2.5 h-9 px-3 rounded-[6px] text-[13px] cursor-pointer",
        "text-(--color-text-secondary)",
        "data-[selected=true]:bg-(--color-ghost-bg-hover) data-[selected=true]:text-(--color-text-primary)",
      )}
    >
      <Icon size={14} strokeWidth={1.5} className="text-(--color-text-tertiary)" />
      <span>{action.label}</span>
      {action.hint && (
        <span className="ml-auto text-[11px] text-(--color-text-quaternary) font-mono">
          {action.hint}
        </span>
      )}
    </Command.Item>
  );
}
