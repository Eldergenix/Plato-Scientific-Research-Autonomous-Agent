import * as React from "react";
import type { ModelDef, Provider } from "@/lib/types";
import { Pill } from "@/components/ui/pill";
import {
  PROVIDER_COLOR,
  PROVIDER_LABEL,
  bestForFor,
  formatCostPer1k,
  formatTokensShort,
} from "./sort";

function ProviderDot({ provider, size = 8 }: { provider: Provider; size?: number }) {
  return (
    <span
      aria-hidden
      className="inline-block shrink-0 rounded-full"
      style={{ width: size, height: size, backgroundColor: PROVIDER_COLOR[provider] }}
    />
  );
}

function KeyStatusDot({ ok, loading }: { ok: boolean; loading: boolean }) {
  const color = loading ? "#515153" : ok ? "#27A644" : "#515153";
  return (
    <span
      aria-hidden
      title={loading ? "loading" : ok ? "key available" : "no key"}
      className="inline-block shrink-0 rounded-full"
      style={{ width: 8, height: 8, backgroundColor: color }}
    />
  );
}

function ModelTableRowImpl({
  model,
  hasKey,
  keysLoading,
}: {
  model: ModelDef;
  hasKey: boolean;
  keysLoading: boolean;
}) {
  const best = bestForFor(model);
  const cost = "font-mono text-[12px] tabular-nums text-(--color-text-primary)";
  return (
    <tr
      className="transition-colors hover:bg-[rgba(255,255,255,0.02)]"
      style={{ height: 44 }}
    >
      <td className="px-4">
        <div className="flex flex-col">
          <span className="text-[13px] text-(--color-text-primary-strong)">{model.label}</span>
          <span className="font-mono text-[10.5px] text-[#949496]">{model.id}</span>
        </div>
      </td>
      <td className="px-4">
        <span className="inline-flex items-center gap-2 text-[12.5px] text-(--color-text-secondary-spec)">
          <ProviderDot provider={model.provider} />
          {PROVIDER_LABEL[model.provider]}
        </span>
      </td>
      <td className="px-4 text-right">
        <span className={cost}>{formatTokensShort(model.maxOutputTokens)}</span>
      </td>
      <td className="px-4 text-right">
        <span className={cost}>{formatCostPer1k(model.costInputPer1k)}</span>
      </td>
      <td className="px-4 text-right">
        <span className={cost}>{formatCostPer1k(model.costOutputPer1k)}</span>
      </td>
      <td className="px-4">
        <Pill tone={best.tone}>{best.label}</Pill>
      </td>
      <td className="px-4 text-center">
        <KeyStatusDot ok={hasKey} loading={keysLoading} />
      </td>
    </tr>
  );
}

export const ModelTableRow = React.memo(ModelTableRowImpl);
