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
 *
 * Mobile-only swipe-to-dismiss is wired on the content element via
 * plain pointer events. Triggers only on coarse pointers under the
 * mobile breakpoint, only on horizontal sheets (left/right), and only
 * when the swipe matches the dismiss direction. Vertical sheets fall
 * back to Radix's built-in Esc/backdrop dismissal.
 */
export type SheetSide = "left" | "right" | "top" | "bottom";

const SIDE_CLASSES: Record<SheetSide, string> = {
  left: "left-0 top-0 h-full w-[260px] data-[state=open]:animate-sheet-in-left",
  right: "right-0 top-0 h-full w-[260px] data-[state=open]:animate-sheet-in-right",
  top: "left-0 top-0 w-full h-[60vh] data-[state=open]:animate-sheet-in-top",
  bottom: "left-0 bottom-0 w-full h-[60vh] data-[state=open]:animate-sheet-in-bottom",
};

const SWIPE_DISMISS_THRESHOLD_PX = 50;
const SWIPE_AXIS_LOCK_PX = 8;
const MOBILE_BREAKPOINT_QUERY = "(max-width: 768px)";

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
  const contentRef = React.useRef<HTMLDivElement | null>(null);
  // Track gesture state on refs — avoids re-rendering on every pointermove
  // (transforms run via direct style mutation for a steady 60fps drag).
  const gesture = React.useRef({
    active: false,
    pointerId: -1,
    startX: 0,
    startY: 0,
    delta: 0,
    axisLocked: false,
  });

  const onOpenChangeRef = React.useRef(onOpenChange);
  React.useEffect(() => {
    onOpenChangeRef.current = onOpenChange;
  }, [onOpenChange]);

  const isHorizontal = side === "left" || side === "right";

  const resetTransform = React.useCallback((animate: boolean) => {
    const el = contentRef.current;
    if (!el) return;
    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (animate && !reduceMotion) {
      el.style.transition = "transform 160ms ease-out";
    } else {
      el.style.transition = "";
    }
    el.style.transform = "";
    // Clear the transition once it runs so it doesn't interfere with
    // Radix's open animation on a subsequent open.
    if (animate && !reduceMotion) {
      const cleanup = () => {
        if (contentRef.current) contentRef.current.style.transition = "";
      };
      window.setTimeout(cleanup, 200);
    }
  }, []);

  const handlePointerDown = React.useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!isHorizontal) return;
      // Only handle coarse pointers (touch/pen) on mobile widths.
      if (e.pointerType === "mouse") return;
      if (typeof window === "undefined") return;
      if (!window.matchMedia(MOBILE_BREAKPOINT_QUERY).matches) return;
      // Don't hijack drags that start on interactive controls — let
      // buttons/links handle their own pointer flow.
      const target = e.target as HTMLElement | null;
      if (target?.closest("button, a, input, textarea, select, [role='button']")) {
        return;
      }
      gesture.current = {
        active: true,
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        delta: 0,
        axisLocked: false,
      };
    },
    [isHorizontal],
  );

  const handlePointerMove = React.useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const g = gesture.current;
      if (!g.active || g.pointerId !== e.pointerId) return;
      const dx = e.clientX - g.startX;
      const dy = e.clientY - g.startY;
      // Lock axis on the first meaningful move — if the user is mostly
      // scrolling vertically, abandon the swipe so inner overflow lists
      // still work.
      if (!g.axisLocked) {
        if (Math.abs(dx) < SWIPE_AXIS_LOCK_PX && Math.abs(dy) < SWIPE_AXIS_LOCK_PX) {
          return;
        }
        if (Math.abs(dy) > Math.abs(dx)) {
          g.active = false;
          return;
        }
        g.axisLocked = true;
        // Capture so we keep getting events even if the finger leaves
        // the panel.
        const el = contentRef.current;
        if (el && el.setPointerCapture) {
          try {
            el.setPointerCapture(e.pointerId);
          } catch {
            // Some environments throw if the pointer is already gone — ignore.
          }
        }
      }
      // Clamp so the panel only moves in the dismiss direction.
      const dismissDelta = side === "left" ? Math.min(0, dx) : Math.max(0, dx);
      g.delta = dismissDelta;
      const el = contentRef.current;
      if (!el) return;
      el.style.transition = "";
      el.style.transform = `translate3d(${dismissDelta}px, 0, 0)`;
    },
    [side],
  );

  const handlePointerUp = React.useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const g = gesture.current;
      if (!g.active || g.pointerId !== e.pointerId) return;
      const wasLocked = g.axisLocked;
      const finalDelta = g.delta;
      g.active = false;
      g.axisLocked = false;
      g.pointerId = -1;
      g.delta = 0;
      const el = contentRef.current;
      if (el && el.releasePointerCapture && el.hasPointerCapture?.(e.pointerId)) {
        try {
          el.releasePointerCapture(e.pointerId);
        } catch {
          // ignore
        }
      }
      if (!wasLocked) return;
      const dismissed = Math.abs(finalDelta) >= SWIPE_DISMISS_THRESHOLD_PX;
      if (dismissed) {
        // Let Radix run its close transition; clear transform on next
        // tick so the panel doesn't snap back before unmounting.
        onOpenChangeRef.current(false);
        // Reset on close so a re-open starts from a clean slate.
        window.setTimeout(() => resetTransform(false), 200);
      } else {
        resetTransform(true);
      }
    },
    [resetTransform],
  );

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm data-[state=open]:animate-fade-in"
          data-testid="sheet-overlay"
        />
        <Dialog.Content
          ref={contentRef}
          data-testid="sheet-content"
          data-side={side}
          className={cn(
            "fixed z-50 flex flex-col bg-(--color-bg-card) shadow-[var(--shadow-dialog)]",
            SIDE_CLASSES[side],
            className,
          )}
          style={{
            border: "1px solid var(--color-border-card)",
            touchAction: isHorizontal ? "pan-y" : undefined,
          }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
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
