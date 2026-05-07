export type StageId =
  | "data"
  | "idea"
  | "literature"
  | "method"
  | "results"
  | "paper"
  | "referee";

export type StageStatus =
  | "empty"
  | "pending"
  | "running"
  | "done"
  | "stale"
  | "failed";

export interface Stage {
  id: StageId;
  label: string;
  status: StageStatus;
  model?: string;
  durationMs?: number;
  lastRunAt?: string;
  origin?: "ai" | "edited";
  progressLabel?: string;
}

export type Mode = "fast" | "cmbagent";

export type Provider =
  | "openai"
  | "gemini"
  | "anthropic"
  | "huggingface"
  | "perplexity"
  | "semantic_scholar";

export interface ModelDef {
  id: string;
  label: string;
  provider: Provider;
  maxOutputTokens: number;
  temperature: number | null;
  costInputPer1k?: number;
  costOutputPer1k?: number;
  notes?: string;
}

export type Journal = "NONE" | "AAS" | "APS" | "ICML" | "JHEP" | "NeurIPS" | "PASJ";

export type PublicationTaskKind = "section" | "review" | "completion" | "other";
export type PublicationTaskStatus = "todo" | "in_progress" | "blocked" | "done";

export interface PublicationAuthor {
  id: string;
  name: string;
  email?: string | null;
  affiliation?: string | null;
  role: string;
  order: number;
}

export interface PublicationDates {
  target?: string | null;
  submitted?: string | null;
  accepted?: string | null;
  published?: string | null;
}

export interface PublicationTask {
  id: string;
  title: string;
  kind: PublicationTaskKind;
  section?: string | null;
  assignee?: string | null;
  assignee_email?: string | null;
  status: PublicationTaskStatus;
  due_at?: string | null;
  completed_at?: string | null;
  notes?: string | null;
}

export interface PublicationSettings {
  authors: PublicationAuthor[];
  dates: PublicationDates;
  tasks: PublicationTask[];
}

export interface Project {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  journal: Journal;
  stages: Record<StageId, Stage>;
  activeRun?: ActiveRun | null;
  totalTokens: number;
  totalCostCents: number;
  publicationSettings?: PublicationSettings;
  // Iter-27: per-project approvals carried alongside the Project shape
  // so synchronous gate evaluation (``getBlockingApproval``) doesn't
  // have to await an extra round trip per stage. ``null`` / undefined
  // means "no approvals recorded yet".
  approvals?: {
    per_stage: Record<string, "pending" | "approved" | "rejected" | "skipped">;
    auto_skip: boolean;
  } | null;
}

export interface ActiveRun {
  runId: string;
  stage: StageId;
  startedAt: string;
  step?: number;
  totalSteps?: number;
  attempt?: number;
  totalAttempts?: number;
  ipuBudget?: number;
  ipuUsed?: number;
}

export type LogLevel = "info" | "tool" | "error" | "warn";

export interface LogLine {
  ts: string;
  source: string;
  agent?: string;
  level: LogLevel;
  text: string;
  tokens?: number;
}

export interface CitationPaper {
  id: string;
  title: string;
  authors: string[];
  year: number;
  venue?: string;
  abstract?: string;
  url?: string;
  arxivId?: string;
  bibtex?: string;
}
