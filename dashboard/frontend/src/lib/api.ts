import type {
  Journal,
  Project,
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

// Iter-28 — backend already emits these via langgraph_bridge.py for
// every node in AGENT_NODE_NAMES. The frontend used to drop them into
// RunEventUnknown so the AgentSwimlane could never show real activity.
// Now they get explicit discriminants and useProject collects them
// into ``nodeEvents`` for downstream consumers.
export interface RunEventNodeEntered {
  kind: "node.entered";
  ts: number | string;
  /** Node name from AGENT_NODE_NAMES (idea_maker, methods_node, ...). */
  name: string;
  /** Backend stage that owns the run (idea / method / results / ...). */
  stage?: string;
}

export interface RunEventNodeExited {
  kind: "node.exited";
  ts: number | string;
  name: string;
  stage?: string;
  duration_ms?: number;
}

// Iter-30 — code.execute events emitted by ``_child_main`` after the
// results-stage executor returns. One event per cell in
// ``ExecutorResult.artifacts.cells``. Powers the ResultsStage CodePane
// which used to be an honest placeholder pointing elsewhere.
export interface RunEventCodeExecute {
  kind: "code.execute";
  ts: number | string;
  /** Zero-based cell index in the executor run. */
  index?: number;
  /** Python source the executor evaluated. */
  source?: string;
  /** Captured stdout from the cell. */
  stdout?: string | null;
  /** Captured stderr from the cell. */
  stderr?: string | null;
  /** Executor name (cmbagent / local_jupyter / modal / e2b). */
  executor?: string | null;
  /** Error metadata when the cell raised, otherwise undefined. */
  error?: {
    ename?: string;
    evalue?: string;
  } | null;
}

export interface RunEventUnknown {
  kind: string;
  [key: string]: unknown;
}

export type RunEvent =
  | RunEventLogLine
  | RunEventStageFinished
  | RunEventPlotCreated
  | RunEventNodeEntered
  | RunEventNodeExited
  | RunEventCodeExecute
  | RunEventUnknown;

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

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined ?? {}),
  };
  if (_activeRunId && !("X-Plato-Run-Id" in headers)) {
    headers["X-Plato-Run-Id"] = _activeRunId;
  }
  try {
    r = await fetch(`${API_BASE}${path}`, {
      ...init,
      // ``credentials: "include"`` carries the ``plato_user`` cookie
      // set at /auth/login. ``auth.extract_user_id`` reads cookie or
      // header — without ``include`` here, browser-driven calls 401
      // in PLATO_DASHBOARD_AUTH_REQUIRED=1 mode.
      credentials: "include",
      headers,
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
type RawProject = Omit<Project, "totalTokens" | "totalCostCents" | "createdAt" | "updatedAt" | "stages" | "activeRun" | "approvals"> & {
  total_tokens: number;
  total_cost_cents: number;
  created_at: string;
  updated_at: string;
  stages: Record<string, RawStage>;
  active_run: RawActiveRun | null;
  // Iter-27: approvals come along on every Project read so
  // ``getBlockingApproval`` can evaluate the gate synchronously without
  // an extra round trip per stage.
  approvals?: ApprovalsState | null;
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
    approvals: p.approvals ?? null,
  };
}

// ---------------------------------------------------------------- iter-23
// Idea-history response shape — mirror of
// ``plato_dashboard.api.idea_history.IdeaHistoryResponse``.
export interface IdeaHistoryEntry {
  run_id: string;
  workflow: string;
  started_at: string | null;
  ended_at: string | null;
  status: string;
  models: Record<string, string>;
  cost_usd: number;
  tokens_in: number;
  tokens_out: number;
  duration_seconds: number | null;
}

export interface IdeaHistoryResponse {
  entries: IdeaHistoryEntry[];
}

// Iter-26 — mirror of ``plato_dashboard.domain.models.CostCapState``.
export interface CostCapState {
  budget_cents: number | null;
  stop_on_exceed: boolean;
}

// Iter-27 — mirror of ``plato_dashboard.domain.models.ApprovalsState``.
// ``per_stage`` keys are stage ids; values are one of
// ``"pending" | "approved" | "rejected" | "skipped"``.
export type ApprovalState =
  | "pending"
  | "approved"
  | "rejected"
  | "skipped";
export interface ApprovalsState {
  per_stage: Record<string, ApprovalState>;
  auto_skip: boolean;
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

  async createProject(
    name: string,
    dataDescription?: string,
    journal?: Journal | null,
  ): Promise<Project> {
    const raw = await fetchJson<RawProject>("/projects", {
      method: "POST",
      body: JSON.stringify({
        name,
        data_description: dataDescription,
        // Backend treats null/undefined as "no journal preference" (defaults
        // to ``Journal.NONE`` on the model). Sending an explicit empty
        // string would 422 — Pydantic enums reject it.
        ...(journal ? { journal } : {}),
      }),
    });
    return adaptProject(raw);
  },

  /**
   * Iter-3: delete a project. Backend route is
   * ``DELETE /api/v1/projects/{pid}``; ProjectStore.delete already runs
   * the tenant guard. The list-projects page is the only consumer
   * today — once a project is gone, the listing reload removes the row.
   */
  async deleteProject(pid: string): Promise<void> {
    await fetchJson(`/projects/${pid}`, { method: "DELETE" });
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
    body: {
      mode?: "fast" | "cmbagent";
      models?: Record<string, string>;
      // Iter-3: backend StageRunRequest (models.py:169) accepts an
      // optional `iterations` budget. The idea-stage UI exposes a
      // numeric input for this; previously the value was collected and
      // dropped on the floor by this client. Forwarding it lets the
      // user-set iteration budget actually reach the worker.
      iterations?: number | null;
      // Iter-3: same story for `journal` and `add_citations` — backend
      // accepts both, frontend never sent either through the start-run
      // body. Adding them here makes the picker controls in the new
      // run-config drawer wire-able without further client changes.
      journal?: Journal | null;
      add_citations?: boolean;
    } = {},
  ): Promise<{ id: string; project_id: string; stage: StageId; status: string }> {
    return fetchJson(`/projects/${pid}/stages/${stage}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async cancelRun(pid: string, runId: string): Promise<{ cancelled: boolean }> {
    return fetchJson(`/projects/${pid}/runs/${runId}/cancel`, { method: "POST" });
  },

  /**
   * Iter-23: list past idea-generation runs for ``pid`` from disk
   * manifests. Drives the IdeaSidePanel "Run history" view —
   * replaces the iter-22 empty state once any historical run exists.
   * Backend route: ``GET /api/v1/projects/{pid}/idea_history``.
   */
  async listIdeaHistory(pid: string): Promise<IdeaHistoryResponse> {
    return fetchJson(`/projects/${pid}/idea_history`);
  },

  /**
   * Iter-26: read the per-project cost cap.
   *
   * Replaces the localStorage-only ``plato:budget:`` /
   * ``plato:budget-stop:`` keys the cost-meter-panel used to persist
   * client-side. Backend persists in ``meta.json`` and the iter-26
   * ``run_stage`` gate consults it before launching new runs.
   *
   * Returns the no-cap default shape (``budget_cents=null``,
   * ``stop_on_exceed=false``) when no cap is configured for ``pid``.
   */
  async getCostCaps(pid: string): Promise<CostCapState> {
    return fetchJson(`/projects/${pid}/cost_caps`);
  },

  /** Iter-26: persist the per-project cost cap (see ``getCostCaps``). */
  async setCostCaps(pid: string, body: CostCapState): Promise<CostCapState> {
    return fetchJson(`/projects/${pid}/cost_caps`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  /**
   * Iter-27: read the per-project approvals state (per_stage map +
   * auto_skip global bypass). Backend persists in meta.json; the
   * iter-27 ``run_stage`` gate consults it before launching to refuse
   * downstream stages whose upstream gate hasn't been approved.
   *
   * Returns the empty default shape (``per_stage={}``,
   * ``auto_skip=false``) when no approvals are configured for ``pid``.
   */
  async getApprovals(pid: string): Promise<ApprovalsState> {
    return fetchJson(`/projects/${pid}/approvals`);
  },

  /** Iter-27: persist the per-project approvals state. Replaces the
   * entire payload — clients with partial updates should fetch first. */
  async setApprovals(pid: string, body: ApprovalsState): Promise<ApprovalsState> {
    return fetchJson(`/projects/${pid}/approvals`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  /** Subscribe to SSE for a run. Returns an unsubscribe fn. */
  subscribeRunEvents(
    pid: string,
    runId: string,
    onEvent: (evt: RunEvent) => void,
    onError?: (e: unknown) => void,
  ): () => void {
    const url = `${API_BASE}/projects/${pid}/runs/${runId}/events`;
    const es = new EventSource(url);
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
      // Iter-3: Langfuse triplet was missing from this Partial despite the
      // backend KeyStore accepting them and the keys-client UI offering
      // input fields. Strict-mode TypeScript would reject the new
      // ``api.updateKeys({ LANGFUSE_PUBLIC: "" })`` call from keys-client
      // without these.
      LANGFUSE_PUBLIC: string;
      LANGFUSE_SECRET: string;
      LANGFUSE_HOST: string;
    }>,
  ): Promise<KeysStatus> {
    return fetchJson<KeysStatus>("/keys", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  async testKey(
    provider:
      | "OPENAI"
      | "GEMINI"
      | "ANTHROPIC"
      | "PERPLEXITY"
      | "SEMANTIC_SCHOLAR",
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
