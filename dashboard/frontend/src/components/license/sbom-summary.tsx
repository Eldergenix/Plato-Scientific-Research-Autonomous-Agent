"use client";

import * as React from "react";
import { Download, FileJson } from "lucide-react";
import { Button } from "@/components/ui/button";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

export interface SbomSummaryData {
  /** CycloneDX spec version, e.g. "1.5". */
  specVersion?: string | null;
  /** Number of `components[]` entries. */
  componentCount: number;
}

/** Pull the count + version out of an arbitrary CycloneDX document.
 *
 * Defensive about missing or oddly-shaped fields — the SBOM is generated
 * by an external tool, and we don't want a malformed document to crash
 * the page.
 */
export function summarizeSbom(doc: unknown): SbomSummaryData {
  const obj = (doc ?? {}) as Record<string, unknown>;
  const specVersion =
    typeof obj.specVersion === "string" ? obj.specVersion : null;
  const components = Array.isArray(obj.components) ? obj.components : [];
  return { specVersion, componentCount: components.length };
}

async function fetchSbom(): Promise<{ doc: unknown; raw: string }> {
  const r = await fetch(`${API_BASE}/sbom`, {
    headers: { Accept: "application/json" },
  });
  if (!r.ok) {
    let msg = `SBOM unavailable (HTTP ${r.status})`;
    try {
      const body = await r.json();
      const detail = (body as { detail?: { message?: string; hint?: string } })
        ?.detail;
      if (detail?.message) msg = detail.message;
      if (detail?.hint) msg = `${msg} — ${detail.hint}`;
    } catch {
      /* swallow JSON parse errors; the status code message is enough */
    }
    throw new Error(msg);
  }
  const raw = await r.text();
  let doc: unknown = null;
  try {
    doc = JSON.parse(raw);
  } catch {
    /* leave doc as null; downloading raw bytes still works */
  }
  return { doc, raw };
}

function downloadBlob(content: string, filename: string) {
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Defer revocation so Safari has time to start the download.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function SbomSummary() {
  const [summary, setSummary] = React.useState<SbomSummaryData | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [downloading, setDownloading] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    fetchSbom()
      .then(({ doc }) => {
        if (cancelled) return;
        setSummary(summarizeSbom(doc));
        setError(null);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onDownload = async () => {
    setDownloading(true);
    try {
      const { raw } = await fetchSbom();
      downloadBlob(raw, "sbom.json");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <section
      className="surface-linear-card overflow-hidden"
      data-testid="sbom-summary"
      style={{ border: "1px solid var(--color-border-card)" }}
    >
      <header
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-border-standard)" }}
      >
        <div className="flex items-center gap-2">
          <FileJson size={14} className="text-(--color-text-tertiary)" />
          <h2
            className="text-(--color-text-primary-strong) text-[15px]"
            style={{ fontWeight: 510 }}
          >
            SBOM (CycloneDX)
          </h2>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onDownload}
          disabled={downloading || !!error}
          data-testid="sbom-download-button"
        >
          <Download size={12} strokeWidth={1.75} />
          {downloading ? "Downloading…" : "Download SBOM"}
        </Button>
      </header>

      <div className="grid grid-cols-2 gap-3 px-4 py-3">
        <Stat label="Spec version" value={summary?.specVersion ?? "—"} mono />
        <Stat
          label="Components"
          value={
            summary?.componentCount !== undefined
              ? String(summary.componentCount)
              : "—"
          }
          mono
        />
      </div>

      {loading ? (
        <p
          className="px-4 py-2 text-[12px] text-(--color-text-row-meta)"
          style={{ borderTop: "1px solid var(--color-border-standard)" }}
          data-testid="sbom-loading"
        >
          Loading SBOM…
        </p>
      ) : error ? (
        <p
          className="px-4 py-2 text-[12px] text-(--color-status-red-spec)"
          style={{ borderTop: "1px solid var(--color-border-standard)" }}
          data-testid="sbom-error"
        >
          {error}
        </p>
      ) : null}
    </section>
  );
}

function Stat({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-label">{label}</span>
      <span
        className={
          mono
            ? "font-mono tabular-nums text-[14px] text-(--color-text-primary)"
            : "text-[14px] text-(--color-text-primary)"
        }
      >
        {value}
      </span>
    </div>
  );
}
