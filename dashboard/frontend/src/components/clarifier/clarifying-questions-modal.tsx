"use client";

import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Check, MessageCircleQuestion, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface ClarificationsPayload {
  questions: string[];
  needs_clarification: boolean;
  answers_submitted: boolean;
}

export interface ClarifyingQuestionsModalProps {
  payload: ClarificationsPayload;
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmitted?: () => void;
}

/**
 * Auto-grow textarea: clamps to a min height, expands as the user types.
 * No external dep — we just sync ``style.height`` against ``scrollHeight``.
 */
function AutoTextarea({
  value,
  onChange,
  disabled,
  placeholder,
  ariaLabel,
  testId,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  placeholder?: string;
  ariaLabel: string;
  testId?: string;
}) {
  const ref = React.useRef<HTMLTextAreaElement | null>(null);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(el.scrollHeight, 64)}px`;
  }, [value]);

  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      placeholder={placeholder}
      aria-label={ariaLabel}
      data-testid={testId}
      rows={2}
      className={cn(
        "min-h-[64px] resize-none overflow-hidden rounded-[6px] border border-[#262628] bg-[#141415] px-2.5 py-2",
        "text-[13px] leading-[1.5] text-(--color-text-primary) placeholder:text-(--color-text-quaternary-spec)",
        "transition-colors hover:border-[#34343a]",
        "focus-visible:border-(--color-brand-indigo) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-indigo)",
        "disabled:opacity-50",
      )}
    />
  );
}

export function ClarifyingQuestionsModal({
  payload,
  runId,
  open,
  onOpenChange,
  onSubmitted,
}: ClarifyingQuestionsModalProps) {
  const { questions } = payload;
  const [answers, setAnswers] = React.useState<string[]>(() =>
    questions.map(() => ""),
  );
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [success, setSuccess] = React.useState(false);

  // When the modal opens (or the question set changes), reset state.
  React.useEffect(() => {
    if (open) {
      setAnswers(questions.map(() => ""));
      setError(null);
      setSuccess(false);
      setSubmitting(false);
    }
  }, [open, questions]);

  const allFilled =
    questions.length > 0 && answers.every((a) => a.trim().length > 0);
  const canSubmit = allFilled && !submitting;

  const handleAnswerChange = (idx: number, value: string) => {
    setAnswers((prev) => {
      const next = prev.slice();
      next[idx] = value;
      return next;
    });
  };

  const handleSubmit = async (e?: React.SyntheticEvent<HTMLFormElement>) => {
    e?.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const resp = await fetch(`/api/v1/runs/${runId}/clarifications`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ answers: answers.map((a) => a.trim()) }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        const msg =
          body?.detail?.message ?? body?.detail?.code ?? `HTTP ${resp.status}`;
        throw new Error(String(msg));
      }
      setSuccess(true);
      // Notify the parent first so it can refresh ``answers_submitted``
      // before the modal closes; that way the inline ClarifierStep
      // already shows its post-submit state by the time we close.
      onSubmitted?.();
      onOpenChange(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Submission failed";
      setError(msg);
      setSubmitting(false);
    }
  };

  const subtitle = `Plato has ${questions.length} question${
    questions.length === 1 ? "" : "s"
  }. Your answers steer the rest of the run.`;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=open]:fade-in-0"
        />
        <Dialog.Content
          data-testid="clarifying-questions-modal"
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[600px] max-w-[92vw] -translate-x-1/2 -translate-y-1/2",
            "max-h-[85vh] overflow-hidden",
            "surface-linear-card flex flex-col",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          )}
          onPointerDownOutside={(e) => {
            if (submitting) e.preventDefault();
          }}
          onEscapeKeyDown={(e) => {
            if (submitting) e.preventDefault();
          }}
        >
          <div className="flex h-11 flex-none items-center justify-between gap-2 border-b border-[#1D1D1F] px-4">
            <Dialog.Title className="flex items-center gap-2 text-[15px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
              <MessageCircleQuestion
                size={14}
                strokeWidth={1.75}
                className="text-(--color-brand-hover)"
              />
              Clarify your research question
            </Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              disabled={submitting}
              className={cn(
                "inline-flex size-7 items-center justify-center rounded-full text-(--color-text-tertiary-spec)",
                "transition-colors hover:bg-white/5 hover:text-(--color-text-primary)",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
                "disabled:opacity-40",
              )}
            >
              <X size={14} strokeWidth={1.75} />
            </Dialog.Close>
          </div>

          <Dialog.Description className="px-4 pt-3 text-[13px] text-(--color-text-secondary-spec)">
            {subtitle}
          </Dialog.Description>

          <form
            onSubmit={handleSubmit}
            className="flex min-h-0 flex-1 flex-col"
          >
            <div className="flex flex-col gap-4 overflow-y-auto px-4 py-3">
              {questions.length === 0 ? (
                <div className="rounded-[6px] border border-[#262628] bg-[#141415] px-3 py-2 text-[13px] text-(--color-text-row-meta)">
                  No clarifying questions for this run.
                </div>
              ) : (
                questions.map((q, idx) => (
                  <div
                    key={`${idx}-${q}`}
                    className="flex flex-col gap-1.5"
                    data-testid={`clarifying-question-${idx}`}
                  >
                    <label
                      htmlFor={`clarify-${idx}`}
                      className="block text-[12px] font-medium leading-[1.4] text-(--color-text-secondary-spec)"
                    >
                      <span className="mr-1.5 font-mono tabular-nums text-(--color-text-tertiary-spec)">
                        {idx + 1}.
                      </span>
                      {q}
                    </label>
                    <AutoTextarea
                      ariaLabel={q}
                      testId={`clarifying-answer-${idx}`}
                      value={answers[idx] ?? ""}
                      onChange={(v) => handleAnswerChange(idx, v)}
                      disabled={submitting || success}
                      placeholder="Type your answer..."
                    />
                  </div>
                ))
              )}

              {error ? (
                <div
                  data-testid="clarifying-error"
                  className="rounded-[6px] border border-(--color-status-red)/30 bg-(--color-status-red)/10 px-2.5 py-1.5 text-[12px] text-(--color-status-red)"
                >
                  {error}
                </div>
              ) : null}

              {success ? (
                <div
                  data-testid="clarifying-success"
                  className="flex items-center gap-2 rounded-[6px] border border-(--color-status-green,#10A37F)/30 bg-(--color-status-green,#10A37F)/10 px-2.5 py-1.5 text-[12px] text-(--color-status-green,#10A37F)"
                >
                  <Check size={12} strokeWidth={2} />
                  Answers submitted. Thanks.
                </div>
              ) : null}
            </div>

            <div className="hairline-t flex flex-none items-center justify-between gap-2 px-4 py-3">
              <span className="text-[12px] text-(--color-text-tertiary-spec)">
                {allFilled
                  ? "Ready to submit"
                  : `${answers.filter((a) => a.trim()).length}/${questions.length} answered`}
              </span>
              <div className="flex items-center gap-1.5">
                <Button
                  type="button"
                  variant="subtle"
                  size="sm"
                  disabled={submitting}
                  onClick={() => onOpenChange(false)}
                  data-testid="clarifying-cancel"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={!canSubmit || success}
                  data-testid="clarifying-submit"
                >
                  {submitting
                    ? "Submitting..."
                    : success
                      ? "Submitted"
                      : "Submit answers"}
                </Button>
              </div>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
