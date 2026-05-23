import type {
  Journal,
  Mode,
  PublicationFeedAuthor,
  PublicationSettings,
  Project,
  ResearchPublication,
  StageId,
} from "./types";
import { dashboardApiBase } from "./api-base";

const API_BASE = dashboardApiBase();

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
  status?: RunStatus;
}

export interface RunEventStageHeartbeat {
  kind: "stage.heartbeat";
  ts?: number | string;
  stage?: StageId;
  step?: number;
  total_steps?: number;
  attempt?: number;
  total_attempts?: number;
}

export interface RunEventPlotCreated {
  kind: "plot.created";
  ts: number | string;
  path?: string;
}

export interface RunEventError {
  kind: "error";
  ts: number | string;
  stage?: StageId;
  message?: string;
  traceback?: string;
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
  | RunEventStageHeartbeat
  | RunEventPlotCreated
  | RunEventError
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
    const detail = await readErrorDetail(r);
    throw new ApiError(r.status, detail);
  }
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(errorMessageForDetail(status, detail));
    this.status = status;
    this.detail = detail;
  }
}

async function readErrorDetail(response: Response): Promise<unknown> {
  const body = await response.text();
  if (!body) return null;
  try {
    return JSON.parse(body);
  } catch {
    return body;
  }
}

function errorMessageForDetail(status: number, detail: unknown): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown; detail?: unknown }).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
    const nestedDetail = (detail as { detail?: unknown }).detail;
    if (typeof nestedDetail === "string" && nestedDetail.trim()) {
      return nestedDetail;
    }
  }
  return `API error ${status}`;
}

