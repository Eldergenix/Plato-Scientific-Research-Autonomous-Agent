"use client";

import * as React from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Themed checkbox to replace raw <input type="checkbox"> usages.
 *
 * Built on a hidden native input so form semantics, keyboard handling,
 * and screen-reader behavior come for free. The visible square is a
 * styled box that mirrors `checked` and `disabled`.
 */
export interface CheckboxProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: React.ReactNode;
  name?: string;
  className?: string;
  id?: string;
  "data-testid"?: string;
  "aria-label"?: string;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox(
    {
      checked,
      onCheckedChange,
      disabled,
      label,
      name,
      className,
      id,
      "data-testid": testId,
      "aria-label": ariaLabel,
    },
    ref,
  ) {
    const generatedId = React.useId();
    const inputId = id ?? generatedId;

    const box = (
      <span className="relative inline-flex h-4 w-4 flex-none items-center justify-center">
        <input
          ref={ref}
          id={inputId}
          type="checkbox"
          name={name}
          checked={checked}
          disabled={disabled}
          aria-label={label ? undefined : ariaLabel}
          data-testid={testId}
          onChange={(e) => onCheckedChange(e.target.checked)}
          className="peer absolute inset-0 h-full w-full cursor-pointer appearance-none rounded-[4px] border border-(--color-border-strong) bg-(--color-bg-elevated) transition-colors checked:border-(--color-brand-indigo) checked:bg-(--color-brand-indigo) hover:border-(--color-border-pill) checked:hover:bg-(--color-brand-interactive) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive) focus-visible:ring-offset-2 focus-visible:ring-offset-(--color-bg-marketing) disabled:cursor-not-allowed disabled:opacity-50"
        />
        <Check
          aria-hidden
          size={12}
          strokeWidth={3}
          className={cn(
            "pointer-events-none relative text-white transition-opacity",
            checked ? "opacity-100" : "opacity-0",
          )}
        />
      </span>
    );

    if (!label) {
      return <span className={cn("inline-flex", className)}>{box}</span>;
    }

    return (
      <label
        htmlFor={inputId}
        className={cn(
          "inline-flex cursor-pointer items-center gap-2 select-none",
          disabled && "cursor-not-allowed opacity-60",
          className,
        )}
      >
        {box}
        <span>{label}</span>
      </label>
    );
  },
);
