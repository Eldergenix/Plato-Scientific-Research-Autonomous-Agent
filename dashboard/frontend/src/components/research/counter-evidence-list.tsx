"use client";

import * as React from "react";
import { ExternalLink, ShieldAlert } from "lucide-react";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

export interface SourceLite {
  id: string;
  title: string;
  venue?: string | null;
  year?: number | null;
  doi?: string | null;
  arxiv_id?: string | null;
  url?: string | null;
}

export interface CounterEvidencePayload {
  sources: SourceLite[];
  queries_used: string[];
}

// The trigger phrases the workflow-#11 node appends to the seed query.
// We match each source against the most-likely phrase so the user sees
// *why* it surfaced. The matcher is best-effort — when nothing matches,
// we fall back to the first phrase in queries_used.
const TRIGGER_KEYWORDS = [
  "fail to replicate",
  "null result",
  "limitations",
  "do not support",
  "contradicts",
] as const;

/**
 * Render an external-link URL for a source.
 *
 * Mirrors ``manifest-panel.sourceUrl`` — copied inline to avoid pulling
 * the manifest module into the research bundle. DOIs and arxiv IDs are
 * the only forms that resolve to a public URL; anything else falls
 * through to either the source's own ``url`` or no link.
 */
function sourceUrl(src: SourceLite): string | null {
  if (src.url) return src.url;
  const doi = src.doi?.trim();
  if (doi && /^10\.\d{4,9}\//.test(doi)) return `https://doi.org/${doi}`;
  const arxiv = src.arxiv_id?.trim();
  if (arxiv) {
    if (/^arxiv:/i.test(arxiv)) {
      return `https://arxiv.org/abs/${arxiv.slice(6)}`;
    }
    if (/^\d{4}\.\d{4,5}(v\d+)?$/.test(arxiv)) {
      return `https://arxiv.org/abs/${arxiv}`;
    }
  }
  return null;
}

function matchTrigger(
  source: SourceLite,
  queriesUsed: string[],
): string | null {
  const haystack = `${source.title} ${source.venue ?? ""}`.toLowerCase();
  for (const keyword of TRIGGER_KEYWORDS) {
    if (haystack.includes(keyword)) return keyword;
    for (const query of queriesUsed) {
      if (query.toLowerCase().includes(keyword) && haystack.length > 0) {
        // Heuristic: if the query name mentions the trigger and we have
        // *any* title at all, attribute the source to that variant.
        return keyword;
      }
    }
  }
  if (queriesUsed.length > 0) {
    // Fall back to the first query phrase so every row carries a badge.
    const first = queriesUsed[0];
    return first.length > 32 ? `${first.slice(0, 32)}…` : first;
  }
  return null;
}

export function CounterEvidenceList({
  payload,
}: {
  payload: CounterEvidencePayload;
}) {
  const { sources, queries_used } = payload;

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="counter-evidence-list"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <ShieldAlert size={16} className="text-(--color-text-tertiary)" />
          <h2
            className="text-(--color-text-primary-strong) text-[15px]"
            style={{ fontWeight: 510 }}
          >
            Counter-evidence
          </h2>
        </div>
        <span className="text-[12px] text-(--color-text-row-meta) tabular-nums">
          {sources.length} {sources.length === 1 ? "source" : "sources"}
        </span>
      </header>

      {sources.length === 0 ? (
        <div className="px-4 py-6 text-center" data-testid="counter-evidence-empty">
          <p className="text-[13px] text-(--color-text-row-meta)">
            No counter-evidence search has run yet.
          </p>
        </div>
      ) : (
        <ul className="flex flex-col">
          {sources.map((source) => {
            const trigger = matchTrigger(source, queries_used);
            const link = sourceUrl(source);
            return (
              <li
                key={source.id}
                className="flex flex-col gap-1.5 px-4 py-3 hover:bg-(--color-ghost-bg-hover)"
                style={{ borderTop: "1px solid var(--color-border-standard)" }}
                data-testid="counter-evidence-row"
              >
                <div className="flex items-start justify-between gap-2">
                  {link ? (
                    <a
                      href={link}
                      target="_blank"
                      rel="noreferrer noopener"
                      className={cn(
                        "inline-flex items-start gap-1 text-[13px]",
                        "text-(--color-brand-interactive) hover:underline",
                      )}
                      title={source.title}
                    >
                      <span className="line-clamp-2">{source.title}</span>
                      <ExternalLink
                        size={11}
                        className="mt-0.5 shrink-0"
                        aria-hidden
                      />
                    </a>
                  ) : (
                    <span
                      className="text-[13px] text-(--color-text-row-title) line-clamp-2"
                      title={source.title}
                    >
                      {source.title}
                    </span>
                  )}
                  {trigger ? (
                    <Pill tone="amber" data-testid="counter-evidence-trigger">
                      {trigger}
                    </Pill>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-(--color-text-row-meta) font-mono">
                  {source.venue ? <span>{source.venue}</span> : null}
                  {source.year ? (
                    <span className="tabular-nums">{source.year}</span>
                  ) : null}
                  {source.doi ? <span>doi:{source.doi}</span> : null}
                  {!source.doi && source.arxiv_id ? (
                    <span>arxiv:{source.arxiv_id}</span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