// ---------------------------------------------------------------- shape
// The backend uses snake_case; the frontend uses camelCase. Translate.
type RawProject = Omit<Project, "totalTokens" | "totalCostCents" | "createdAt" | "updatedAt" | "stages" | "activeRun" | "approvals" | "publicationSettings"> & {
  total_tokens: number;
  total_cost_cents: number;
  created_at: string;
  updated_at: string;
  stages: Record<string, RawStage>;
  active_run: RawActiveRun | null;
  publication_settings?: PublicationSettings | null;
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

function defaultPublicationSettings(): PublicationSettings {
  return { authors: [], dates: {}, tasks: [] };
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
    publicationSettings: p.publication_settings ?? defaultPublicationSettings(),
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

type RawPublicationFeedAuthor = {
  id?: string | null;
  user_id?: string | null;
  name: string;
  affiliation?: string | null;
  avatar_url?: string | null;
  role?: string | null;
};

type RawPublicationComment = {
  id: string;
  publication_id: string;
  user_id: string;
  user_name: string;
  user_affiliation?: string | null;
  user_avatar_url?: string | null;
  body: string;
  tagged_authors?: RawPublicationFeedAuthor[];
  created_at: string;
};

type RawResearchPublication = {
  id: string;
  project_id: string;
  creator_user_id: string;
  creator_name: string;
  creator_affiliation?: string | null;
  creator_avatar_url?: string | null;
  title: string;
  description: string;
  paper_pdf_url: string;
  first_page_preview_url: string;
  source_run_id?: string | null;
  source_stage: string;
  authors?: RawPublicationFeedAuthor[];
  tagged_authors?: RawPublicationFeedAuthor[];
  tags?: string[];
  published_at: string;
  updated_at: string;
  like_count: number;
  comment_count: number;
  share_count: number;
  comments?: RawPublicationComment[];
};

function adaptFeedAuthor(author: RawPublicationFeedAuthor): PublicationFeedAuthor {
  return {
    id: author.id ?? null,
    userId: author.user_id ?? null,
    name: author.name,
    affiliation: author.affiliation ?? null,
    avatarUrl: author.avatar_url ?? null,
    role: author.role ?? null,
  };
}

function adaptPublicationComment(comment: RawPublicationComment) {
  return {
    id: comment.id,
    publicationId: comment.publication_id,
    userId: comment.user_id,
    userName: comment.user_name,
    userAffiliation: comment.user_affiliation ?? null,
    userAvatarUrl: comment.user_avatar_url ?? null,
    body: comment.body,
    taggedAuthors: (comment.tagged_authors ?? []).map(adaptFeedAuthor),
    createdAt: comment.created_at,
  };
}

function adaptResearchPublication(publication: RawResearchPublication): ResearchPublication {
  return {
    id: publication.id,
    projectId: publication.project_id,
    creatorUserId: publication.creator_user_id,
    creatorName: publication.creator_name,
    creatorAffiliation: publication.creator_affiliation ?? null,
    creatorAvatarUrl: publication.creator_avatar_url ?? null,
    title: publication.title,
    description: publication.description,
    paperPdfUrl: publication.paper_pdf_url,
    firstPagePreviewUrl: publication.first_page_preview_url,
    sourceRunId: publication.source_run_id ?? null,
    sourceStage: publication.source_stage,
    authors: (publication.authors ?? []).map(adaptFeedAuthor),
    taggedAuthors: (publication.tagged_authors ?? []).map(adaptFeedAuthor),
    tags: publication.tags ?? [],
    publishedAt: publication.published_at,
    updatedAt: publication.updated_at,
    likeCount: publication.like_count,
    commentCount: publication.comment_count,
    shareCount: publication.share_count,
    comments: (publication.comments ?? []).map(adaptPublicationComment),
  };
}

function toRawFeedAuthor(author: PublicationFeedAuthor): RawPublicationFeedAuthor {
  return {
    id: author.id ?? undefined,
    user_id: author.userId ?? undefined,
    name: author.name,
    affiliation: author.affiliation ?? undefined,
    avatar_url: author.avatarUrl ?? undefined,
    role: author.role ?? undefined,
  };
}

export interface PublishPublicationBody {
  title?: string;
  description?: string;
  creator_name?: string;
  creator_affiliation?: string;
  creator_avatar_url?: string;
  source_run_id?: string;
  tagged_authors?: PublicationFeedAuthor[];
  tags?: string[];
}

export interface PublicationCommentBody {
  body: string;
  user_name?: string;
  user_affiliation?: string;
  user_avatar_url?: string;
  tagged_authors?: PublicationFeedAuthor[];
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

// ---------------------------------------------------------------- usage
// Mirror of ``plato_dashboard.worker.token_tracker.StageTokens`` /
// ``ProjectUsage``. The backend serialises both as plain dicts
// (StageTokens via ``__dict__``, ProjectUsage assembled inline at
// ``api/server.py``). Field names are snake_case to match the wire.
export interface StageTokens {
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_cents: number;
}

export interface ProjectUsage {
  total_input: number;
  total_output: number;
  total_cost_cents: number;
  by_stage: Record<string, StageTokens>;
  by_model: Record<string, StageTokens>;
  /**
   * Per-run records. Currently unpopulated by
   * ``aggregate_project_usage`` (always ``[]``); kept as a typed slot
   * for forward compatibility once the backend records run-level
   * timestamps. Items are intentionally loose — we only consume known
   * keys when present.
   */
  by_run: Array<Record<string, unknown>>;
}

export interface RunUsage {
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_cents: number;
}

export type RunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface RunRecord {
  id: string;
  projectId: string;
  stage: StageId;
  mode: "fast" | "cmbagent";
  status: RunStatus;
  startedAt?: string | null;
  finishedAt?: string | null;
  error?: string | null;
  config: Record<string, unknown>;
  pid?: number | null;
  tokenInput: number;
  tokenOutput: number;
}

export interface StageRunBody {
  mode?: Mode;
  models?: Record<string, string>;
  journal?: Journal | null;
  add_citations?: boolean;
  iterations?: number | null;
  extra?: Record<string, unknown>;
}

interface RawRun {
  id: string;
  project_id: string;
  stage: StageId;
  mode: "fast" | "cmbagent";
  status: RunStatus;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  config?: Record<string, unknown>;
  pid?: number | null;
  token_input?: number;
  token_output?: number;
}

function adaptRun(r: RawRun): RunRecord {
  return {
    id: r.id,
    projectId: r.project_id,
    stage: r.stage,
    mode: r.mode,
    status: r.status,
    startedAt: r.started_at ?? null,
    finishedAt: r.finished_at ?? null,
    error: r.error ?? null,
    config: r.config ?? {},
    pid: r.pid ?? null,
    tokenInput: r.token_input ?? 0,
    tokenOutput: r.token_output ?? 0,
  };
}

// Iter-31 — paper artifact shape returned by api.getPaperArtifacts.
// PaperPreview consumes sections directly; pdfUrl is wired into the
// PDF tab when the worker has produced paper/main.pdf.
export interface PaperSectionArtifact {
  id: string;
  name: string;
  status: "compiled" | "warning" | "failed" | "pending";
  markdown?: string;
  tex?: string;
}

export interface PaperArtifacts {
  pdfUrl?: string;
  submissionZipUrl?: string;
  sections: PaperSectionArtifact[];
}

export interface ScientificScoreAxis {
  score: number;
  label: string;
  summary: string;
  signals: string[];
  cautions: string[];
}

export interface ScientificScores {
  overall: {
    score: number;
    label: string;
    summary: string;
  };
  axes: {
    originality: ScientificScoreAxis;
    impact: ScientificScoreAxis;
    findings: ScientificScoreAxis;
  };
  inputs: {
    has_data: boolean;
    has_idea: boolean;
    has_literature: boolean;
    has_method: boolean;
    has_results: boolean;
    has_paper_tex: boolean;
    has_paper_pdf: boolean;
    plot_count: number;
    metric_mentions: number;
  };
  updated_at: string;
}

export type McpTransport = "stdio" | "http" | "sse";
export type McpStatus = "untested" | "ok" | "error" | "inactive";

export interface ToolInfo {
  id: string;
  name: string;
  description: string;
  category: string;
  permissions: string[];
  enabled: boolean;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
}

export interface McpServerInfo {
  id: string;
  name: string;
  description: string;
  transport: McpTransport;
  target: string;
  enabled: boolean;
  built_in: boolean;
  auth_configured: boolean;
  status: McpStatus;
  status_message?: string | null;
  tools: string[];
  tool_count: number;
  created_at?: string | null;
  updated_at?: string | null;
  last_checked_at?: string | null;
}

export interface ToolingState {
  tools: ToolInfo[];
  mcp_servers: McpServerInfo[];
  custom_mcp_servers: McpServerInfo[];
}

// Parse top-level section commands out of a LaTeX source so the Sections
// gutter has something honest to render. We only look at the document
// body; anything before begin{document} is preamble and section refs
// inside macros aren't real sections.
function latexSectionToMarkdown(sectionTex: string): string {
  return sectionTex
    .replace(/\\section\*?\{([^}]+)\}/g, "## $1\n\n")
    .replace(/\\label\{[^}]*\}/g, "")
    .replace(/\\(?:citep?|ref|eqref)\{([^}]*)\}/g, "[$1]")
    .replace(/\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}/g, "$1")
    .replace(/\\[a-zA-Z]+/g, "")
    .replace(/[{}]/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function parseTexSections(tex: string): PaperSectionArtifact[] {
  const begin = tex.indexOf("\\begin{document}");
  const body = begin >= 0 ? tex.slice(begin) : tex;
  const re = /\\section\*?\{([^}]+)\}/g;
  const matches: Array<{ id: string; name: string; start: number }> = [];
  const out: PaperSectionArtifact[] = [];
  const seen = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(body)) !== null) {
    const name = m[1].trim();
    if (!name) continue;
    const id = name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      || `section-${out.length + 1}`;
    if (seen.has(id)) continue;
    seen.add(id);
    matches.push({ id, name, start: m.index });
  }
  matches.forEach((match, index) => {
    const next = matches[index + 1];
    const sectionTex = body.slice(match.start, next?.start).trim();
    out.push({
      id: match.id,
      name: match.name,
      status: "compiled",
      markdown: latexSectionToMarkdown(sectionTex),
      tex: sectionTex,
    });
  });
  if (out.length === 0 && tex.trim()) {
    const sectionTex = tex.trim();
    out.push({
      id: "full-document",
      name: "Full document",
      status: "compiled",
      markdown: latexSectionToMarkdown(sectionTex),
      tex: sectionTex,
    });
  }
  return out;
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

  async getTooling(): Promise<ToolingState> {
    return fetchJson<ToolingState>("/tooling");
  },

  async setToolEnabled(toolId: string, enabled: boolean): Promise<ToolInfo> {
    return fetchJson<ToolInfo>(`/tooling/tools/${encodeURIComponent(toolId)}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    });
  },

  async setMcpEnabled(serverId: string, enabled: boolean): Promise<McpServerInfo> {
    return fetchJson<McpServerInfo>(`/tooling/mcp/${encodeURIComponent(serverId)}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    });
  },

  async testMcpServer(serverId: string): Promise<McpServerInfo> {
    return fetchJson<McpServerInfo>(`/tooling/mcp/${encodeURIComponent(serverId)}/test`, {
      method: "POST",
    });
  },

  async createCustomMcpServer(body: {
    name: string;
    description?: string;
    transport: McpTransport;
    target: string;
    auth?: string;
    enabled?: boolean;
  }): Promise<McpServerInfo> {
    return fetchJson<McpServerInfo>("/tooling/mcp/custom", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async updateCustomMcpServer(
    serverId: string,
    body: Partial<{
      name: string;
      description: string;
      transport: McpTransport;
      target: string;
      auth: string;
      enabled: boolean;
    }>,
  ): Promise<McpServerInfo> {
    return fetchJson<McpServerInfo>(`/tooling/mcp/custom/${encodeURIComponent(serverId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  async deleteCustomMcpServer(serverId: string): Promise<void> {
    await fetchJson(`/tooling/mcp/custom/${encodeURIComponent(serverId)}`, {
      method: "DELETE",
    });
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

  async getPublicationSettings(pid: string): Promise<PublicationSettings> {
    return fetchJson<PublicationSettings>(`/projects/${pid}/publication_settings`);
  },

  async updatePublicationSettings(
    pid: string,
    body: PublicationSettings,
  ): Promise<PublicationSettings> {
    return fetchJson<PublicationSettings>(`/projects/${pid}/publication_settings`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  async listPublications(params: {
    tag?: string;
    q?: string;
    author?: string;
    limit?: number;
  } = {}): Promise<ResearchPublication[]> {
    const search = new URLSearchParams();
    if (params.tag) search.set("tag", params.tag);
    if (params.q) search.set("q", params.q);
    if (params.author) search.set("author", params.author);
    if (params.limit) search.set("limit", String(params.limit));
    const suffix = search.size ? `?${search.toString()}` : "";
    const raw = await fetchJson<{ publications: RawResearchPublication[] }>(`/publications${suffix}`);
    return raw.publications.map(adaptResearchPublication);
  },

  async publishProjectPublication(
    pid: string,
    body: PublishPublicationBody,
  ): Promise<ResearchPublication> {
    const raw = await fetchJson<RawResearchPublication>(`/projects/${pid}/publications`, {
      method: "POST",
      body: JSON.stringify({
        ...body,
        tagged_authors: body.tagged_authors?.map(toRawFeedAuthor),
      }),
    });
    return adaptResearchPublication(raw);
  },

  async commentOnPublication(
    publicationId: string,
    body: PublicationCommentBody,
  ): Promise<ResearchPublication["comments"][number]> {
    const raw = await fetchJson<RawPublicationComment>(`/publications/${publicationId}/comments`, {
      method: "POST",
      body: JSON.stringify({
        ...body,
        tagged_authors: body.tagged_authors?.map(toRawFeedAuthor),
      }),
    });
    return adaptPublicationComment(raw);
  },

  async likePublication(publicationId: string): Promise<ResearchPublication> {
    const raw = await fetchJson<RawResearchPublication>(`/publications/${publicationId}/likes/me`, {
      method: "PUT",
    });
    return adaptResearchPublication(raw);
  },

  async unlikePublication(publicationId: string): Promise<ResearchPublication> {
    const raw = await fetchJson<RawResearchPublication>(`/publications/${publicationId}/likes/me`, {
      method: "DELETE",
    });
    return adaptResearchPublication(raw);
  },

  async sharePublication(publicationId: string, target = "link"): Promise<ResearchPublication> {
    const raw = await fetchJson<RawResearchPublication>(`/publications/${publicationId}/shares`, {
      method: "POST",
      body: JSON.stringify({ target }),
    });
    return adaptResearchPublication(raw);
  },

  async tagPublicationAuthors(
    publicationId: string,
    authors: PublicationFeedAuthor[],
  ): Promise<ResearchPublication> {
    const raw = await fetchJson<RawResearchPublication>(`/publications/${publicationId}/author-tags`, {
      method: "POST",
      body: JSON.stringify({ authors: authors.map(toRawFeedAuthor) }),
    });
    return adaptResearchPublication(raw);
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
    body: StageRunBody = {},
  ): Promise<RawRun> {
    return fetchJson(`/projects/${pid}/stages/${stage}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async listRuns(pid: string): Promise<RunRecord[]> {
    const raw = await fetchJson<RawRun[]>(`/projects/${pid}/runs`);
    return raw.map(adaptRun);
  },

  async listRunEvents(pid: string, runId: string): Promise<RunEvent[]> {
    return fetchJson<RunEvent[]>(`/projects/${pid}/runs/${runId}/events/history`);
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

  /**
   * Aggregate token + cost usage for ``pid``, broken down by stage
   * and model. Backend route: ``GET /api/v1/projects/{pid}/usage``.
   * Mirrors ``aggregate_project_usage`` in token_tracker.py — totals
   * across every stage's ``LLM_calls.txt``.
   */
  async getProjectUsage(pid: string): Promise<ProjectUsage> {
    return fetchJson<ProjectUsage>(`/projects/${pid}/usage`);
  },

  /**
   * Live in-memory token usage for an active run. 404s once the run
   * is no longer in the ledger; callers should treat that as "not
   * tracked" rather than an error. Backend route:
   * ``GET /api/v1/runs/{run_id}/usage``.
   */
  async getRunUsage(runId: string): Promise<RunUsage> {
    return fetchJson<RunUsage>(`/runs/${runId}/usage`);
  },

  /**
   * Subscribe to SSE for a run with auto-reconnect.
   *
   * The browser's EventSource auto-reconnects on a dropped TCP
   * connection but bails permanently on an HTTP error (e.g. backend
   * restart returning 502 briefly). We wrap it so:
   *
   *   - ``onerror`` closes the source and schedules a reconnect with
   *     exponential backoff (500ms -> 30s, ±20% jitter).
   *   - We stop reconnecting once a ``stage.finished`` event arrives
   *     (the run is done) or the consumer calls the returned ``close``.
   *   - Replayed events across reconnects are de-duplicated by a
   *     ``${ts}:${kind}:${stage|name}`` key, capped at 200 entries.
   *
   * Returns an unsubscribe fn matching the original signature.
   */
  subscribeRunEvents(
    pid: string,
    runId: string,
    onEvent: (evt: RunEvent) => void,
    onError?: (e: unknown) => void,
  ): () => void {
    const url = `${API_BASE}/projects/${pid}/runs/${runId}/events`;
    let es: EventSource | null = null;
    let stopped = false;
    let finished = false;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    const seen = new Set<string>();
    const seenOrder: string[] = [];
    const SEEN_CAP = 200;

    const dedupKey = (raw: Record<string, unknown>): string => {
      const ts = String(raw.ts ?? "");
      const kind = String(raw.kind ?? "");
      const tag = String(raw.stage ?? raw.name ?? raw.path ?? raw.index ?? "");
      return `${ts}:${kind}:${tag}`;
    };

    const remember = (key: string): boolean => {
      if (seen.has(key)) return false;
      seen.add(key);
      seenOrder.push(key);
      if (seenOrder.length > SEEN_CAP) {
        const evicted = seenOrder.shift();
        if (evicted !== undefined) seen.delete(evicted);
      }
      return true;
    };

    const scheduleReconnect = () => {
      if (stopped || finished) return;
      const base = Math.min(30_000, 500 * 2 ** attempt);
      const jitter = base * (0.8 + Math.random() * 0.4);
      attempt += 1;
      reconnectTimer = setTimeout(connect, jitter);
    };

    const connect = () => {
      if (stopped || finished) return;
      reconnectTimer = null;
      es = new EventSource(url, { withCredentials: true });
      es.onopen = () => {
        attempt = 0;
      };
      es.onmessage = (e) => {
        try {
          const raw = JSON.parse(e.data) as Record<string, unknown>;
          const key = dedupKey(raw);
          if (!remember(key)) return;
          if (raw.kind === "stage.finished") {
            finished = true;
            onEvent(raw as RunEvent);
            es?.close();
            es = null;
            return;
          }
          onEvent(raw as RunEvent);
        } catch (err) {
          onError?.(err);
        }
      };
      es.onerror = (e) => {
        onError?.(e);
        es?.close();
        es = null;
        scheduleReconnect();
      };
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      es?.close();
      es = null;
    };
  },

  // ------------------------------------------------------------ keys
  async getKeysStatus(): Promise<KeysStatus> {
    return fetchJson<KeysStatus>("/keys/status");
  },

  async getHuggingFaceAccount(): Promise<HuggingFaceAccountStatus> {
    return fetchJson<HuggingFaceAccountStatus>("/keys/huggingface/account");
  },

  async updateKeys(
    payload: Partial<{
      OPENAI: string;
      GEMINI: string;
      ANTHROPIC: string;
      HUGGINGFACE: string;
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

  // Iter-31: read paper artifacts produced by the Paper stage.
  // The worker writes paper/main.pdf and paper/main.tex into the project
  // directory. Both are exposed by GET /api/v1/projects/{pid}/files/{relpath}.
  // We probe the PDF with HEAD (FastAPI auto-registers HEAD for GET routes),
  // then fetch the .tex source so we can derive a sections outline from
  // top-level section commands. Returns empty arrays when neither artifact
  // exists; PaperPreview renders its own honest empty state in that case.
  async getPaperArtifacts(pid: string): Promise<PaperArtifacts> {
    const pdfPath = `/projects/${pid}/files/paper/main.pdf`;
    const texPath = `/projects/${pid}/files/paper/main.tex`;
    const zipPath = `/projects/${pid}/files/paper/submission_package.zip`;
    const pdfUrl = `${API_BASE}${pdfPath}`;
    const texUrl = `${API_BASE}${texPath}`;
    const submissionZipUrl = `${API_BASE}${zipPath}`;

    let pdfExists = false;
    let zipExists = false;
    try {
      const head = await fetch(pdfUrl, {
        method: "HEAD",
        credentials: "include",
      });
      pdfExists = head.ok;
    } catch {
      pdfExists = false;
    }
    try {
      const head = await fetch(submissionZipUrl, {
        method: "HEAD",
        credentials: "include",
      });
      zipExists = head.ok;
    } catch {
      zipExists = false;
    }

    let sections: PaperSectionArtifact[] = [];
    try {
      const r = await fetch(texUrl, { credentials: "include" });
      if (r.ok) {
        const tex = await r.text();
        sections = parseTexSections(tex);
      }
    } catch {
      /* tex absent is fine */
    }

    return {
      pdfUrl: pdfExists ? pdfUrl : undefined,
      submissionZipUrl: zipExists ? submissionZipUrl : undefined,
      sections,
    };
  },

  async getScientificScores(pid: string): Promise<ScientificScores> {
    return fetchJson<ScientificScores>(`/projects/${pid}/scientific-scores`);
  },

  async testKey(
    provider: "OPENAI" | "GEMINI" | "ANTHROPIC" | "HUGGINGFACE",
  ): Promise<{ ok: boolean; latency_ms?: number; error?: string; account?: string }> {
    try {
      return await fetchJson<{
        ok: boolean;
        latency_ms?: number;
        error?: string;
        account?: string;
      }>(
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
  HUGGINGFACE: KeyState;
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

export interface HuggingFaceOrg {
  name?: string | null;
  fullname?: string | null;
  role?: string | null;
  type?: string | null;
}

export interface HuggingFaceAccount {
  name?: string | null;
  fullname?: string | null;
  email?: string | null;
  type?: string | null;
  isPro?: boolean | null;
  avatarUrl?: string | null;
  orgs: HuggingFaceOrg[];
}

export interface HuggingFaceAccountStatus {
  connected: boolean;
  account: HuggingFaceAccount | null;
  error?: string | null;
}
