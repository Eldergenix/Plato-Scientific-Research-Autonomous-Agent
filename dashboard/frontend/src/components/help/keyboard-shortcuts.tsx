"use client";

import * as React from "react";
import { Sheet } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

/**
 * Global keyboard-shortcut reference. Opens via cmd/ctrl+/ or `?` (when no
 * input is focused) and is also wired into the bottom bar's "Shortcuts"
 * link and the onboarding empty-state tip.
 *
 * The `?` trigger explicitly bails out when the active element is an input,
 * textarea, or contenteditable surface so users can still type a literal `?`
 * into a prompt field without summoning the help panel.
 */

type Chord = string[];

interface ShortcutEntry {
  chord: Chord;
  description: string;
}

interface ShortcutGroup {
  heading: string;
  entries: ShortcutEntry[];
}

const isMac = typeof navigator !== "undefined"
  && /Mac|iPhone|iPad|iPod/.test(navigator.platform);

const MOD = isMac ? "⌘" : "Ctrl";

const GROUPS: ShortcutGroup[] = [
  {
    heading: "Navigation",
    entries: [
      { chord: [MOD, "K"], description: "Open command palette" },
      { chord: [MOD, "/"], description: "Show this shortcuts panel" },
      { chord: ["?"], description: "Show this shortcuts panel" },
      { chord: ["Tab"], description: "Move focus to the next control" },
      { chord: ["Shift", "Tab"], description: "Move focus to the previous control" },
      { chord: ["←", "→"], description: "Switch between filter tabs (Active / Backlog / All)" },
    ],
  },
  {
    heading: "Editing",
    entries: [
      { chord: ["Enter"], description: "Activate the focused button or row" },
      { chord: ["Space"], description: "Activate the focused button or row" },
      { chord: ["Enter"], description: "Commit a plot caption edit" },
      { chord: ["Esc"], description: "Cancel a caption edit or close a dialog" },
    ],
  },
  {
    heading: "Run control",
    entries: [
      { chord: [MOD, "K"], description: "Search a stage to run from the command palette" },
      { chord: ["Esc"], description: "Close the command palette without selecting" },
      { chord: ["Esc"], description: "Close the plot lightbox" },
    ],
  },
];

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (el.isContentEditable) return true;
  // cmdk inputs sit inside [cmdk-input-wrapper] — treat them as typing too.
  if (el.closest("[cmdk-input]") || el.closest("[contenteditable='true']")) {
    return true;
  }
  return false;
}

export interface KeyboardShortcutsContextValue {
  open: () => void;
}

const KeyboardShortcutsContext = React.createContext<
  KeyboardShortcutsContextValue | null
>(null);

/**
 * Global wrapper that owns the shortcuts overlay. Wraps the dashboard so any
 * descendant can call {@link useKeyboardShortcuts} to open the panel from a
 * link or button (bottom bar, onboarding empty state, etc.).
 */
export function KeyboardShortcutsProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    function down(e: KeyboardEvent) {
      // cmd/ctrl + / — power-user trigger that doesn't conflict with the
      // browser's "find on page" or "view source".
      if (e.key === "/" && (e.metaKey || e.ctrlKey) && !e.shiftKey) {
        e.preventDefault();
        setOpen((prev) => !prev);
        return;
      }
      // `?` — only when not typing into a field. Browsers report `?` as
      // either e.key === "?" or shift+`/`; cover both.
      const isQuestion =
        e.key === "?" || (e.key === "/" && e.shiftKey);
      if (isQuestion && !e.metaKey && !e.ctrlKey && !e.altKey) {
        if (isTypingTarget(e.target)) return;
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const value = React.useMemo(
    () => ({ open: () => setOpen(true) }),
    [],
  );

  return (
    <KeyboardShortcutsContext.Provider value={value}>
      {children}
      <KeyboardShortcutsSheet open={open} onOpenChange={setOpen} />
    </KeyboardShortcutsContext.Provider>
  );
}

export function useKeyboardShortcuts(): KeyboardShortcutsContextValue {
  const ctx = React.useContext(KeyboardShortcutsContext);
  if (!ctx) {
    // Safe fallback so consumers outside the provider don't crash; the call
    // site simply becomes a no-op until the provider mounts.
    return { open: () => {} };
  }
  return ctx;
}

function KeyboardShortcutsSheet({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Keyboard shortcuts"
      side="right"
      className="w-[380px]"
    >
      <div
        className="flex flex-col gap-5 px-4 py-4"
        data-testid="keyboard-shortcuts-panel"
      >
        {GROUPS.map((group) => (
          <section key={group.heading} className="flex flex-col gap-2">
            <h3 className="text-[11px] font-medium uppercase tracking-wider text-(--color-text-quaternary)">
              {group.heading}
            </h3>
            <ul className="flex flex-col">
              {group.entries.map((entry, idx) => (
                <li
                  key={`${group.heading}-${idx}`}
                  className="flex items-center justify-between gap-3 py-1.5 hairline-b last:border-b-0"
                >
                  <span className="text-[12.5px] text-(--color-text-secondary)">
                    {entry.description}
                  </span>
                  <span className="flex items-center gap-1 shrink-0">
                    {entry.chord.map((key, i) => (
                      <React.Fragment key={`${key}-${i}`}>
                        {i > 0 && (
                          <span
                            aria-hidden
                            className="text-[10px] text-(--color-text-quaternary)"
                          >
                            +
                          </span>
                        )}
                        <Kbd>{key}</Kbd>
                      </React.Fragment>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </Sheet>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd
      className={cn(
        "inline-flex items-center justify-center",
        "min-w-[20px] h-[20px] px-1.5",
        "rounded-[4px] border border-(--color-border-card)",
        "bg-(--color-bg-button-glass)",
        "text-[11px] font-mono text-(--color-text-secondary)",
        "shadow-[var(--shadow-glass)]",
      )}
    >
      {children}
    </kbd>
  );
}
