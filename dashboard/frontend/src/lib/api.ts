import type {
  Project,
  Run,
  RunStatus,
  StageId,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

// Discriminated union for SSE payloads emitted by the FastAPI event
// bus (see plato_dashboard.events.bus). Consumers should switch on
// ``kind`` rather than reading bare ``Record<string, unknown>``
// fields. Unknown event kinds fall through to ``RunEventUnknown``
// so a backend addition won't crash the frontend on first contact.
export interface RunEventLogLine {
  kind: "log.line";
  ts: number | string;
  source?: string;
  agent?: string;
  level?: "info" | "warn" | "error" | "tool";
  text?: string;
}

export interface RunEventStageFinished {
  kind: "stage.finished";
  ts: number | string;
  stage: StageId;
  ok?: boolean;
}

export interface RunEventPlotCreated {
  kind: "plot.created";
  ts: number | string;
  path?: string;
}

export interface RunEventUnknown {
  kind: string;
  [key: string]: unknown;
}

export type RunEvent =
  | RunEventLogLine
  | RunEventStageFinished
  | RunEventPlotCreated
  | RunEventUnknown;

// One file under a run dir, advertised by the artifacts listing.
// Mirrors ``Artifact`` in dashboard/backend/.../api/server.py — keep
// the union of ``kind`` values in lockstep with the backend Literal so
// we never drop a new bucket on the floor.
export type RunArtifactKind =
  | "paper_pdf"
  | "manifest"
  | "report"
  | "data"
  | "log"
  | "other";

export interface RunArtifact {
  path: string;
  size: number;
  mtime: string; // ISO-8601 UTC
  kind: RunArtifactKind;
}

// Module-level run-id store. Components that know they're inside an
// active run (workspace shell, run-detail subroutes, loop monitor)
// set this so every subsequent fetchJson call carries the matching
// X-Plato-Run-Id header. The dashboard backend's middleware reads
// the same header into a contextvar that flows to the log
// formatter — closing the iter-12 correlation loop.
let _activeRunId: string | null = null;

export function setActiveRunId(id: string | null): void {
  _activeRunId = id;
}

export function getActiveRunId(): string | null {
  return _activeRunId;
}

// Module-level user-id store for ADR 0004 multi-tenancy. The auth
// context calls setActiveUserId on login/logout/refresh and on cold
// load we rehydrate from localStorage so the very first fetchJson
// after a page refresh already carries X-Plato-User. The cookie set
// by /auth/login remains the server's source of truth — this header
// drives backend log correlation and tenant routing.
const USER_ID_STORAGE_KEY = "plato:user_id";
let _activeUserId: string | null = null;

if (typeof window !== "undefined") {
  try {
    const persisted = window.localStorage.getItem(USER_ID_STORAGE_KEY);
    if (persisted && persisted.length > 0) _activeUserId = persisted;
  } catch {
    /* private mode / quota — login flow will repopulate */
  }
}

export function setActiveUserId(id: string | null): void {
  _activeUserId = id;
}

export function getActiveUserId(): string | null {
  return _activeUserId;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined ?? {}),
  };
  if (_activeRunId && !("X-Plato-Run-Id" in headers)) {
    headers["X-Plato-Run-Id"] = _activeRunId;
  }
  if (_activeUserId && !("X-Plato-User" in headers)) {
    headers["X-Plato-User"] = _activeUserId;
  }
  try {
    r = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: init?.credentials ?? "include",
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

type RawRun = {
  id: string;
  project_id: string;
  stage: StageId;
  mode: Run["mode"];
  status: RunStatus;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  token_input: number;
  token_output: number;
};

function adaptRun(r: RawRun): Run {
  return {
    id: r.id,
    projectId: r.project_id,
    stage: r.stage,
    mode: r.mode,
    status: r.status,
    startedAt: r.started_at ?? undefined,
    finishedAt: r.finished_at ?? undefined,
    error: r.error ?? undefined,
    tokenInput: r.token_input ?? 0,
    tokenOutput: r.token_output ?? 0,
  };
}

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

  // Retry semantically maps to "start a new run for this stage" — the
  // backend has no dedicated endpoint, but POST /stages/{stage}/run is
  // idempotent w.r.t. capability checks and produces a fresh run id we
  // navigate to. Kept separate from startRun() so call-sites read clearly.
  async retryRun(
    pid: string,
    stage: StageId,
    body: { mode?: "fast" | "cmbagent"; models?: Record<string, string> } = {},
  ): Promise<{ id: string; project_id: string; stage: StageId; status: string }> {
    return fetchJson(`/projects/${pid}/stages/${stage}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async getRun(pid: string, runId: string): Promise<Run> {
    const raw = await fetchJson<RawRun>(`/projects/${pid}/runs/${runId}`);
    return adaptRun(raw);
  },

  async listRuns(pid: string): Promise<Run[]> {
    const raw = await fetchJson<RawRun[]>(`/projects/${pid}/runs`);
    return raw.map(adaptRun);
  },

  async listRunArtifacts(pid: string, runId: string): Promise<RunArtifact[]> {
    const raw = await fetchJson<{ items: RunArtifact[] }>(
      `/projects/${pid}/runs/${runId}/artifacts`,
    );
    return raw.items;
  },

  /**
   * Subscribe to SSE for a run with automatic reconnect.
   *
   * Native EventSource only retries within a single browser-managed
   * window — once the server hard-closes (process restart, network
   * blip past that budget), the stream stays dead. We wrap creation
   * in a small supervisor that retries up to 5 times with exponential
   * backoff (1s -> 2s -> 4s -> 8s -> 16s, capped), resets the attempt
   * counter on a successful onopen, and stops scheduling once the
   * caller invokes the returned close().
   *
   * Signature stays a `() => void` unsubscribe so existing callers
   * (loop monitor, run-detail page) need no change.
   */
  subscribeRunEvents(
    pid: string,
    runId: string,
    onEvent: (evt: RunEvent) => void,
    onError?: (e: unknown) => void,
  ): () => void {
    const url = `${API_BASE}/projects/${pid}/runs/${runId}/events`;
    const MAX_ATTEMPTS = 5;
    let attempts = 0;
    let stopped = false;
    let current: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = (): void => {
      if (stopped) return;
      const es = new EventSource(url);
      current = es;
      es.onopen = () => {
        attempts = 0;
      };
      es.onmessage = (e) => {
        try {
          // The backend bus emits Record<string, unknown> shapes; we
          // narrow at the boundary so consumers can discriminate on
          // ``kind`` instead of doing String(evt.kind) inline.
          const raw = JSON.parse(e.data) as Record<string, unknown>;
          onEvent(raw as RunEvent);
        } catch (err) {
          onError?.(err);
        }
      };
      es.onerror = (e) => {
        onError?.(e);
        if (stopped) return;
        es.close();
        current = null;
        if (attempts >= MAX_ATTEMPTS) return;
        const delay = Math.min(1000 * 2 ** attempts, 16000);
        attempts += 1;
        retryTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      stopped = true;
      if (retryTimer !== null) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }
      if (current) {
        current.close();
        current = null;
      }
    };
  },

  // ------------------------------------------------------------ telemetry
  async getTelemetryPreferences(): Promise<TelemetryPreferences> {
    return fetchJson<TelemetryPreferences>("/telemetry/preferences");
  },

  async setTelemetryPreferences(enabled: boolean): Promise<TelemetryPreferences> {
    return fetchJson<TelemetryPreferences>("/telemetry/preferences", {
      method: "PUT",
      body: JSON.stringify({ telemetry_enabled: enabled }),
    });
  },

  // ------------------------------------------------------------ run presets
  async listRunPresets(): Promise<RunPreset[]> {
    return fetchJson<RunPreset[]>("/run-presets");
  },

  async getRunPreset(id: string): Promise<RunPreset> {
    return fetchJson<RunPreset>(`/run-presets/${id}`);
  },

  async createRunPreset(
    name: string,
    config: RunPresetConfig,
  ): Promise<RunPreset> {
    return fetchJson<RunPreset>("/run-presets", {
      method: "POST",
      body: JSON.stringify({ name, config }),
    });
  },

  async updateRunPreset(
    id: string,
    payload: { name?: string; config?: RunPresetConfig },
  ): Promise<RunPreset> {
    return fetchJson<RunPreset>(`/run-presets/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  async deleteRunPreset(id: string): Promise<void> {
    await fetchJson<void>(`/run-presets/${id}`, { method: "DELETE" });
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

// Download a binary artefact via the per-project files endpoint.
//
// The fetchJson helper above always parses the response as JSON, which
// corrupts PDFs and any other binary. We need a separate path that
// reads the body as a Blob and triggers a save dialog. Auth headers
// are forwarded so the backend's tenant guard still passes.
export async function downloadArtifact(
  projectId: string,
  relpath: string,
  suggestedFilename?: string,
): Promise<void> {
  const headers: Record<string, string> = {};
  if (_activeRunId) headers["X-Plato-Run-Id"] = _activeRunId;
  if (_activeUserId) headers["X-Plato-User"] = _activeUserId;

  const url = `${API_BASE}/projects/${projectId}/files/${relpath}`;
  const r = await fetch(url, { headers, credentials: "include" });
  if (!r.ok) {
    let detail: unknown;
    try {
      detail = await r.json();
    } catch {
      detail = await r.text();
    }
    throw new ApiError(r.status, detail);
  }
  const blob = await r.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = suggestedFilename ?? relpath.split("/").pop() ?? "artifact";
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    // Defer revoke so Safari has time to start the download stream.
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }
}

// ---------------------------------------------------------------- telemetry types
export interface TelemetryEntry {
  timestamp?: string;
  run_id?: string;
  workflow?: string;
  duration_seconds?: number | null;
  tokens_in?: number;
  tokens_out?: number;
  cost_usd?: number;
  status?: string;
}

export interface TelemetryAggregates {
  total_runs: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: number;
}

export interface TelemetryPreferences {
  telemetry_enabled: boolean;
  last_n_summary: TelemetryEntry[];
  aggregates: TelemetryAggregates;
}

// ---------------------------------------------------------------- run preset types
//
// The on-disk ``config`` payload is a free-form bag matching the
// backend ``RunPresetCreate.config`` field. Callers merge it over their
// run-start defaults at submit time. We type the well-known stage
// knobs and leave the rest as ``unknown`` so adding a new field on the
// server doesn't require a frontend rev.
export interface RunPresetConfig {
  idea_iters?: number;
  max_revision_iters?: number;
  journal?: string;
  domain?: string;
  executor?: string;
  [key: string]: unknown;
}

export interface RunPreset {
  id: string;
  name: string;
  created_at: string;
  config: RunPresetConfig;
}

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
