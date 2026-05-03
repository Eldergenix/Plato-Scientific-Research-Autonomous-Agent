"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, LineChart, Sparkles, X as CloseIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TableSkeleton } from "@/components/shell/route-loading";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

// Mirror of evals/runner.py:_summarize output shape. Each metric
// reports {count, mean, p50, p95}; an empty count means no task in
// the panel produced that metric.
interface MetricSummary {
  count: number;
  mean?: number;
  p50?: number;
  p95?: number;
}

interface EvalSummary {
  task_count: number;
  task_ids: string[];
  metrics: Record<string, MetricSummary>;
}

type Loadable<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T }
  | { kind: "missing" }
  | { kind: "error"; message: string };

const METRIC_LABELS: Record<string, string> = {
  citation_validation_rate: "Citation validation rate",
  unsupported_claim_rate: "Unsupported claim rate",
  novelty_consistency: "Novelty (judge)",
  referee_severity_max: "Max referee severity",
  paper_coherence: "Paper coherence (judge)",
  cost_usd: "Cost (USD)",
  tokens_in: "Tokens in",
  tokens_out: "Tokens out",
  latency_seconds: "Latency (seconds)",
  tool_call_error_rate: "Tool error rate",
  keyword_recall: "Keyword recall",
  gold_source_recall: "Gold-source recall",
};

function formatNumber(value: number | undefined): string {
  if (value === undefined) return "—";
  if (Math.abs(value) >= 1000) return value.toFixed(0);
  return value.toFixed(3).replace(/\.?0+$/, "");
}

