import type { Metadata } from "next";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { LicensesClient } from "./licenses-client";

// Page-level metadata so /settings/licenses gets its own browser-tab
// title and shareable preview, instead of inheriting the generic
// "Settings — Plato" from the parent layout. This is the whole reason
// for the RSC chrome split: a "use client" page.tsx can't export
// `metadata` (Next.js rejects it at build time).
export const metadata: Metadata = {
  title: "Licenses & SBOM — Plato",
  description:
    "GPLv3 compatibility audit for every installed Python distribution, plus the CycloneDX SBOM the CI pipeline ships.",
};

/**
 * RSC chrome for /settings/licenses.
 *
 * Renders the static header / breadcrumb on the server and delegates
 * every interactive piece (audit fetch, error state, SBOM download)
 * to {@link LicensesClient} — the client island. Splitting the chrome
 * shaves the JS bundle for the page wrapper and unlocks page-level
 * `metadata` (which a "use client" file cannot export).
 */
export default function LicensesSettingsPage() {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-3 py-6 sm:px-6 sm:py-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <header
          className="surface-linear-card p-5"
          data-testid="licenses-page-header"
        >
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
            <span className="text-(--color-text-primary)">Licenses & SBOM</span>
          </nav>
          <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
            Licenses & SBOM
          </h1>
          <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
            GPLv3 compatibility audit for every installed Python distribution,
            plus the CycloneDX SBOM the CI pipeline ships.
          </p>
        </header>

        <LicensesClient />
      </div>
    </div>
  );
}
