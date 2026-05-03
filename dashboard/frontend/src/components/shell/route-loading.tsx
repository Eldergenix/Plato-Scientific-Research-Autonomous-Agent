import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

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

/**
 * Skeleton placeholder for tables. Renders `rows` rows of grey bars
 * sized to `columnWidths` (CSS widths like "32%", "120px"), so the
 * loading state mirrors the column layout of the eventual content
 * instead of showing a generic spinner that shifts the layout when
 * data lands.
 */
export function TableSkeleton({
  rows = 6,
  columnWidths,
  className,
  caption = "Loading table data",
}: {
  rows?: number;
  columnWidths: ReadonlyArray<string>;
  className?: string;
  caption?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={caption}
      data-testid="table-skeleton"
      className={cn("w-full", className)}
    >
      <span className="sr-only">{caption}</span>
      <div className="flex items-center gap-3 px-4 py-2 hairline-b">
        {columnWidths.map((width, i) => (
          <div
            key={`head-${i}`}
            className="h-3 rounded-[3px] bg-(--color-bg-pill-inactive) animate-pulse"
            style={{ width }}
          />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div
          key={`row-${rowIdx}`}
          className="flex items-center gap-3 px-4 py-3 hairline-b"
        >
          {columnWidths.map((width, colIdx) => (
            <div
              key={`cell-${rowIdx}-${colIdx}`}
              className="h-3.5 rounded-[3px] bg-(--color-ghost-bg-hover) animate-pulse"
              style={{
                width,
                animationDelay: `${(rowIdx * columnWidths.length + colIdx) * 40}ms`,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
