import type { Metadata } from "next";
import Link from "next/link";
import { ChevronRight, Cpu } from "lucide-react";
import { cn } from "@/lib/utils";
import { ExecutorsClient } from "./executors-client";

// Page-level metadata so /settings/executors gets its own browser tab
// title; impossible while the page itself was a "use client" module.
export const metadata: Metadata = {
  title: "Executors — Plato",
  description:
    "Pick which code-execution backend Plato uses for new runs. cmbagent is the recommended default.",
};

/**
 * RSC chrome for /settings/executors.
 *
 * Renders the breadcrumb + page header on the server and delegates
 * the executor list + selector + default-toggle interactions to the
 * client island {@link ExecutorsClient}.
 */
export default function ExecutorsSettingsPage() {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-3 py-6 sm:px-6 sm:py-8">
      <div className="mx-auto max-w-3xl space-y-6">
        <Breadcrumb />

        <header className="surface-linear-card p-5">
          <div className="flex items-center gap-2">
            <Cpu size={16} className="text-(--color-brand-hover)" />
            <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
              Executors
            </h1>
          </div>
          <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
            Pick which code-execution backend Plato uses for new runs.{" "}
            <span className="font-mono text-[12px]">cmbagent</span> is the
            recommended default.
          </p>
        </header>

        <ExecutorsClient />
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
      <span className="text-(--color-text-primary)">Executors</span>
    </nav>
  );
}
