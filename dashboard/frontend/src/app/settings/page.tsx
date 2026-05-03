"use client";

import * as React from "react";
import Link from "next/link";
import {
  ChevronRight,
  Globe2,
  Info,
  Monitor,
  Moon,
  ScrollText,
  Server,
  Sliders,
  Sparkles,
  Sun,
  Trash2,
  CheckCircle2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTheme } from "@/components/shell/theme-provider";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { api, type TelemetryPreferences } from "@/lib/api";
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
    href: "/settings/llm-providers",
    label: "LLM Providers",
    description:
      "Pick the provider/model used per stage. Add credentials under /keys.",
    icon: Sparkles,
    testId: "settings-link-llm-providers",
  },
  {
    href: "/settings/run-presets",
    label: "Run presets",
    description:
      "Save named run configurations — idea iters, journal, executor — and reuse them at run-start.",
    icon: Sliders,
    testId: "settings-link-run-presets",
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

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();

  const [autoSkip, setAutoSkip] = React.useState<boolean>(false);
  const [hydrated, setHydrated] = React.useState(false);
  const [resetMsg, setResetMsg] = React.useState<string | null>(null);
  const [resetConfirmOpen, setResetConfirmOpen] = React.useState(false);

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
          <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
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
          <Checkbox
            checked={autoSkip}
            disabled={!hydrated}
            onCheckedChange={onAutoSkipChange}
            className="mt-3 items-start gap-3"
            label={
              <span>
                <span className="block text-[13px] font-[510] text-(--color-text-primary)">
                  Skip all approval gates
                </span>
                <span className="block text-[12px] text-(--color-text-tertiary)">
                  Auto-approve every checkpoint. Reads/writes{" "}
                  <code className="font-mono text-[11px]">{APPROVALS_AUTO_SKIP_KEY}</code>.
                </span>
              </span>
            }
          />
        </section>

        {/* Telemetry */}
        <TelemetrySection />

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
            <Button
              variant="danger"
              size="md"
              onClick={() => setResetConfirmOpen(true)}
            >
              <Trash2 size={13} strokeWidth={1.75} />
              Clear all local data
            </Button>
            {resetMsg ? (
              <span className="text-[12px] text-(--color-text-tertiary)">{resetMsg}</span>
            ) : null}
          </div>
        </section>
      </div>

      <ConfirmDialog
        open={resetConfirmOpen}
        onOpenChange={setResetConfirmOpen}
        title="Clear all locally-stored Plato data?"
        description="Removes API keys saved in-app, approval state, theme preference, and other settings stored under the plato: namespace. Server-side data is unaffected. This cannot be undone."
        confirmLabel="Clear local data"
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={onResetLocalData}
      />
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

// Local-only run-summary telemetry. Toggle persists in user_preferences.json
// on the server; aggregates render the last 30 entries from
// ~/.plato/telemetry.jsonl. Nothing about this section talks to a third
// party — we own the file and the user owns their machine.
function TelemetrySection() {
  const [prefs, setPrefs] = React.useState<TelemetryPreferences | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    api
      .getTelemetryPreferences()
      .then((p) => {
        if (!cancelled) setPrefs(p);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Failed to load.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onToggle = async (next: boolean) => {
    if (pending) return;
    setPending(true);
    const previous = prefs;
    // Optimistic — flip immediately, roll back on failure.
    setPrefs((p) => (p ? { ...p, telemetry_enabled: next } : p));
    try {
      const updated = await api.setTelemetryPreferences(next);
      setPrefs(updated);
      setLoadError(null);
    } catch (err) {
      setPrefs(previous);
      setLoadError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setPending(false);
    }
  };

  const enabled = prefs?.telemetry_enabled ?? false;
  const ready = prefs !== null;
  const agg = prefs?.aggregates;

  return (
    <section className="surface-linear-card p-5">
      <SectionTitle
        title="Telemetry"
        subtitle="Local-only usage stats. Never transmitted off this machine."
      />

      <Checkbox
        checked={enabled}
        disabled={!ready || pending}
        onCheckedChange={onToggle}
        data-testid="settings-telemetry-toggle"
        className="mt-3 items-start gap-3"
        label={
          <span>
            <span className="block text-[13px] font-[510] text-(--color-text-primary)">
              Track local usage stats (run counts, durations, token usage)
            </span>
            <span className="block text-[12px] text-(--color-text-tertiary)">
              Appended to{" "}
              <code className="font-mono text-[11px]">~/.plato/telemetry.jsonl</code>
              . Set <code className="font-mono text-[11px]">PLATO_TELEMETRY_DISABLED=1</code>{" "}
              to disable from the shell.
            </span>
          </span>
        }
      />

      <div className="mt-3 flex items-start gap-2 rounded-[8px] border border-(--color-border-card) bg-(--color-bg-pill-inactive) px-3 py-2">
        <Info
          size={14}
          strokeWidth={1.75}
          className="mt-0.5 text-(--color-text-tertiary)"
        />
        <p className="text-[12px] text-(--color-text-tertiary-spec)">
          What we record per run: timestamp, run_id, workflow name, duration,
          input/output tokens, cost, status. Nothing else — no prompts, no
          outputs, no project paths. The file lives entirely on your machine.
        </p>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <SummaryStat
          label="Recent runs"
          value={agg ? String(agg.total_runs) : "—"}
        />
        <SummaryStat
          label="Tokens (in / out)"
          value={
            agg
              ? `${formatInt(agg.total_tokens_in)} / ${formatInt(agg.total_tokens_out)}`
              : "—"
          }
        />
        <SummaryStat
          label="Cost (USD)"
          value={agg ? `$${agg.total_cost_usd.toFixed(4)}` : "—"}
        />
      </div>

      {loadError ? (
        <p className="mt-2 text-[12px] text-(--color-status-red)">{loadError}</p>
      ) : !ready ? (
        <p className="mt-2 text-[12px] text-(--color-text-tertiary)">Loading…</p>
      ) : (
        <p className="mt-2 text-[12px] text-(--color-text-tertiary)">
          {agg && agg.total_runs > 0
            ? `Aggregated from the last ${agg.total_runs} run${agg.total_runs === 1 ? "" : "s"}.`
            : "No runs recorded yet."}
        </p>
      )}
    </section>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) px-3 py-2">
      <div className="text-[11px] uppercase tracking-[0.04em] text-(--color-text-quaternary-spec)">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-[13px] text-(--color-text-primary)">
        {value}
      </div>
    </div>
  );
}

function formatInt(n: number): string {
  return new Intl.NumberFormat("en-US").format(Math.round(n));
}
