import * as React from "react";
import type { KeysStatus } from "@/lib/api";
import { MODELS, MODEL_GROUPS } from "@/lib/models";
import type { Provider } from "@/lib/types";

const PROVIDER_KEY_FIELD: Record<Provider, keyof KeysStatus | undefined> = {
  anthropic: "ANTHROPIC",
  openai: "OPENAI",
  gemini: "GEMINI",
  perplexity: "PERPLEXITY",
  semantic_scholar: "SEMANTIC_SCHOLAR",
};

export function providerHasKey(p: Provider, status: KeysStatus | null): boolean {
  if (!status) return false;
  const field = PROVIDER_KEY_FIELD[p];
  if (!field) return false;
  return status[field] !== "unset";
}

export function ProviderStatusHeader({
  keysStatus,
  keysLoading,
}: {
  keysStatus: KeysStatus | null;
  keysLoading: boolean;
}) {
  return (
    <header className="surface-linear-card flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
      <div className="min-w-0">
        <h1
          className="text-(--color-text-primary-strong)"
          style={{ fontFamily: "Inter", fontWeight: 510, fontSize: 24, letterSpacing: "-0.5px" }}
        >
          Models
        </h1>
        <p className="mt-0.5 text-[13px] text-(--color-text-tertiary-spec)">
          {MODELS.length} models across {MODEL_GROUPS.length} providers. Pricing in USD per 1K tokens.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {MODEL_GROUPS.map((g) => {
          const has = providerHasKey(g.provider, keysStatus);
          const dataColor =
            g.provider === "anthropic" ? "teal" : g.provider === "openai" ? "green" : "blue";
          return (
            <span
              key={g.provider}
              className="tag-pill border-(--color-border-pill)"
              data-color={dataColor}
              title={
                keysLoading
                  ? "Loading key status…"
                  : has
                    ? `${g.label} key available`
                    : `${g.label} key missing`
              }
            >
              <span>
                {g.label}{" "}
                <span className="text-(--color-text-row-meta)">
                  {keysLoading ? "…" : has ? "✓" : "✗"}
                </span>
              </span>
            </span>
          );
        })}
      </div>
    </header>
  );
}
