import { Loader2 } from "lucide-react";

/**
 * Shared route-level loading skeleton.
 *
 * Drop-in body for ``loading.tsx`` files at any segment. Renders a
 * centred spinner under the same page chrome the actual route would
 * use, so navigations no longer flash a blank screen while the route
 * component (and its data fetches) hydrate.
 */
export function RouteLoading({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="route-loading"
      className="flex min-h-[40vh] flex-col items-center justify-center gap-3 px-6 py-8 text-(--color-text-tertiary-spec)"
    >
      <Loader2
        size={20}
        strokeWidth={1.75}
        className="animate-spin text-(--color-brand-hover)"
      />
      <span className="text-[12.5px]">{label}</span>
    </div>
  );
}
