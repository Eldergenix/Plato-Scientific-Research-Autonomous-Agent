"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { PlayCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { loopApi, type LoopStartBody } from "./loop-api";

export interface LoopSettingsFormProps {
  /** Called when the start request succeeds. The dialog usually closes via this. */
  onStarted?: (loopId: string) => void;
}

interface FormState {
  projectDir: string;
  maxIters: string;
  timeBudgetHours: string;
  maxCostUsd: string;
  branchPrefix: string;
}

const INITIAL: FormState = {
  projectDir: "",
  maxIters: "",
  timeBudgetHours: "8",
  maxCostUsd: "50",
  branchPrefix: "plato-runs",
};

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[12px] font-medium text-(--color-text-secondary-spec)">
      {children}
    </label>
  );
}

const inputClass = cn(
  "h-8 w-full rounded-[6px] border border-[#262628] bg-[#141415] px-2.5",
  "text-[13px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary-spec)",
  "transition-colors hover:border-[#34343a]",
  "focus-visible:border-(--color-brand-indigo) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-indigo)",
  "disabled:opacity-50",
);

export function LoopSettingsForm({ onStarted }: LoopSettingsFormProps) {
  const router = useRouter();
  const [state, setState] = React.useState<FormState>(INITIAL);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const setField = (key: keyof FormState, value: string) =>
    setState((s) => ({ ...s, [key]: value }));

  const canSubmit = state.projectDir.trim().length > 0 && !submitting;

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const body: LoopStartBody = {
        project_dir: state.projectDir.trim(),
        max_iters:
          state.maxIters.trim() === "" ? null : Number.parseInt(state.maxIters, 10),
        time_budget_hours: Number.parseFloat(state.timeBudgetHours) || 8,
        max_cost_usd: Number.parseFloat(state.maxCostUsd) || 50,
        branch_prefix: state.branchPrefix.trim() || "plato-runs",
      };
      const started = await loopApi.start(body);
      // Push first so the navigation is in flight before the dialog closes
      // unmounts this component.
      router.push(`/loop/${started.loop_id}`);
      onStarted?.(started.loop_id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to start loop";
      setError(msg);
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-4">
      <div className="flex flex-col gap-1.5">
        <FieldLabel>Project directory</FieldLabel>
        <input
          autoFocus
          type="text"
          value={state.projectDir}
          onChange={(e) => setField("projectDir", e.target.value)}
          disabled={submitting}
          placeholder="/path/to/plato/project"
          className={inputClass}
          data-testid="loop-form-project-dir"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <FieldLabel>Max iterations</FieldLabel>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            value={state.maxIters}
            onChange={(e) => setField("maxIters", e.target.value)}
            disabled={submitting}
            placeholder="blank = unlimited"
            className={cn(inputClass, "tabular-nums")}
            data-testid="loop-form-max-iters"
          />
          <span className="text-[11px] text-(--color-text-tertiary-spec)">
            blank = unlimited
          </span>
        </div>
        <div className="flex flex-col gap-1.5">
          <FieldLabel>Branch prefix</FieldLabel>
          <input
            type="text"
            value={state.branchPrefix}
            onChange={(e) => setField("branchPrefix", e.target.value)}
            disabled={submitting}
            className={inputClass}
            data-testid="loop-form-branch-prefix"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <FieldLabel>Time budget (hours)</FieldLabel>
          <input
            type="number"
            inputMode="decimal"
            min={0.1}
            step="any"
            value={state.timeBudgetHours}
            onChange={(e) => setField("timeBudgetHours", e.target.value)}
            disabled={submitting}
            className={cn(inputClass, "tabular-nums")}
            data-testid="loop-form-time-budget"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <FieldLabel>Max cost (USD)</FieldLabel>
          <input
            type="number"
            inputMode="decimal"
            min={0.01}
            step="any"
            value={state.maxCostUsd}
            onChange={(e) => setField("maxCostUsd", e.target.value)}
            disabled={submitting}
            className={cn(inputClass, "tabular-nums")}
            data-testid="loop-form-max-cost"
          />
        </div>
      </div>

      {error ? (
        <div className="rounded-[6px] border border-(--color-status-red)/30 bg-(--color-status-red)/10 px-2.5 py-1.5 text-[12px] text-(--color-status-red)">
          {error}
        </div>
      ) : null}

      <div className="hairline-t -mx-4 -mb-4 mt-2 flex items-center justify-end gap-1.5 px-4 py-3">
        <Button
          type="submit"
          variant="primary"
          size="sm"
          disabled={!canSubmit}
          data-testid="loop-form-submit"
        >
          <PlayCircle size={12} strokeWidth={1.75} />
          {submitting ? "Starting…" : "Start loop"}
        </Button>
      </div>
    </form>
  );
}
