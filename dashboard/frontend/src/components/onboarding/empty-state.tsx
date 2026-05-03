"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Circle, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

interface OnboardingStep {
  id: "key" | "domain" | "run";
  title: string;
  description: string;
  href: string;
  cta: string;
  done: boolean;
}

export function OnboardingEmptyState({
  hasApiKey,
  hasProject,
}: {
  hasApiKey: boolean;
  hasProject: boolean;
}) {
  const steps: OnboardingStep[] = [
    {
      id: "key",
      title: "Add an LLM API key",
      description:
        "Plato calls OpenAI, Anthropic, Gemini, or Perplexity to draft ideas, score novelty, and write methods. Configure at least one to unlock pipeline runs.",
      href: "/keys",
      cta: "Open /keys",
      done: hasApiKey,
    },
    {
      id: "domain",
      title: "Pick a domain (astro / biology / ml)",
      description:
        "Domain profiles ship preset prompts, journal templates, and keyword extractors so the agent reasons about your field with the right vocabulary.",
      href: "/settings/domains",
      cta: "Open /settings/domains",
      done: hasProject,
    },
    {
      id: "run",
      title: "Start your first research run",
      description:
        "Once a key and domain are set, kick off the autonomous loop. The agent will iterate from idea to draft paper, with checkpoints you can approve.",
      href: "/loop",
      cta: "Open /loop",
      done: false,
    },
  ];

  const completedCount = steps.filter((s) => s.done).length;

  return (
    <div
      className="flex h-full overflow-y-auto"
      data-testid="onboarding-empty-state"
    >
      <main className="flex-1 flex flex-col items-center justify-start gap-6 px-6 py-10">
        <div className="size-12 rounded-full bg-(--color-ghost-bg) hairline-r hairline-l hairline-t hairline-b flex items-center justify-center">
          <Sparkles size={20} strokeWidth={1.5} className="text-(--color-text-tertiary)" />
        </div>
        <div className="flex flex-col items-center gap-2 max-w-xl">
          <h1 className="font-h1 tracking-[-0.704px]">
            Welcome to Plato — autonomous research in 3 steps
          </h1>
          <p className="text-[13.5px] text-(--color-text-tertiary) text-center leading-[1.6]">
            Finish the checklist to unlock your first run. Your progress is
            saved automatically as you complete each step.
          </p>
          <div
            className="text-[12px] text-(--color-text-tertiary) mt-1"
            aria-live="polite"
          >
            {completedCount} of {steps.length} complete
          </div>
        </div>

        <ol
          className="w-full max-w-2xl flex flex-col gap-2"
          aria-label="Onboarding checklist"
        >
          {steps.map((step, idx) => (
            <li key={step.id}>
              <StepCard step={step} index={idx + 1} />
            </li>
          ))}
        </ol>
      </main>
    </div>
  );
}

function StepCard({ step, index }: { step: OnboardingStep; index: number }) {
  return (
    <div
      className="surface-card px-4 py-3.5 flex items-start gap-3"
      data-testid={`onboarding-step-${step.id}`}
      data-done={step.done ? "true" : "false"}
    >
      <div className="mt-0.5 shrink-0">
        {step.done ? (
          <CheckCircle2
            size={18}
            strokeWidth={1.75}
            className="text-(--color-status-green)"
            aria-label="Step complete"
          />
        ) : (
          <Circle
            size={18}
            strokeWidth={1.75}
            className="text-(--color-text-quaternary)"
            aria-label="Step incomplete"
          />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-[11.5px] font-mono text-(--color-text-quaternary)">
            Step {index}
          </span>
          <h2 className="text-[13.5px] font-medium text-(--color-text-primary)">
            {step.title}
          </h2>
        </div>
        <p className="text-[12.5px] text-(--color-text-tertiary) mt-1 leading-[1.55]">
          {step.description}
        </p>
      </div>
      <div className="shrink-0">
        <Button
          asChild
          variant={step.done ? "ghost" : "primary"}
          size="sm"
        >
          <Link href={step.href}>
            {step.cta}
            <ArrowRight size={12} strokeWidth={1.75} />
          </Link>
        </Button>
      </div>
    </div>
  );
}
