import * as React from "react";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "indigo" | "green" | "amber" | "red" | "lavender";

const TONE_CLASSES: Record<Tone, string> = {
  neutral:
    "bg-(--color-ghost-bg) text-(--color-text-secondary) border-(--color-border-solid)",
  indigo:
    "bg-(--color-brand-indigo)/15 text-(--color-brand-hover) border-(--color-brand-indigo)/30",
  green:
    "bg-(--color-status-emerald)/12 text-(--color-status-emerald) border-(--color-status-emerald)/30",
  amber:
    "bg-(--color-status-amber)/12 text-(--color-status-amber) border-(--color-status-amber)/30",
  red:
    "bg-(--color-status-red)/12 text-(--color-status-red) border-(--color-status-red)/30",
  lavender:
    "bg-(--color-brand-lavender)/12 text-(--color-brand-lavender) border-(--color-brand-lavender)/30",
};

export function Pill({
  tone = "neutral",
  className,
  children,
  ...rest
}: { tone?: Tone } & React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "pill border",
        TONE_CLASSES[tone],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
