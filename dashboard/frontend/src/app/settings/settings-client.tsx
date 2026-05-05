"use client";

import * as React from "react";
import Link from "next/link";
import {
  ChevronRight,
  Globe2,
  Monitor,
  Moon,
  ScrollText,
  Server,
  Sun,
  Trash2,
  CheckCircle2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTheme } from "@/components/shell/theme-provider";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

// Mirror of RECOMMENDED_BY_STAGE in src/app/models/page.tsx — kept in sync
// manually rather than re-exported to avoid pulling that page's heavy
// transitive deps into the settings route.
const DEFAULT_MODELS: Array<{ id: string; label: string; model: string }> = [
  { id: "idea", label: "Idea", model: "gpt-4.1" },
  { id: "literature", label: "Literature", model: "gpt-4.1-mini" },
  { id: "method", label: "Method", model: "claude-4.1-opus" },
  { id: "results", label: "Results", model: "gpt-5" },
  { id: "paper", label: "Paper", model: "claude-4.1-opus" },
  { id: "referee", label: "Referee", model: "o3-mini" },
];

const APPROVALS_AUTO_SKIP_KEY = "plato:approvals:auto-skip";
const PLATO_KEY_PREFIX = "plato:";

type ThemeChoice = "dark" | "light" | "system";

const SETTINGS_SECTIONS: Array<{
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
  testId: string;
}> = [
  {
    href: "/settings/domains",
    label: "Domains",
    description:
      "Pick the DomainProfile that drives retrieval, drafting, and execution.",
    icon: Globe2,
    testId: "settings-link-domains",
  },
  {
    href: "/settings/executors",
    label: "Executors",
    description:
      "Choose how Plato runs scientific code — cmbagent, local Jupyter, Modal, or E2B.",
    icon: Server,
    testId: "settings-link-executors",
  },
  {
    href: "/settings/licenses",
    label: "Licenses & SBOM",
    description:
      "Audit third-party license compatibility and download a CycloneDX SBOM.",
    icon: ScrollText,
    testId: "settings-link-licenses",
  },
];

const THEME_OPTIONS: Array<{
  value: ThemeChoice;
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  {
    value: "dark",
    label: "Dark",
    description: "Plato's default — tuned tokens.",
    icon: Moon,
  },
  {
    value: "light",
    label: "Light",
    description: "Minimum-viable light palette.",
    icon: Sun,
  },
  {
    value: "system",
    label: "System",
    description: "Match your OS preference.",
    icon: Monitor,
  },
];

