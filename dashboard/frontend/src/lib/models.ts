import type { ModelDef } from "./types";

// Mirrors plato/llm.py:83-98 with cost metadata layered on top.
// Costs are USD per 1K tokens at list price as of 2026-01; update as providers change.
export const MODELS: ModelDef[] = [
  {
    id: "gemini-2.0-flash",
    label: "Gemini 2.0 Flash",
    provider: "gemini",
    maxOutputTokens: 8192,
    temperature: 0.7,
    costInputPer1k: 0.00010,
    costOutputPer1k: 0.00040,
    notes: "Cheap · fast",
  },
  {
    id: "gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
    provider: "gemini",
    maxOutputTokens: 65536,
    temperature: 0.7,
    costInputPer1k: 0.00030,
    costOutputPer1k: 0.0025,
    notes: "Cheap · long output",
  },
  {
    id: "gemini-2.5-pro",
    label: "Gemini 2.5 Pro",
    provider: "gemini",
    maxOutputTokens: 65536,
    temperature: 0.7,
    costInputPer1k: 0.00125,
    costOutputPer1k: 0.010,
    notes: "Strong reasoning",
  },
  {
    id: "o3-mini",
    label: "o3-mini",
    provider: "openai",
    maxOutputTokens: 100000,
    temperature: null,
    costInputPer1k: 0.00110,
    costOutputPer1k: 0.0044,
    notes: "Strong reasoning",
  },
  {
    id: "gpt-4o",
    label: "GPT-4o",
    provider: "openai",
    maxOutputTokens: 16384,
    temperature: 0.5,
    costInputPer1k: 0.0025,
    costOutputPer1k: 0.010,
  },
  {
    id: "gpt-4.1",
    label: "GPT-4.1",
    provider: "openai",
    maxOutputTokens: 16384,
    temperature: 0.5,
    costInputPer1k: 0.0020,
    costOutputPer1k: 0.0080,
    notes: "Recommended",
  },
  {
    id: "gpt-4.1-mini",
    label: "GPT-4.1 mini",
    provider: "openai",
    maxOutputTokens: 16384,
    temperature: 0.5,
    costInputPer1k: 0.00040,
    costOutputPer1k: 0.0016,
    notes: "Cheap",
  },
  {
    id: "gpt-4o-mini",
    label: "GPT-4o mini",
    provider: "openai",
    maxOutputTokens: 16384,
    temperature: 0.5,
    costInputPer1k: 0.00015,
    costOutputPer1k: 0.00060,
    notes: "Cheap",
  },
  {
    id: "gpt-4.5",
    label: "GPT-4.5 preview",
    provider: "openai",
    maxOutputTokens: 16384,
    temperature: 0.5,
    costInputPer1k: 0.075,
    costOutputPer1k: 0.150,
    notes: "Premium",
  },
  {
    id: "gpt-5",
    label: "GPT-5",
    provider: "openai",
    maxOutputTokens: 128000,
    temperature: null,
    costInputPer1k: 0.0125,
    costOutputPer1k: 0.050,
    notes: "Premium · long output",
  },
  {
    id: "gpt-5-mini",
    label: "GPT-5 mini",
    provider: "openai",
    maxOutputTokens: 128000,
    temperature: null,
    costInputPer1k: 0.00025,
    costOutputPer1k: 0.0020,
    notes: "Cheap · long output",
  },
  {
    id: "claude-3.7-sonnet",
    label: "Claude 3.7 Sonnet",
    provider: "anthropic",
    maxOutputTokens: 64000,
    temperature: 0,
    costInputPer1k: 0.003,
    costOutputPer1k: 0.015,
  },
  {
    id: "claude-4-opus",
    label: "Claude 4 Opus",
    provider: "anthropic",
    maxOutputTokens: 32000,
    temperature: 0,
    costInputPer1k: 0.015,
    costOutputPer1k: 0.075,
    notes: "Premium reasoning",
  },
  {
    id: "claude-4.1-opus",
    label: "Claude 4.1 Opus",
    provider: "anthropic",
    maxOutputTokens: 32000,
    temperature: 0,
    costInputPer1k: 0.015,
    costOutputPer1k: 0.075,
    notes: "Recommended for retries",
  },
];

export const MODELS_BY_ID = Object.fromEntries(MODELS.map((m) => [m.id, m]));

export const MODEL_GROUPS = [
  { provider: "anthropic" as const, label: "Anthropic" },
  { provider: "openai" as const, label: "OpenAI" },
  { provider: "gemini" as const, label: "Google" },
];

export function modelsForProvider(provider: ModelDef["provider"]): ModelDef[] {
  return MODELS.filter((m) => m.provider === provider);
}

// Iter-7: single source of truth for per-stage recommended-model defaults.
// model-picker.tsx and models-client.tsx used to declare independent copies
// that drifted on ``paper`` and ``referee`` (different defaults in each
// place), so the localStorage override layer saved one model while the
// run-config dropdown showed a different "Recommended" badge. Both
// consumers now import this table.
export const RECOMMENDED_MODEL_BY_STAGE = {
  idea: "gpt-4.1",
  literature: "gpt-4.1-mini",
  method: "claude-4.1-opus",
  results: "gpt-5",
  paper: "claude-4.1-opus",
  referee: "o3-mini",
} as const satisfies Record<string, string>;

export type RecommendedStageId = keyof typeof RECOMMENDED_MODEL_BY_STAGE;


export function estimateCost(model: ModelDef, inputTokens: number, outputTokens: number): number {
  const inputCost = ((model.costInputPer1k ?? 0) * inputTokens) / 1000;
  const outputCost = ((model.costOutputPer1k ?? 0) * outputTokens) / 1000;
  return Math.round((inputCost + outputCost) * 10000); // return in cents (0.01 = 1 cent), with 4-decimal precision
}
