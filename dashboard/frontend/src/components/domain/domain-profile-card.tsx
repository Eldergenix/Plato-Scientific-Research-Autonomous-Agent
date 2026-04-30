"use client";

import * as React from "react";
import { CheckCircle2, Loader2, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

export interface DomainProfileFull {
  name: string;
  retrieval_sources: string[];
  keyword_extractor: string;
  journal_presets: string[];
  executor: string;
  novelty_corpus: string;
}

export interface DomainProfileCardProps {
  profile: DomainProfileFull;
  isDefault: boolean;
  onSetDefault: () => void | Promise<void>;
  saving?: boolean;
}

export function DomainProfileCard({
  profile,
  isDefault,
  onSetDefault,
  saving = false,
}: DomainProfileCardProps) {
  return (
    <article
      className="surface-linear-card p-5"
      data-testid={`domain-card-${profile.name}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-[16px] font-[510] tracking-[-0.2px] text-(--color-text-primary-strong)">
            {profile.name}
          </h2>
          {isDefault ? (
            <Pill tone="indigo" data-testid="domain-default-pill">
              <Star size={10} strokeWidth={2} />
              Default
            </Pill>
          ) : null}
        </div>
        <Button
          variant={isDefault ? "subtle" : "primary"}
          size="md"
          disabled={isDefault || saving}
          onClick={() => onSetDefault()}
          data-testid="domain-set-default-button"
        >
          {saving ? (
            <Loader2 size={13} strokeWidth={1.75} className="animate-spin" />
          ) : isDefault ? (
            <CheckCircle2 size={13} strokeWidth={1.75} />
          ) : null}
          {isDefault ? "Default" : "Set as default"}
        </Button>
      </header>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Section
          title="Retrieval sources"
          subtitle="Adapters consulted during literature search."
        >
          <ChipList items={profile.retrieval_sources} testid="retrieval-sources" />
        </Section>

        <Section
          title="Keyword extractor"
          subtitle="Strategy used to derive search terms."
        >
          <Mono testid="keyword-extractor">{profile.keyword_extractor}</Mono>
        </Section>

        <Section
          title="Journal presets"
          subtitle="Allowed journal targets for this domain."
        >
          <ChipList items={profile.journal_presets} testid="journal-presets" />
        </Section>

        <Section
          title="Executor"
          subtitle="Code-execution backend for results stages."
        >
          <Mono testid="executor">{profile.executor}</Mono>
        </Section>

        <Section
          title="Novelty corpus"
          subtitle="Reference set used by the novelty scorer."
          className="sm:col-span-2"
        >
          <Mono testid="novelty-corpus">{profile.novelty_corpus || "—"}</Mono>
        </Section>
      </div>
    </article>
  );
}

function Section({
  title,
  subtitle,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) p-3",
        className,
      )}
    >
      <h3 className="text-[12px] font-[510] uppercase tracking-wider text-(--color-text-quaternary)">
        {title}
      </h3>
      {subtitle ? (
        <p className="mt-0.5 text-[11.5px] text-(--color-text-tertiary)">
          {subtitle}
        </p>
      ) : null}
      <div className="mt-2">{children}</div>
    </div>
  );
}

function ChipList({ items, testid }: { items: string[]; testid: string }) {
  if (items.length === 0) {
    return (
      <span className="text-[12px] text-(--color-text-tertiary)" data-testid={testid}>
        None configured.
      </span>
    );
  }
  return (
    <ul
      className="flex flex-wrap gap-1.5"
      data-testid={testid}
    >
      {items.map((item) => (
        <li key={item}>
          <Pill tone="neutral">{item}</Pill>
        </li>
      ))}
    </ul>
  );
}

function Mono({
  children,
  testid,
}: {
  children: React.ReactNode;
  testid: string;
}) {
  return (
    <code
      className="block rounded-[5px] bg-(--color-bg-pill-inactive) px-2 py-1 font-mono text-[12px] text-(--color-text-primary)"
      data-testid={testid}
    >
      {children}
    </code>
  );
}
