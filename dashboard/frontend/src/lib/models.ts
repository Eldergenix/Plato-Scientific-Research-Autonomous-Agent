// Backwards-compatible shim. The catalog now lives in `models-catalog`
// so consumers that don't statically need it (the model picker, the home
// shell, run detail pages) can dynamic-import via `models-async` without
// dragging the catalog into their First Load JS.
//
// Static-catalog consumers (the `/models` page and the
// `/settings/llm-providers` page) should import from `@/lib/models-catalog`
// directly. This barrel is kept for `estimateCost` and any caller that
// needs both types and the catalog.
import type { ModelDef } from "./types";

export type { ModelDef } from "./types";
export {
  MODELS,
  MODELS_BY_ID,
  MODEL_GROUPS,
  modelsForProvider,
} from "./models-catalog";

export function estimateCost(
  model: ModelDef,
  inputTokens: number,
  outputTokens: number,
): number {
  const inputCost = ((model.costInputPer1k ?? 0) * inputTokens) / 1000;
  const outputCost = ((model.costOutputPer1k ?? 0) * outputTokens) / 1000;
  return Math.round((inputCost + outputCost) * 10000); // 0.01 = 1 cent, 4-decimal precision
}
