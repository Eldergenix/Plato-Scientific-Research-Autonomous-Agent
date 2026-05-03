"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Shared route-level error fallback.
 *
 * Drop-in body for ``error.tsx`` files at any segment. The component
 * runs in the browser (Next.js requires ``"use client"`` on
 * ``error.tsx``) and offers a single ``reset`` action so the user
 * doesn't have to reload the whole tab when a single route segment
 * crashes — the sidebar and shell stay navigable.
 */
export function RouteError({
  error,
  reset,
  label = "Something went wrong",
}: {
  error: Error & { digest?: string };
  reset: () => void;
  label?: string;
}) {
  return (
    <div
      role="alert"
      data-testid="route-error"
      className="flex min-h-[40vh] flex-col items-center justify-center gap-3 px-6 py-8 text-(--color-text-primary)"
    >
      <AlertTriangle
        size={28}
        strokeWidth={1.5}
        className="text-(--color-status-red)"
      />
      <div className="text-[14px] font-medium">{label}</div>
      <div className="max-w-md text-center text-[12.5px] text-(--color-text-tertiary-spec)">
        {error.message || "An unexpected error occurred."}
        {error.digest ? (
          <span className="mt-1 block font-mono text-[11px] text-(--color-text-quaternary-spec)">
            digest: {error.digest}
          </span>
        ) : null}
      </div>
      <Button variant="primary" size="sm" onClick={reset}>
        <RotateCcw size={12} strokeWidth={1.75} />
        Try again
      </Button>
    </div>
  );
}
