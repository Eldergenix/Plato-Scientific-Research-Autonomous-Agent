/**
 * Which model each agent role runs on, and what its tokens cost against the allowance.
 *
 * The project agent (the orchestrator) defaults to Claude Opus 5.5; every sub-agent inside a
 * research thread defaults to Claude Haiku 5.5. Configuration (wrangler vars):
 *   PLATO_ORCHESTRATOR_MODEL  the project agent
 *   PLATO_SCIENTIST_MODEL     every sub-agent role without an override
 *   PLATO_ROLE_MODELS         optional JSON string of per-role overrides, e.g. {"skeptic":"claude-sonnet-5-5"}
 *
 * Budgets and the monthly allowance count allowance tokens: a call's tokens times its model's
 * price weight relative to Claude Haiku 5.5. models.json is generated from
 * plato/scientist/models.py (the Python service applies the same weights to research
 * threads), and a test keeps the two equal.
 */
import catalogue from "./models.json";
import type { Env } from "./lib";

export const ORCHESTRATOR_DEFAULT = catalogue.orchestrator_default;
export const WORKER_DEFAULT = catalogue.worker_default;
export const WORKER_ROLES: readonly string[] = catalogue.roles;
const WEIGHTS: Record<string, number> = catalogue.weights;

/** Price per token relative to Claude Haiku 5.5; unknown models get the highest listed weight. */
export function weight(model: string): number {
  return WEIGHTS[model] ?? catalogue.unknown_weight;
}

/** `tokens` of `model` in allowance (Claude Haiku 5.5) tokens. */
export function allowanceTokens(model: string, tokens: number): number {
  return Math.max(0, tokens) * weight(model);
}

export function orchestratorModel(env: Env): string {
  return env.PLATO_ORCHESTRATOR_MODEL?.trim() || ORCHESTRATOR_DEFAULT;
}

export function workerModel(env: Env): string {
  return env.PLATO_SCIENTIST_MODEL?.trim() || WORKER_DEFAULT;
}

/** Every sub-agent role's model. Throws on a malformed PLATO_ROLE_MODELS (as the container does). */
export function roleModels(env: Env): Record<string, string> {
  const out: Record<string, string> = Object.fromEntries(WORKER_ROLES.map((r) => [r, workerModel(env)]));
  const raw = env.PLATO_ROLE_MODELS?.trim();
  if (!raw) return out;
  const data: unknown = JSON.parse(raw);
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("PLATO_ROLE_MODELS must be a JSON object of role -> model");
  }
  for (const [role, model] of Object.entries(data)) {
    if (!WORKER_ROLES.includes(role)) throw new Error(`PLATO_ROLE_MODELS has an unknown role: ${role}`);
    if (typeof model !== "string" || !model.trim() || model.length > 100) {
      throw new Error(`PLATO_ROLE_MODELS[${role}] must be a model id`);
    }
    out[role] = model.trim();
  }
  return out;
}

/** The models in use, for the API: the orchestrator and the sub-agents' default and overrides. */
export function modelsInfo(env: Env): {
  orchestrator: string;
  workers: string;
  roles: Record<string, string>;
  /** Allowance weight of each model in use (Claude Haiku 5.5 = 1). */
  weights: Record<string, number>;
} {
  const orchestrator = orchestratorModel(env);
  const workers = workerModel(env);
  let roles: Record<string, string> = {};
  try {
    roles = Object.fromEntries(Object.entries(roleModels(env)).filter(([, m]) => m !== workers));
  } catch (err) {
    console.error("invalid PLATO_ROLE_MODELS", err);
  }
  const used = new Set([orchestrator, workers, ...Object.values(roles)]);
  return { orchestrator, workers, roles, weights: Object.fromEntries([...used].map((m) => [m, weight(m)])) };
}
