import type { Metadata } from "next";
import Link from "next/link";
import { ChevronRight, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { LlmProvidersClient } from "./llm-providers-client";

// Page-level metadata so /settings/llm-providers gets its own browser tab
// title; impossible while the page itself was a "use client" module.
export const metadata: Metadata = {
  title: "LLM Providers — Plato",
  description:
    "Pick which provider/model Plato uses for each stage. Add API keys under /keys.",
};

/**
 * RSC chrome for /settings/llm-providers.
 *
 * Renders the breadcrumb + page header on the server and delegates the
 * provider grid + per-stage model pickers + save mutation to the client
 * island {@link LlmProvidersClient}. Mirrors the executors / licenses
 * settings pages so the surface stays consistent.
 */
export default function LlmProvidersSettingsPage() {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-3 py-6 sm:px-6 sm:py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <Breadcrumb />

        <header className="surface-linear-card p-5">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-(--color-brand-hover)" />
            <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
              LLM Providers
            </h1>
          </div>
          <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
            Pick which provider and model Plato uses for each stage. Provider
            credentials live under{" "}
            <Link
              href="/keys"
              className="text-(--color-brand-hover) hover:underline"
            >
              /keys
            </Link>
            .
          </p>
        </header>

        <LlmProvidersClient />
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
      <span className="text-(--color-text-primary)">LLM Providers</span>
    </nav>
  );
}
