import type { Metadata } from "next";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { DomainsClient } from "./domains-client";

// Page-level metadata so /settings/domains gets its own browser-tab
// title — impossible while the page itself was a "use client" module.
export const metadata: Metadata = {
  title: "Domains — Plato",
  description:
    "Pick the DomainProfile that retrieval, drafting, and execution will consult by default.",
};

/**
 * RSC chrome for /settings/domains.
 *
 * Renders the back-link + page header on the server and delegates the
 * domain-selector + profile card + toggle interactions to the client
 * island {@link DomainsClient}. The data-fetching stays client-side so
 * the existing Playwright tests, which mock the backend with
 * `page.route()`, keep working unchanged.
 */
export default function DomainsSettingsPage() {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-3 py-6 sm:px-6 sm:py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <header className="surface-linear-card p-5">
          <Link
            href="/settings"
            className="inline-flex items-center gap-1 text-[12px] text-(--color-text-tertiary-spec) hover:text-(--color-text-primary)"
          >
            <ChevronLeft size={12} strokeWidth={1.75} />
            Settings
          </Link>
          <h1 className="mt-2 text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
            Domains
          </h1>
          <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
            Pick the DomainProfile that retrieval, drafting, and execution will
            consult by default. Each profile bundles its own retrieval
            adapters, keyword extractor, journal presets, executor, and novelty
            corpus.
          </p>
        </header>

        <DomainsClient />
      </div>
    </div>
  );
}
