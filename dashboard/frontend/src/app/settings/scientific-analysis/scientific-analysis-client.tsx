"use client";

import * as React from "react";
import { AlertCircle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1";

type CapabilityDecision =
  | "integrate_core"
  | "optional_adapter"
  | "external_adapter"
  | "defer";

type CapabilityStatus = "available" | "missing";

interface ScientificCapability {
  name: string;
  domain: string;
  package: string | null;
  decision: CapabilityDecision;
  status: CapabilityStatus;
  priority: "high" | "medium" | "low";
  rationale: string;
  integration: string;
  artifacts: string[];
  verification: string[];
  install_hint?: string | null;
  caveats: string[];
}

interface VerificationCheck {
  name: string;
  domain: string;
  expected: number | string;
  observed: number | string;
  tolerance: number;
  passed: boolean;
  method: string;
}

interface ScientificCapabilityReport {
  summary: string;
  publication_contract: string[];
  capabilities: ScientificCapability[];
  verification_checks: VerificationCheck[];
  fingerprint: string;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; report: ScientificCapabilityReport };

async function fetchReport(): Promise<ScientificCapabilityReport> {
  const response = await fetch(`${API_BASE}/scientific-capabilities`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as ScientificCapabilityReport;
}

export function ScientificAnalysisClient() {
  const [state, setState] = React.useState<LoadState>({ kind: "loading" });

  const load = React.useCallback(async () => {
    setState({ kind: "loading" });
    try {
      setState({ kind: "ready", report: await fetchReport() });
    } catch (error) {
      setState({
        kind: "error",
        message:
          error instanceof Error
            ? error.message
            : "Failed to load scientific capabilities",
      });
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") {
    return (
      <div className="surface-linear-card flex items-center gap-2 p-5 text-[13px] text-(--color-text-tertiary)">
        <Loader2 size={14} strokeWidth={1.75} className="animate-spin" />
        Loading scientific analysis capabilities...
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div
        role="alert"
        className="surface-linear-card flex items-start justify-between gap-4 p-5 text-[13px]"
      >
        <div className="flex items-start gap-2 text-(--color-status-red-spec)">
          <AlertCircle size={14} strokeWidth={1.75} className="mt-0.5" />
          <span>{state.message}</span>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center gap-1 rounded-[6px] border border-(--color-border-card) px-2.5 py-1 text-[12px] text-(--color-text-secondary) hover:bg-(--color-ghost-bg-hover)"
        >
          <RefreshCw size={12} strokeWidth={1.75} />
          Retry
        </button>
      </div>
    );
  }

  const { report } = state;
  const coreCount = report.capabilities.filter(
    (item) => item.decision === "integrate_core",
  ).length;
  const availableCount = report.capabilities.filter(
    (item) => item.status === "available",
  ).length;
  const passedChecks = report.verification_checks.filter((check) => check.passed)
    .length;

  return (
    <div className="space-y-6">
      <section className="surface-linear-card p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <h2 className="text-[15px] font-[510] tracking-[-0.2px] text-(--color-text-primary-strong)">
              Capability matrix
            </h2>
            <p className="mt-1 text-[13px] leading-[1.55] text-(--color-text-tertiary-spec)">
              {report.summary}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 self-start rounded-[6px] border border-(--color-border-card) px-2.5 py-1.5 text-[12px] text-(--color-text-secondary) hover:bg-(--color-ghost-bg-hover)"
          >
            <RefreshCw size={12} strokeWidth={1.75} />
            Refresh
          </button>
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-4">
          <Metric label="Core stacks" value={coreCount} />
          <Metric label="Available now" value={availableCount} />
          <Metric label="Checks passed" value={`${passedChecks}/${report.verification_checks.length}`} />
          <Metric label="Fingerprint" value={report.fingerprint} mono />
        </div>
      </section>

      <section className="surface-linear-card p-5">
        <SectionTitle
          title="Publication contract"
          subtitle="Every scientific adapter must satisfy these artifact and provenance rules."
        />
        <ul className="mt-3 space-y-2">
          {report.publication_contract.map((item) => (
            <li
              key={item}
              className="flex gap-2 rounded-[6px] border border-(--color-border-card) px-3 py-2 text-[12.5px] leading-[1.45] text-(--color-text-secondary)"
            >
              <CheckCircle2
                size={14}
                strokeWidth={1.75}
                className="mt-0.5 shrink-0 text-(--color-status-emerald)"
              />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="surface-linear-card p-5">
        <SectionTitle
          title="Repeatability checks"
          subtitle="Deterministic smoke checks used to validate numerical and scientific assumptions."
        />
        <div className="mt-3 grid gap-2 lg:grid-cols-2">
          {report.verification_checks.map((check) => (
            <div
              key={check.name}
              className="rounded-[8px] border border-(--color-border-card) px-3 py-2.5"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[13px] font-medium text-(--color-text-primary)">
                    {check.name}
                  </div>
                  <div className="mt-0.5 text-[11.5px] capitalize text-(--color-text-tertiary)">
                    {check.domain}
                  </div>
                </div>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 font-mono text-[11px]",
                    check.passed
                      ? "bg-(--color-status-emerald)/12 text-(--color-status-emerald)"
                      : "bg-(--color-status-red)/12 text-(--color-status-red-spec)",
                  )}
                >
                  {check.passed ? "passed" : "failed"}
                </span>
              </div>
              <p className="mt-2 text-[12px] leading-[1.45] text-(--color-text-tertiary-spec)">
                {check.method}
              </p>
              <dl className="mt-2 grid grid-cols-2 gap-2 text-[11.5px]">
                <KeyValue label="Expected" value={formatCheckValue(check.expected)} />
                <KeyValue label="Observed" value={formatCheckValue(check.observed)} />
              </dl>
            </div>
          ))}
        </div>
      </section>

      <section className="surface-linear-card p-5">
        <SectionTitle
          title="Libraries"
          subtitle="Core dependencies, optional adapters, and external integrations by scientific domain."
        />
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {report.capabilities.map((item) => (
            <article
              key={`${item.domain}-${item.name}`}
              className="rounded-[8px] border border-(--color-border-card) px-3 py-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="text-[13px] font-medium text-(--color-text-primary)">
                    {item.name}
                  </h3>
                  <p className="mt-0.5 text-[11.5px] capitalize text-(--color-text-tertiary)">
                    {item.domain}
                    {item.package ? ` · ${item.package}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap justify-end gap-1">
                  <Pill>{decisionLabel(item.decision)}</Pill>
                  <Pill tone={item.status === "available" ? "ok" : "muted"}>
                    {item.status}
                  </Pill>
                </div>
              </div>
              <p className="mt-2 text-[12px] leading-[1.45] text-(--color-text-secondary)">
                {item.rationale}
              </p>
              <p className="mt-2 text-[12px] leading-[1.45] text-(--color-text-tertiary-spec)">
                {item.integration}
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                {item.artifacts.map((artifact) => (
                  <Pill key={artifact} tone="muted">
                    {artifact}
                  </Pill>
                ))}
              </div>
              {item.install_hint ? (
                <code className="mt-2 block rounded-[6px] bg-(--color-ghost-bg) px-2 py-1 font-mono text-[11px] text-(--color-text-tertiary)">
                  {item.install_hint}
                </code>
              ) : null}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function SectionTitle({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <div>
      <h2 className="text-[15px] font-[510] tracking-[-0.2px] text-(--color-text-primary-strong)">
        {title}
      </h2>
      {subtitle ? (
        <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
          {subtitle}
        </p>
      ) : null}
    </div>
  );
}

function Metric({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="rounded-[6px] border border-(--color-border-card) px-3 py-2">
      <div className="text-[11px] text-(--color-text-tertiary)">{label}</div>
      <div
        className={cn(
          "mt-1 text-[16px] font-medium text-(--color-text-primary)",
          mono && "font-mono text-[13px]",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[6px] bg-(--color-ghost-bg) px-2 py-1">
      <dt className="text-(--color-text-tertiary)">{label}</dt>
      <dd className="mt-0.5 break-words font-mono text-[11px] text-(--color-text-secondary)">
        {value}
      </dd>
    </div>
  );
}

function Pill({
  children,
  tone = "default",
}: {
  children: React.ReactNode;
  tone?: "default" | "muted" | "ok";
}) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[11px]",
        tone === "ok"
          ? "bg-(--color-status-emerald)/12 text-(--color-status-emerald)"
          : tone === "muted"
            ? "bg-(--color-ghost-bg) text-(--color-text-tertiary)"
            : "bg-(--color-brand-indigo)/15 text-(--color-brand-hover)",
      )}
    >
      {children}
    </span>
  );
}

function decisionLabel(decision: CapabilityDecision): string {
  return decision.replaceAll("_", " ");
}

function formatCheckValue(value: number | string): string {
  if (typeof value === "string") return value;
  if (Number.isInteger(value)) return String(value);
  return Number(value.toPrecision(8)).toString();
}
