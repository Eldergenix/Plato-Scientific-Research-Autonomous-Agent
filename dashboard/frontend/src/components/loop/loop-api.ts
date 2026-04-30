"use client";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

export type LoopStatusValue = "running" | "stopped" | "interrupted" | "error";

export interface LoopStatus {
  loop_id: string;
  status: LoopStatusValue;
  iterations: number;
  kept: number;
  discarded: number;
  best_composite: number;
  started_at: string;
  tsv_path: string;
  error: string | null;
}

export interface LoopTsvRow {
  iter: number;
  timestamp: string;
  composite: number;
  status: string;
  description: string;
}

export interface LoopStartBody {
  project_dir: string;
  max_iters: number | null;
  time_budget_hours: number;
  max_cost_usd: number;
  branch_prefix: string;
}

class LoopApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(`Loop API error ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    throw new LoopApiError(0, {
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
    throw new LoopApiError(r.status, detail);
  }
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export const loopApi = {
  async list(): Promise<LoopStatus[]> {
    return request<LoopStatus[]>("/loop");
  },
  async start(body: LoopStartBody): Promise<LoopStatus> {
    return request<LoopStatus>("/loop/start", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  async status(loopId: string): Promise<LoopStatus> {
    return request<LoopStatus>(`/loop/${loopId}/status`);
  },
  async stop(loopId: string): Promise<LoopStatus> {
    return request<LoopStatus>(`/loop/${loopId}/stop`, { method: "POST" });
  },
  async tsv(loopId: string): Promise<{ rows: LoopTsvRow[] }> {
    return request<{ rows: LoopTsvRow[] }>(`/loop/${loopId}/tsv`);
  },
};

export { LoopApiError };
