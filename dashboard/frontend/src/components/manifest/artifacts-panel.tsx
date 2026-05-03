"use client";

import * as React from "react";
import { Download, ExternalLink, FileText } from "lucide-react";
import {
  api,
  ApiError,
  downloadArtifact,
  type RunArtifact,
  type RunArtifactKind,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface ArtifactsPanelProps {
  projectId: string | null;
  runId: string;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

const KIND_LABEL: Record<RunArtifactKind, string> = {
  paper_pdf: "Paper",
  manifest: "Manifest",
  report: "Report",
  data: "Data",
  log: "Log",
  other: "Other",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; items: RunArtifact[] }
  | { kind: "missing" }
  | { kind: "error"; message: string };

export function ArtifactsPanel({ projectId, runId }: ArtifactsPanelProps) {
  const [state, setState] = React.useState<LoadState>({ kind: "loading" });

  React.useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setState({ kind: "loading" });

    api
      .listRunArtifacts(projectId, runId)
      .then((items) => {
        if (cancelled) return;
        setState({ kind: "ready", items });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setState({ kind: "missing" });
          return;
        }
        const msg =
          err instanceof ApiError
            ? `HTTP ${err.status}`
            : err instanceof Error
              ? err.message
              : "Failed to load artifacts";
        setState({ kind: "error", message: msg });
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, runId]);

  // Without a project id we have no URL to fetch — render the same
  // empty-state copy the backend would show on a missing run dir so
  // the run-detail layout doesn't suddenly grow a hidden gap.
  if (!projectId) {
    return <EmptyState />;
  }

  if (state.kind === "loading") {
    return (
      <PanelShell>
        <p className="px-4 py-4 text-[13px] text-(--color-text-row-meta)">
          Loading artifacts…
        </p>
      </PanelShell>
    );
  }

  if (state.kind === "error") {
    return (
      <PanelShell>
        <p className="px-4 py-4 text-[13px] text-(--color-status-red-spec)">
          Failed to load artifacts: {state.message}
        </p>
      </PanelShell>
    );
  }

  if (state.kind === "missing" || state.items.length === 0) {
    return <EmptyState />;
  }

  return (
    <PanelShell count={state.items.length}>
      <ArtifactTable items={state.items} projectId={projectId} />
    </PanelShell>
  );
}

function EmptyState() {
  return (
    <section
      className="surface-linear-card px-4 py-4"
      data-testid="artifacts-panel-empty"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <div className="font-label" style={{ marginBottom: 6 }}>
        Artifacts
      </div>
      <p className="text-[13px] text-(--color-text-row-meta)">
        No artifacts available yet.
      </p>
    </section>
  );
}

function PanelShell({
  count,
  children,
}: {
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="artifacts-panel"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <FileText size={16} className="text-(--color-text-tertiary)" />
        <h2
          className="text-(--color-text-primary-strong) text-[15px]"
          style={{ fontWeight: 510 }}
        >
          Artifacts
        </h2>
        {typeof count === "number" ? (
          <span className="text-[12px] text-(--color-text-tertiary)">
            {count} {count === 1 ? "file" : "files"}
          </span>
        ) : null}
      </header>
      {children}
    </section>
  );
}

function ArtifactTable({
  items,
  projectId,
}: {
  items: RunArtifact[];
  projectId: string;
}) {
  return (
    <table className="w-full border-collapse text-[13px]">
      <thead>
        <tr
          className="text-left text-(--color-text-tertiary)"
          style={{ borderBottom: "1px solid var(--color-border-standard)" }}
        >
          <Th>Filename</Th>
          <Th align="right">Size</Th>
          <Th>Kind</Th>
          <Th align="right">Actions</Th>
        </tr>
      </thead>
      <tbody>
        {items.map((entry) => (
          <ArtifactRow key={entry.path} entry={entry} projectId={projectId} />
        ))}
      </tbody>
    </table>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      className="px-4 py-2 font-mono text-[11px] font-normal uppercase tracking-wide"
      style={{ textAlign: align }}
    >
      {children}
    </th>
  );
}

function ArtifactRow({
  entry,
  projectId,
}: {
  entry: RunArtifact;
  projectId: string;
}) {
  const filename = entry.path.split("/").pop() ?? entry.path;
  const fileUrl = `${API_BASE}/projects/${projectId}/files/${entry.path}`;
  return (
    <tr
      className="text-(--color-text-row-title)"
      style={{ borderTop: "1px solid var(--color-border-standard)" }}
    >
      <td className="px-4 py-2.5 align-top">
        <div className="flex flex-col gap-0.5 min-w-0">
          <span className="truncate">{filename}</span>
          {filename !== entry.path ? (
            <span className="font-mono text-[11px] text-(--color-text-tertiary) truncate">
              {entry.path}
            </span>
          ) : null}
        </div>
      </td>
      <td className="px-4 py-2.5 align-top text-right font-mono text-[12px] text-(--color-text-row-meta)">
        {formatSize(entry.size)}
      </td>
      <td className="px-4 py-2.5 align-top">
        <KindBadge kind={entry.kind} />
      </td>
      <td className="px-4 py-2.5 align-top text-right">
        <RowActions entry={entry} projectId={projectId} fileUrl={fileUrl} />
      </td>
    </tr>
  );
}

function KindBadge({ kind }: { kind: RunArtifactKind }) {
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[11px]"
      style={{
        backgroundColor: "var(--color-bg-hover)",
        color: "var(--color-text-row-title)",
      }}
    >
      {KIND_LABEL[kind]}
    </span>
  );
}

function RowActions({
  entry,
  projectId,
  fileUrl,
}: {
  entry: RunArtifact;
  projectId: string;
  fileUrl: string;
}) {
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const filename = entry.path.split("/").pop() ?? entry.path;
  const onDownload = React.useCallback(async () => {
    setPending(true);
    setError(null);
    try {
      await downloadArtifact(projectId, entry.path, filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setPending(false);
    }
  }, [entry.path, filename, projectId]);

  return (
    <div className="inline-flex items-center gap-2">
      {error ? (
        <span
          className="text-[11px] text-(--color-status-red-spec)"
          title={error}
        >
          failed
        </span>
      ) : null}
      {entry.kind === "paper_pdf" ? (
        <a
          href={fileUrl}
          target="_blank"
          rel="noreferrer noopener"
          className={cn(
            "inline-flex items-center gap-1 text-[12px]",
            "text-(--color-brand-interactive) hover:underline",
          )}
          data-testid={`artifact-open-${entry.path}`}
        >
          Open
          <ExternalLink size={11} />
        </a>
      ) : null}
      <button
        type="button"
        onClick={onDownload}
        disabled={pending}
        className={cn(
          "inline-flex items-center gap-1 rounded px-2 py-1 text-[12px]",
          "border border-(--color-border-standard)",
          "text-(--color-text-row-title) hover:bg-(--color-bg-hover)",
          "disabled:opacity-50 disabled:cursor-not-allowed",
        )}
        data-testid={`artifact-download-${entry.path}`}
      >
        <Download size={11} />
        {pending ? "…" : "Download"}
      </button>
    </div>
  );
}
