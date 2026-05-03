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

export type Provider = "openai" | "gemini" | "anthropic" | "perplexity" | "semantic_scholar";

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

export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Run {
  id: string;
  projectId: string;
  projectName?: string;
  stage: StageId;
  mode: Mode;
  status: RunStatus;
  startedAt?: string;
  finishedAt?: string;
  error?: string;
  tokenInput: number;
  tokenOutput: number;
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
