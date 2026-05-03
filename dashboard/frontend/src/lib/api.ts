import type {
  Project,
  StageId,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    throw new ApiError(0, {
      code: "network_error",
      message: e instanceof Error ? e.message : "Backend offline",
    });
  }
  if (!r.ok) {
    let detail: unknown;
    try {
      detail = await r.json();
    } catch {
      detail = await r.text();
    }
    throw new ApiError(r.status, detail);
  }
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`API error ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

// ---------------------------------------------------------------- shape
// The backend uses snake_case; the frontend uses camelCase. Translate.
type RawProject = Omit<Project, "totalTokens" | "totalCostCents" | "createdAt" | "updatedAt" | "stages" | "activeRun"> & {
  total_tokens: number;
  total_cost_cents: number;
  created_at: string;
  updated_at: string;
  stages: Record<string, RawStage>;
  active_run: RawActiveRun | null;
};
type RawStage = {
  id: StageId;
  label: string;
  status: Project["stages"][StageId]["status"];
  model?: string | null;
  duration_ms?: number | null;
  last_run_at?: string | null;
  origin?: "ai" | "edited" | null;
  progress_label?: string | null;
};
type RawActiveRun = {
  run_id: string;
  stage: StageId;
  started_at: string;
  step?: number | null;
  total_steps?: number | null;
  attempt?: number | null;
  total_attempts?: number | null;
};

function adaptProject(p: RawProject): Project {
  const stages = Object.fromEntries(
    Object.entries(p.stages).map(([k, s]) => [
      k,
      {
        id: s.id,
        label: s.label,
        status: s.status,
        model: s.model ?? undefined,
        durationMs: s.duration_ms ?? undefined,
        lastRunAt: s.last_run_at ?? undefined,
        origin: s.origin ?? undefined,
        progressLabel: s.progress_label ?? undefined,
      },
    ]),
  ) as Project["stages"];
  return {
    id: p.id,
    name: p.name,
    journal: p.journal,
    createdAt: p.created_at,
    updatedAt: p.updated_at,
    totalTokens: p.total_tokens,
    totalCostCents: p.total_cost_cents,
    stages,
    activeRun: p.active_run
      ? {
          runId: p.active_run.run_id,
          stage: p.active_run.stage,
          startedAt: p.active_run.started_at,
          step: p.active_run.step ?? undefined,
          totalSteps: p.active_run.total_steps ?? undefined,
          attempt: p.active_run.attempt ?? undefined,
          totalAttempts: p.active_run.total_attempts ?? undefined,
        }
      : null,
  };
}

// ---------------------------------------------------------------- API
export const api = {
  async health(): Promise<{ ok: boolean; demo_mode: boolean }> {
    return fetchJson("/health");
  },

  async capabilities(): Promise<{
    is_demo: boolean;
    allowed_stages: StageId[];
    max_concurrent_runs: number;
    session_budget_cents?: number;
    notes: string[];
  }> {
    return fetchJson("/capabilities");
  },

  async listProjects(): Promise<Project[]> {
    const raw = await fetchJson<RawProject[]>("/projects");
    return raw.map(adaptProject);
  },

  async getProject(id: string): Promise<Project> {
    const raw = await fetchJson<RawProject>(`/projects/${id}`);
    return adaptProject(raw);
  },

  async createProject(name: string, dataDescription?: string): Promise<Project> {
    const raw = await fetchJson<RawProject>("/projects", {
      method: "POST",
      body: JSON.stringify({ name, data_description: dataDescription }),
    });
    return adaptProject(raw);
  },

  async readStage(pid: string, stage: StageId): Promise<{ markdown: string; origin: string } | null> {
    const r = await fetchJson<{ markdown: string; origin: string } | null>(
      `/projects/${pid}/state/${stage}`,
    );
    return r;
  },

  async writeStage(pid: string, stage: StageId, markdown: string): Promise<void> {
    await fetchJson(`/projects/${pid}/state/${stage}`, {
      method: "PUT",
      body: JSON.stringify({ markdown }),
    });
  },

  async startRun(
    pid: string,
    stage: StageId,
    body: { mode?: "fast" | "cmbagent"; models?: Record<string, string> } = {},
  ): Promise<{ id: string; project_id: string; stage: StageId; status: string }> {
    return fetchJson(`/projects/${pid}/stages/${stage}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async cancelRun(pid: string, runId: string): Promise<{ cancelled: boolean }> {
    return fetchJson(`/projects/${pid}/runs/${runId}/cancel`, { method: "POST" });
  },

  /** Subscribe to SSE for a run. Returns an unsubscribe fn. */
  subscribeRunEvents(
    pid: string,
    runId: string,
    onEvent: (evt: Record<string, unknown>) => void,
    onError?: (e: unknown) => void,
  ): () => void {
    const url = `${API_BASE}/projects/${pid}/runs/${runId}/events`;
    const es = new EventSource(url);
    es.onmessage = (e) => {
      try {
        onEvent(JSON.parse(e.data));
      } catch (err) {
        onError?.(err);
      }
    };
    es.onerror = (e) => onError?.(e);
    return () => es.close();
  },

  // ------------------------------------------------------------ keys
  async getKeysStatus(): Promise<KeysStatus> {
    return fetchJson<KeysStatus>("/keys/status");
  },

  async updateKeys(
    payload: Partial<{
      OPENAI: string;
      GEMINI: string;
      ANTHROPIC: string;
      PERPLEXITY: string;
      SEMANTIC_SCHOLAR: string;
    }>,
  ): Promise<KeysStatus> {
    return fetchJson<KeysStatus>("/keys", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  async testKey(
    provider: "OPENAI" | "GEMINI" | "ANTHROPIC",
  ): Promise<{ ok: boolean; latency_ms?: number; error?: string }> {
    try {
      return await fetchJson<{ ok: boolean; latency_ms?: number; error?: string }>(
        `/keys/test/${provider}`,
        { method: "POST" },
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        return { ok: false, error: "not implemented" };
      }
      const msg = err instanceof Error ? err.message : "test failed";
      return { ok: false, error: msg };
    }
  },
};

// ---------------------------------------------------------------- keys types
export type KeyState = "unset" | "from_env" | "in_app";
export interface KeysStatus {
  OPENAI: KeyState;
  GEMINI: KeyState;
  ANTHROPIC: KeyState;
  PERPLEXITY: KeyState;
  SEMANTIC_SCHOLAR: KeyState;
  // R8 — observability keys are stored alongside LLM provider keys.
  // Backend ENV_KEYS includes all three so the dashboard `/keys` UI
  // can configure Langfuse without shell env vars; the frontend
  // shape must mirror it or `Object.keys(keysStatus)` iteration in
  // the UI silently drops these three states.
  LANGFUSE_PUBLIC: KeyState;
  LANGFUSE_SECRET: KeyState;
  LANGFUSE_HOST: KeyState;
}
