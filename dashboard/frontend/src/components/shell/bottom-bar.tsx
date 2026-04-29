"use client";

import * as React from "react";
import { Sparkles, History } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Linear-style bottom bar.
 *
 * Spec:
 *   Outer:    full-width, height 32px, bg #070707 (--color-bg-page),
 *             padding 2px 8px 0 2px.
 *   Inside:   justify-end, gap 2px.
 *   Buttons:  rounded-[8px], h-7 (28px), hover bg #151516.
 *
 *   "Ask Plato": Sparkles icon (14x14) + label (Inter 450 / 12px / 15px lh / #919193)
 *                padding 0 11.5px 0 9.5px, gap 6px between icon and text.
 *   History:     square 28x28, padding 0 6px, History icon (14x14).
 */
export function BottomBar({
  onAskAi,
  onOpenHistory,
}: {
  onAskAi?: () => void;
  onOpenHistory?: () => void;
}) {
  return (
    <div
      className={cn(
        "w-full flex items-center justify-end gap-[2px]",
        "bg-(--color-bg-page) hairline-t",
      )}
      style={{
        height: "var(--h-bottom-bar)",
        padding: "2px 8px 0 2px",
      }}
    >
      <button
        type="button"
        onClick={onAskAi}
        className={cn(
          "inline-flex items-center gap-1.5",
          "h-7 rounded-[8px] bg-transparent",
          "transition-colors hover:bg-[#151516]",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-interactive)",
        )}
        style={{ padding: "0 11.5px 0 9.5px" }}
        aria-label="Ask Plato"
      >
        <Sparkles
          size={14}
          strokeWidth={1.5}
          className="text-(--color-text-tertiary-spec)"
        />
        <span
          style={{
            fontFamily: "var(--font-sans)",
            fontWeight: 450,
            fontSize: "12px",
            lineHeight: "15px",
            color: "#919193",
          }}
        >
          Ask Plato
        </span>
      </button>

      <button
        type="button"
        onClick={onOpenHistory}
        className={cn(
          "inline-flex items-center justify-center",
          "h-7 w-7 rounded-[8px] bg-transparent",
          "transition-colors hover:bg-[#151516]",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-interactive)",
        )}
        style={{ padding: "0 6px" }}
        aria-label="Open run history"
        title="Run history"
      >
        <History
          size={14}
          strokeWidth={1.5}
          className="text-(--color-text-tertiary-spec)"
        />
      </button>
    </div>
  );
}
