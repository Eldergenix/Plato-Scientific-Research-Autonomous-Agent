import type { Metadata } from "next";
import Link from "next/link";
import { ChevronRight, Sliders } from "lucide-react";
import { cn } from "@/lib/utils";
import { RunPresetsClient } from "./run-presets-client";

export const metadata: Metadata = {
  title: "Run presets — Plato",
  description:
    "Save and reuse named run configurations — idea iterations, max revision iters, journal, domain, executor.",
};

/**
 * RSC chrome for /settings/run-presets.
 *
 * Mirrors /settings/executors: server-side breadcrumb + header, with the
 * preset table + new-preset form delegated to the client island. Data
 * fetching stays client-side so the existing Playwright `page.route`
 * mocks (used in other settings tests) keep working unchanged.
 */
export default function RunPresetsSettingsPage() {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-3 py-6 sm:px-6 sm:py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <Breadcrumb />

        <header className="surface-linear-card p-5">
          <div className="flex items-center gap-2">
            <Sliders size={16} className="text-(--color-brand-hover)" />
            <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
              Run presets
            </h1>
          </div>
          <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
            Save and reuse named run configurations — idea iterations, max
            revision iters, journal, domain, executor. Apply at run-start time
            instead of re-typing every field.
          </p>
        </header>

        <RunPresetsClient />
      </div>
    </div>
  );
}

function Breadcrumb() {
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex items-center gap-1.5 text-[12px] text-(--color-text-tertiary-spec)"
    >
      <Link
        href="/settings"
        className={cn("transition-colors hover:text-(--color-text-primary)")}
      >
        Settings
      </Link>
      <ChevronRight size={12} className="text-(--color-text-quaternary)" />
      <span className="text-(--color-text-primary)">Run presets</span>
    </nav>
  );
}
