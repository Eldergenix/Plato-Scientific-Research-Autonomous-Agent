"use client";

import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Slide-in panel built on Radix Dialog — used for the mobile sidebar
 * drawer (and any other off-canvas surface that needs a real focus
 * trap + ESC handling). The component matches the visual language of
 * `confirm-dialog.tsx`: same overlay tint, same border treatment, same
 * close-button affordance, but slides in from a side instead of
 * centering.
 *
 * We deliberately do NOT export a Trigger — callers wire up their own
 * hamburger button and pass `open` / `onOpenChange` so the sheet can be
 * driven by both pointer clicks and route-change side-effects (e.g.
 * auto-close on navigation).
 */
export type SheetSide = "left" | "right" | "top" | "bottom";

const SIDE_CLASSES: Record<SheetSide, string> = {
  left: "left-0 top-0 h-full w-[260px] data-[state=open]:animate-sheet-in-left",
  right: "right-0 top-0 h-full w-[260px] data-[state=open]:animate-sheet-in-right",
  top: "left-0 top-0 w-full h-[60vh] data-[state=open]:animate-sheet-in-top",
  bottom: "left-0 bottom-0 w-full h-[60vh] data-[state=open]:animate-sheet-in-bottom",
};

export interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Visible title for screen readers; pass `srOnly` to hide visually. */
  title: string;
  /** Hide the title visually while keeping it in the a11y tree. */
  srOnly?: boolean;
  side?: SheetSide;
  /** Override the panel width (left/right) or height (top/bottom). */
  className?: string;
  /** Hide the built-in close button — useful if the panel itself owns dismissal. */
  hideCloseButton?: boolean;
  children: React.ReactNode;
}

export function Sheet({
  open,
  onOpenChange,
  title,
  srOnly = false,
  side = "left",
  className,
  hideCloseButton = false,
  children,
}: SheetProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm data-[state=open]:animate-fade-in"
          data-testid="sheet-overlay"
        />
        <Dialog.Content
          data-testid="sheet-content"
          data-side={side}
          className={cn(
            "fixed z-50 flex flex-col bg-(--color-bg-card) shadow-[var(--shadow-dialog)]",
            SIDE_CLASSES[side],
            className,
          )}
          style={{
            border: "1px solid var(--color-border-card)",
          }}
        >
          {/* Title is required by Radix Dialog for a11y — we render it
              visually unless srOnly is set, in which case it's screen-
              reader-only via .sr-only. */}
          <Dialog.Title
            className={cn(
              srOnly
                ? "sr-only"
                : "px-4 py-3 text-[13px] font-medium text-(--color-text-primary) hairline-b",
            )}
          >
            {title}
          </Dialog.Title>

          {!hideCloseButton ? (
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close"
                data-testid="sheet-close"
                className="absolute right-2 top-2 size-7 inline-flex items-center justify-center rounded-full text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary) transition-colors"
              >
                <X size={14} strokeWidth={1.75} />
              </button>
            </Dialog.Close>
          ) : null}

          <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
