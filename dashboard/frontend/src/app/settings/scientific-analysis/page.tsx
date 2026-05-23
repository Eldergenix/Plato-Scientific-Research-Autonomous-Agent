import type { Metadata } from "next";
import Link from "next/link";
import { Atom, ChevronRight } from "lucide-react";
import { ScientificAnalysisClient } from "./scientific-analysis-client";

export const metadata: Metadata = {
  title: "Scientific Analysis — Plato",
  description:
    "Scientific library capability decisions, artifact contracts, and repeatability checks for Plato publications.",
};

export default function ScientificAnalysisSettingsPage() {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-3 py-6 sm:px-6 sm:py-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="surface-linear-card p-5">
          <nav
            aria-label="Breadcrumb"
            className="mb-2 flex items-center gap-1 text-[12px] text-(--color-text-tertiary)"
          >
            <Link
              href="/settings"
              className="hover:text-(--color-text-primary) hover:underline"
            >
              Settings
            </Link>
            <ChevronRight size={12} strokeWidth={1.75} />
            <span className="text-(--color-text-primary)">Scientific analysis</span>
          </nav>
          <div className="flex items-center gap-2">
            <Atom size={16} className="text-(--color-brand-hover)" />
            <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
              Scientific analysis
            </h1>
          </div>
          <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
            Review which scientific stacks belong in Plato&apos;s publication
            baseline, which stay optional, and which need external adapters.
          </p>
        </header>

        <ScientificAnalysisClient />
      </div>
    </div>
  );
}