export default function EvalsPage() {
  const [state, setState] = React.useState<Loadable<EvalSummary>>({
    kind: "loading",
  });
  // Per-task drill-down: clicking a task id pulls its full
  // metrics.json into a side panel without leaving the page.
  const [openTask, setOpenTask] = React.useState<string | null>(null);
  const [taskMetrics, setTaskMetrics] = React.useState<
    Loadable<Record<string, unknown>> | null
  >(null);

  React.useEffect(() => {
    if (!openTask) {
      setTaskMetrics(null);
      return;
    }
    let cancelled = false;
    setTaskMetrics({ kind: "loading" });
    fetch(`${API_BASE}/evals/tasks/${openTask}/metrics`, { cache: "no-store" })
      .then(async (resp) => {
        if (cancelled) return;
        if (resp.status === 404) {
          setTaskMetrics({ kind: "missing" });
          return;
        }
        if (!resp.ok) {
          setTaskMetrics({ kind: "error", message: `HTTP ${resp.status}` });
          return;
        }
        setTaskMetrics({ kind: "ready", data: await resp.json() });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTaskMetrics({
          kind: "error",
          message: err instanceof Error ? err.message : "Network error",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [openTask]);

  // Retry counter — bumping this re-runs the summary fetch effect.
  const [retryNonce, setRetryNonce] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    fetch(`${API_BASE}/evals/summary`, { cache: "no-store" })
      .then(async (resp) => {
        if (cancelled) return;
        if (resp.status === 404) {
          setState({ kind: "missing" });
          return;
        }
        if (!resp.ok) {
          setState({ kind: "error", message: `HTTP ${resp.status}` });
          return;
        }
        const data = (await resp.json()) as EvalSummary;
        setState({ kind: "ready", data });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Network error",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [retryNonce]);

  return (
    <div
      className="min-h-screen bg-(--color-bg-page) px-3 py-6 sm:px-6 sm:py-8"
      data-testid="evals-page"
    >
      <div className="mx-auto max-w-4xl space-y-6">
        <header
          className="surface-linear-card flex items-start gap-3 px-4 py-4"
          style={{ border: "1px solid var(--color-border-card)" }}
        >
          <LineChart
            size={20}
            strokeWidth={1.75}
            className="mt-0.5 text-(--color-brand-hover)"
          />
          <div>
            <h1 className="text-[18px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
              Evaluation summary
            </h1>
            <p className="mt-1 text-[12.5px] text-(--color-text-tertiary-spec)">
              Aggregated metrics from the most recent
              {" "}
              <code className="font-mono">python -m evals.runner</code>{" "}
              invocation. Updated nightly by the{" "}
              <code className="font-mono">eval-nightly.yml</code>{" "}
              GitHub Actions workflow.
            </p>
          </div>
        </header>

        {state.kind === "loading" ? (
          <section
            data-testid="evals-loading"
            className="surface-linear-card overflow-hidden"
            style={{ border: "1px solid var(--color-border-card)" }}
          >
            <TableSkeleton
              rows={6}
              columnWidths={["32%", "12%", "16%", "16%", "16%"]}
              caption="Loading eval summary"
            />
          </section>
        ) : null}

        {state.kind === "missing" ? (
          <EvalsEmptyState testId="evals-missing" />
        ) : null}

        {state.kind === "error" ? (
          <EvalsErrorCard
            message={state.message}
            onRetry={() => setRetryNonce((n) => n + 1)}
          />
        ) : null}

        {state.kind === "ready" && state.data.task_count === 0 ? (
          <EvalsEmptyState testId="evals-empty" />
        ) : null}

        {state.kind === "ready" && state.data.task_count > 0 ? (
          <>
            <section
              className="surface-linear-card px-4 py-4"
              data-testid="evals-task-list"
              style={{ border: "1px solid var(--color-border-card)" }}
            >
              <div className="text-[13px] font-medium text-(--color-text-primary-strong)">
                {state.data.task_count} task
                {state.data.task_count === 1 ? "" : "s"}
              </div>
              <ul className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                {state.data.task_ids.map((id) => (
                  <li key={id}>
                    <button
                      type="button"
                      onClick={() => setOpenTask(id)}
                      data-testid={`evals-task-pill-${id}`}
                      className="rounded-[6px] bg-(--color-bg-pill-inactive) px-2 py-1 font-mono text-(--color-text-row-meta) transition-colors hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)"
                    >
                      {id}
                    </button>
                  </li>
                ))}
              </ul>
            </section>

            {openTask ? (
              <section
                className="surface-linear-card px-4 py-4"
                data-testid="evals-task-detail"
                style={{ border: "1px solid var(--color-border-card)" }}
              >
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[11.5px] uppercase tracking-wide text-(--color-text-tertiary-spec)">
                      Task metrics
                    </div>
                    <div className="font-mono text-[13px] text-(--color-text-primary-strong)">
                      {openTask}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setOpenTask(null)}
                    aria-label="Close task detail"
                    className="rounded-[6px] p-1 text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover)"
                  >
                    <CloseIcon size={14} strokeWidth={1.75} />
                  </button>
                </div>
                {taskMetrics?.kind === "loading" ? (
                  <div className="text-[12.5px] text-(--color-text-tertiary)">
                    Loading metrics.json…
                  </div>
                ) : null}
                {taskMetrics?.kind === "missing" ? (
                  <div className="text-[12.5px] text-(--color-text-tertiary)">
                    No metrics.json on disk for this task yet.
                  </div>
                ) : null}
                {taskMetrics?.kind === "error" ? (
                  <div className="text-[12.5px] text-(--color-status-red-spec)">
                    {taskMetrics.message}
                  </div>
                ) : null}
                {taskMetrics?.kind === "ready" ? (
                  <pre className="overflow-x-auto rounded-[6px] bg-(--color-bg-pill-inactive) p-3 font-mono text-[11.5px] leading-relaxed text-(--color-text-secondary)">
                    {JSON.stringify(taskMetrics.data, null, 2)}
                  </pre>
                ) : null}
              </section>
            ) : null}

            <section
              className="surface-linear-card overflow-hidden"
              data-testid="evals-metrics-table"
              style={{ border: "1px solid var(--color-border-card)" }}
            >
              <table className="w-full text-[12.5px]">
                <thead className="bg-(--color-bg-pill-inactive) text-(--color-text-tertiary-spec)">
                  <tr>
                    <th className="px-3 py-2 text-left font-[510]">Metric</th>
                    <th className="px-3 py-2 text-right font-[510]">N</th>
                    <th className="px-3 py-2 text-right font-[510]">Mean</th>
                    <th className="px-3 py-2 text-right font-[510]">p50</th>
                    <th className="px-3 py-2 text-right font-[510]">p95</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(state.data.metrics).map(([key, m]) => (
                    <tr
                      key={key}
                      className="border-t border-(--color-border-card)"
                    >
                      <td className="px-3 py-2 text-(--color-text-primary)">
                        {METRIC_LABELS[key] ?? key}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-(--color-text-tertiary)">
                        {m.count}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-(--color-text-secondary)">
                        {formatNumber(m.mean)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-(--color-text-secondary)">
                        {formatNumber(m.p50)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-(--color-text-secondary)">
                        {formatNumber(m.p95)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        ) : null}
      </div>
    </div>
  );
}

function EvalsEmptyState({ testId }: { testId: string }) {
  return (
    <section
      data-testid={testId}
      className="surface-linear-card flex flex-col items-center gap-3 px-6 py-10 text-center"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <Sparkles
        size={20}
        strokeWidth={1.75}
        className="text-(--color-brand-hover)"
      />
      <p className="text-[13.5px] font-[510] text-(--color-text-primary)">
        No eval tasks yet
      </p>
      <p className="max-w-md text-[12.5px] text-(--color-text-tertiary-spec)">
        Run an eval task to populate this page. Either kick off a research run
        from a project, or schedule a recurring eval via{" "}
        <code className="font-mono text-[11.5px]">/loop</code>.
      </p>
      <div className="mt-1 flex gap-2">
        <Button asChild variant="primary" size="sm">
          <Link href="/projects">Open projects</Link>
        </Button>
        <Button asChild variant="ghost" size="sm">
          <Link href="/loop">Schedule via /loop</Link>
        </Button>
      </div>
    </section>
  );
}

function EvalsErrorCard({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <section
      data-testid="evals-error"
      className="surface-linear-card flex flex-col items-center gap-3 px-6 py-10 text-center"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <AlertTriangle
        size={20}
        strokeWidth={1.75}
        className="text-(--color-status-red-spec)"
      />
      <p className="text-[13.5px] font-[510] text-(--color-text-primary)">
        Failed to load eval summary
      </p>
      <p className="max-w-md font-mono text-[11.5px] text-(--color-text-tertiary-spec)">
        {message}
      </p>
      <Button variant="ghost" size="sm" onClick={onRetry}>
        Retry
      </Button>
    </section>
  );
}