export function SettingsClient() {
  const { theme, setTheme } = useTheme();

  const [autoSkip, setAutoSkip] = React.useState<boolean>(false);
  const [hydrated, setHydrated] = React.useState(false);
  const [resetMsg, setResetMsg] = React.useState<string | null>(null);

  // Hydrate localStorage-backed state on mount.
  React.useEffect(() => {
    try {
      const v = window.localStorage.getItem(APPROVALS_AUTO_SKIP_KEY);
      setAutoSkip(v === "1" || v === "true");
    } catch {
      /* ignore */
    }
    setHydrated(true);
  }, []);

  const onAutoSkipChange = (next: boolean) => {
    setAutoSkip(next);
    try {
      if (next) window.localStorage.setItem(APPROVALS_AUTO_SKIP_KEY, "1");
      else window.localStorage.removeItem(APPROVALS_AUTO_SKIP_KEY);
    } catch {
      /* ignore */
    }
  };

  const onResetLocalData = () => {
    if (typeof window === "undefined") return;
    const ok = window.confirm(
      "Clear all locally-stored Plato data? This removes API keys saved in-app, approval state, theme preference, and other settings stored under the plato: namespace. This cannot be undone.",
    );
    if (!ok) return;
    try {
      const keys: string[] = [];
      for (let i = 0; i < window.localStorage.length; i += 1) {
        const k = window.localStorage.key(i);
        if (k && k.startsWith(PLATO_KEY_PREFIX)) keys.push(k);
      }
      keys.forEach((k) => window.localStorage.removeItem(k));
      setResetMsg(`Cleared ${keys.length} ${keys.length === 1 ? "entry" : "entries"}.`);
      // Reset local state that mirrors storage.
      setAutoSkip(false);
    } catch (err) {
      setResetMsg(`Failed to clear: ${(err as Error).message}`);
    }
  };

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Header card */}
        <header className="surface-linear-card p-5">
          <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
            Settings
          </h1>
          <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
            Local preferences for the Plato dashboard. Stored in your browser only.
          </p>
        </header>

        {/* Configuration sections — server-backed, not browser-local. */}
        <section
          className="surface-linear-card p-5"
          data-testid="settings-section-links"
        >
          <SectionTitle
            title="Configuration"
            subtitle="Server-side settings that affect every project in this workspace."
          />
          <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {SETTINGS_SECTIONS.map((section) => {
              const Icon = section.icon;
              return (
                <li key={section.href}>
                  <Link
                    href={section.href}
                    data-testid={section.testId}
                    className={cn(
                      "group flex h-full flex-col gap-1.5 rounded-[10px] border p-3 text-left transition-colors",
                      "border-(--color-border-card) bg-(--color-bg-card) hover:border-(--color-brand-indigo) hover:bg-(--color-ghost-bg-hover)",
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <Icon
                        size={16}
                        strokeWidth={1.75}
                        className="text-(--color-text-tertiary) group-hover:text-(--color-brand-hover)"
                      />
                      <ChevronRight
                        size={14}
                        strokeWidth={1.75}
                        className="text-(--color-text-quaternary-spec) group-hover:text-(--color-brand-hover)"
                      />
                    </div>
                    <div>
                      <div className="text-[13px] font-[510] text-(--color-text-primary)">
                        {section.label}
                      </div>
                      <div className="mt-0.5 text-[12px] text-(--color-text-tertiary)">
                        {section.description}
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>

        {/* Appearance */}
        <section className="surface-linear-card p-5">
          <SectionTitle title="Appearance" subtitle="Pick how Plato looks." />
          <div
            role="radiogroup"
            aria-label="Theme"
            className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3"
          >
            {THEME_OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const active = theme === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setTheme(opt.value)}
                  className={cn(
                    "flex flex-col items-start gap-2 rounded-[10px] border p-3 text-left transition-colors",
                    active
                      ? "border-(--color-brand-indigo) bg-(--color-brand-indigo)/10"
                      : "border-(--color-border-card) bg-(--color-bg-card) hover:bg-(--color-ghost-bg-hover)",
                  )}
                >
                  <div className="flex w-full items-center justify-between">
                    <Icon
                      size={16}
                      strokeWidth={1.75}
                      className={cn(
                        active
                          ? "text-(--color-brand-hover)"
                          : "text-(--color-text-tertiary)",
                      )}
                    />
                    {active ? (
                      <CheckCircle2
                        size={14}
                        strokeWidth={1.75}
                        className="text-(--color-brand-hover)"
                      />
                    ) : null}
                  </div>
                  <div>
                    <div className="text-[13px] font-[510] text-(--color-text-primary)">
                      {opt.label}
                    </div>
                    <div className="text-[12px] text-(--color-text-tertiary)">
                      {opt.description}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        {/* Defaults — read-only */}
        <section className="surface-linear-card p-5">
          <SectionTitle
            title="Defaults"
            subtitle="Recommended models per stage. Edit per project from /models."
          />
          <div className="mt-3 overflow-hidden rounded-[8px] border border-(--color-border-card)">
            <table className="w-full text-[13px]">
              <thead className="bg-(--color-bg-pill-inactive) text-(--color-text-tertiary-spec)">
                <tr>
                  <th className="px-3 py-2 text-left font-[510]">Stage</th>
                  <th className="px-3 py-2 text-left font-[510]">Model</th>
                </tr>
              </thead>
              <tbody>
                {DEFAULT_MODELS.map((row, idx) => (
                  <tr
                    key={row.id}
                    className={cn(
                      idx > 0 ? "border-t border-(--color-border-card)" : "",
                      "bg-(--color-bg-card)",
                    )}
                  >
                    <td className="px-3 py-2 text-(--color-text-primary)">{row.label}</td>
                    <td className="px-3 py-2 font-mono text-[12px] text-(--color-text-secondary)">
                      {row.model}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Approvals */}
        <section className="surface-linear-card p-5">
          <SectionTitle
            title="Approvals"
            subtitle="Control when Plato pauses for your approval between stages."
          />
          <label className="mt-3 flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={autoSkip}
              disabled={!hydrated}
              onChange={(e) => onAutoSkipChange(e.target.checked)}
              className="mt-0.5 h-4 w-4 cursor-pointer disabled:cursor-not-allowed"
            />
            <span>
              <span className="block text-[13px] font-[510] text-(--color-text-primary)">
                Skip all approval gates
              </span>
              <span className="block text-[12px] text-(--color-text-tertiary)">
                Auto-approve every checkpoint. Reads/writes{" "}
                <code className="font-mono text-[11px]">{APPROVALS_AUTO_SKIP_KEY}</code>.
              </span>
            </span>
          </label>
        </section>

        {/* Telemetry */}
        <section className="surface-linear-card p-5">
          <SectionTitle title="Telemetry" subtitle="Help improve Plato with anonymous usage data." />
          <div className="mt-3 flex items-center justify-between gap-3 rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) px-3 py-2.5">
            <div>
              <div className="text-[13px] text-(--color-text-primary)">
                Telemetry: not yet implemented
              </div>
              <div className="text-[12px] text-(--color-text-tertiary)">
                This setting will become active once the backend collector ships.
              </div>
            </div>
            <Pill tone="neutral">disabled</Pill>
          </div>
        </section>

        {/* Reset (danger) */}
        <section
          className="surface-linear-card p-5"
          style={{ borderColor: "rgba(235, 87, 87, 0.3)" }}
        >
          <SectionTitle title="Reset" subtitle="Clear locally-stored Plato data." danger />
          <p className="mt-2 text-[12px] text-(--color-text-tertiary)">
            Removes everything under the <code className="font-mono">plato:</code> namespace
            from this browser — in-app API keys, approval state, theme preference, and any
            other locally-saved setting. Server-side data is unaffected.
          </p>
          <div className="mt-3 flex items-center gap-3">
            <Button variant="danger" size="md" onClick={onResetLocalData}>
              <Trash2 size={13} strokeWidth={1.75} />
              Clear all local data
            </Button>
            {resetMsg ? (
              <span className="text-[12px] text-(--color-text-tertiary)">{resetMsg}</span>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}

function SectionTitle({
  title,
  subtitle,
  danger,
}: {
  title: string;
  subtitle?: string;
  danger?: boolean;
}) {
  return (
    <div>
      <h2
        className={cn(
          "text-[15px] font-[510] tracking-[-0.2px]",
          danger ? "text-(--color-status-red)" : "text-(--color-text-primary-strong)",
        )}
      >
        {title}
      </h2>
      {subtitle ? (
        <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">{subtitle}</p>
      ) : null}
    </div>
  );
}
