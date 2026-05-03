import { TableSkeleton } from "@/components/shell/route-loading";

/**
 * Route-level loading state for /models. Renders a column-matched
 * skeleton inside the same surface card the page uses, so the layout
 * doesn't shift when the actual table mounts.
 *
 * Column widths mirror the <colgroup> in models/page.tsx — keep these
 * in sync if the table layout changes.
 */
const COLUMN_WIDTHS = ["26%", "13%", "10%", "13%", "13%", "17%", "8%"] as const;

export default function Loading() {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-7xl space-y-4">
        <header className="surface-linear-card flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <h1
              className="text-(--color-text-primary-strong)"
              style={{ fontFamily: "Inter", fontWeight: 510, fontSize: 24, letterSpacing: "-0.5px" }}
            >
              Models
            </h1>
            <p className="mt-0.5 text-[13px] text-(--color-text-tertiary-spec)">
              Loading model catalog…
            </p>
          </div>
        </header>

        <section className="surface-linear-card overflow-hidden">
          <TableSkeleton
            rows={8}
            columnWidths={COLUMN_WIDTHS}
            caption="Loading models table"
          />
        </section>
      </div>
    </div>
  );
}
