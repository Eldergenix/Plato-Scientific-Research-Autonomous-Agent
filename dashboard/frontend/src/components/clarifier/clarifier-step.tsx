"use client";

import * as React from "react";
import { CheckCircle2, MessageCircleQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ClarifyingQuestionsModal,
  type ClarificationsPayload,
} from "./clarifying-questions-modal";

export interface ClarifierStepProps {
  payload: ClarificationsPayload;
  runId: string;
  onSubmitted?: () => void;
  className?: string;
}

/**
 * Compact, inline-on-the-run-page version of the clarifier UI.
 *
 *  - When ``needs_clarification`` is false: render nothing.
 *  - Otherwise list the questions and offer an "Answer questions" button
 *    that opens the modal.
 *  - When answers were already submitted: collapse to a "submitted" badge.
 */
export function ClarifierStep({
  payload,
  runId,
  onSubmitted,
  className,
}: ClarifierStepProps) {
  const [modalOpen, setModalOpen] = React.useState(false);
  const [showAnswers, setShowAnswers] = React.useState(false);

  if (!payload.needs_clarification) return null;
  const { questions, answers_submitted } = payload;

  return (
    <section
      data-testid="clarifier-step"
      className={cn(
        "surface-linear-card flex flex-col gap-3 p-4",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-2">
        <h3 className="font-label flex items-center gap-2">
          <MessageCircleQuestion
            size={12}
            strokeWidth={1.75}
            className="text-(--color-brand-hover)"
          />
          Clarifying questions ({questions.length})
        </h3>
        {answers_submitted ? (
          <span
            data-testid="clarifier-submitted-badge"
            className="inline-flex items-center gap-1.5 rounded-full border border-[#262628] bg-[#141415] px-2 py-0.5 text-[11px] font-medium text-(--color-text-secondary-spec)"
          >
            <CheckCircle2
              size={11}
              strokeWidth={2}
              className="text-(--color-status-green,#10A37F)"
            />
            Answers submitted
          </span>
        ) : null}
      </header>

      <ul className="flex flex-col gap-1.5">
        {questions.map((q, idx) => (
          <li
            key={`${idx}-${q}`}
            className="flex items-start gap-2 text-[13px] leading-[1.5] text-(--color-text-primary)"
          >
            <span className="mt-[3px] inline-block size-1 flex-none rounded-full bg-(--color-text-tertiary-spec)" />
            <span>{q}</span>
          </li>
        ))}
      </ul>

      <div className="flex items-center gap-1.5">
        {answers_submitted ? (
          <Button
            type="button"
            variant="subtle"
            size="sm"
            onClick={() => setShowAnswers((v) => !v)}
            data-testid="clarifier-view-answers"
          >
            {showAnswers ? "Hide answers" : "View answers"}
          </Button>
        ) : (
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={() => setModalOpen(true)}
            data-testid="clarifier-open-modal"
          >
            Answer questions
          </Button>
        )}
      </div>

      {showAnswers && answers_submitted ? (
        <div
          data-testid="clarifier-submitted-note"
          className="rounded-[6px] border border-[#262628] bg-[#141415] px-3 py-2 text-[12px] text-(--color-text-row-meta)"
        >
          Answers were submitted for this run. The full payload is stored at{" "}
          <span className="font-mono text-(--color-text-secondary-spec)">
            runs/{runId}/clarifications_answers.json
          </span>
          .
        </div>
      ) : null}

      <ClarifyingQuestionsModal
        payload={payload}
        runId={runId}
        open={modalOpen}
        onOpenChange={setModalOpen}
        onSubmitted={onSubmitted}
      />
    </section>
  );
}
