"use client";

import * as React from "react";
import {
  ChevronDown,
  FileText,
  FileCode,
  AlignLeft,
  Wrench,
  SkipForward,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";

// react-pdf is loaded lazily so a missing dependency / SSR doesn't blow up
// the rest of the module (the worker URL is set the first time we actually
// render the PDF tab).
type ReactPdfModule = typeof import("react-pdf") | null;
let reactPdfModule: ReactPdfModule = null;
let reactPdfLoadAttempted = false;
let reactPdfLoadPromise: Promise<ReactPdfModule> | null = null;

function loadReactPdf(): Promise<ReactPdfModule> {
  if (reactPdfModule || reactPdfLoadAttempted) {
    return Promise.resolve(reactPdfModule);
  }
  if (reactPdfLoadPromise) return reactPdfLoadPromise;
  reactPdfLoadPromise = import("react-pdf")
    .then((mod) => {
      reactPdfModule = mod;
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const v = (mod as any).pdfjs?.version ?? "latest";
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (mod as any).pdfjs.GlobalWorkerOptions.workerSrc =
          `https://unpkg.com/pdfjs-dist@${v}/build/pdf.worker.min.mjs`;
      } catch {
        /* worker config best-effort */
      }
      return mod;
    })
    .catch(() => null)
    .finally(() => {
      reactPdfLoadAttempted = true;
    });
  return reactPdfLoadPromise;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PaperSectionStatus = "compiled" | "warning" | "failed" | "pending";

export interface PaperSection {
  id: string;
  name: string;
  status: PaperSectionStatus;
  markdown?: string;
  tex?: string;
  errorMessage?: string;
}

export interface PaperPreviewProps {
  pdfUrl?: string;
  sections: PaperSection[];
  versions?: Array<{ id: string; label: string; current?: boolean }>;
  onRetrySection?: (sectionId: string) => void;
  onAutoFix?: (sectionId: string) => void;
  onSelectVersion?: (versionId: string) => void;
}

type Tab = "pdf" | "sections" | "latex";

const TABS: Array<{ id: Tab; label: string; icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }> }> = [
  { id: "pdf", label: "PDF", icon: FileText },
  { id: "sections", label: "Sections", icon: AlignLeft },
  { id: "latex", label: "LaTeX", icon: FileCode },
];

// ---------------------------------------------------------------------------
// Iter-24 cleanup: deleted SAMPLE_SECTIONS — six PaperSection entries that
// rendered the GW231123 ringdown abstract / methods / results as the
// default content for every paper-stage render. Callers that omit
// ``sections`` now hit the empty state below instead of leaking the
// astro narrative across non-astro projects (or the "Untitled project"
// first-paint state). When the parent has no sections to pass — because
// the paper graph hasn't run, or the paper/sections/* files don't exist
// yet — the user sees an honest "no paper yet" affordance.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PaperPreview({
  pdfUrl,
  sections = [],
  versions,
  onRetrySection,
  onAutoFix,
  onSelectVersion,
}: PaperPreviewProps) {
  const [tab, setTab] = React.useState<Tab>("pdf");
  const [activeSectionId, setActiveSectionId] = React.useState<string | null>(
    sections[0]?.id ?? null,
  );

  const failed = sections.filter((s) => s.status === "failed");
  const firstFailed = failed[0];

  const sectionRefs = React.useRef<Record<string, HTMLElement | null>>({});

  const jumpToSection = React.useCallback((id: string, targetTab: Tab = "latex") => {
    setTab(targetTab);
    setActiveSectionId(id);
    requestAnimationFrame(() => {
      const el = sectionRefs.current[id];
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        if (el instanceof HTMLDetailsElement) el.open = true;
      }
    });
  }, []);

  return (
    <div className="flex h-full w-full flex-col surface-linear-card overflow-hidden">
      {/* ---- Top bar: tabs + version pills ---- */}
      <div className="flex items-center justify-between gap-3 px-3 hairline-b" style={{ height: "var(--h-toolbar)" }}>
        <div role="tablist" className="flex items-center gap-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = t.id === tab;
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={active}
                data-state={active ? "active" : "inactive"}
                onClick={() => setTab(t.id)}
                className="tab-pill gap-1.5"
              >
                <Icon size={12} strokeWidth={1.75} />
                {t.label}
              </button>
            );
          })}
        </div>

        {versions && versions.length > 0 && (
          <div className="flex items-center gap-1">
            {versions.map((v) => {
              const active = v.current;
              return (
                <button
                  key={v.id}
                  type="button"
                  data-state={active ? "active" : "inactive"}
                  onClick={() => onSelectVersion?.(v.id)}
                  className="tab-pill"
                  style={{ minWidth: 32 }}
                >
                  {v.label}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* ---- Body: gutter + content ---- */}
      <div className="flex flex-1 min-h-0">
        <SectionHealthGutter
          sections={sections}
          activeId={activeSectionId}
          onSelect={(id) => {
            const sec = sections.find((s) => s.id === id);
            if (sec?.status === "failed") {
              jumpToSection(id, "latex");
            } else {
              jumpToSection(id, tab === "pdf" ? "sections" : tab);
            }
          }}
        />

        <div className="flex-1 min-w-0 overflow-auto">
          {tab === "pdf" && <PdfTab pdfUrl={pdfUrl} />}
          {tab === "sections" && (
            <SectionsTab
              sections={sections}
              sectionRefs={sectionRefs}
              activeId={activeSectionId}
              onActivate={setActiveSectionId}
            />
          )}
          {tab === "latex" && (
            <LatexTab
              sections={sections}
              sectionRefs={sectionRefs}
              activeId={activeSectionId}
              onActivate={setActiveSectionId}
            />
          )}
        </div>
      </div>

      {/* ---- Failure tray ---- */}
      {firstFailed && (
        <FailureTray
          section={firstFailed}
          totalFailed={failed.length}
          onAutoFix={() => onAutoFix?.(firstFailed.id)}
          onManualFix={() => jumpToSection(firstFailed.id, "latex")}
          onSkip={() => onRetrySection?.(firstFailed.id)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section health gutter
// ---------------------------------------------------------------------------

const STATUS_COLOR: Record<PaperSectionStatus, string> = {
  compiled: "var(--color-status-green-spec)",
  warning: "var(--color-status-amber-spec)",
  failed: "var(--color-status-red-spec)",
  pending: "var(--color-text-quaternary-spec)",
};

const STATUS_LABEL: Record<PaperSectionStatus, string> = {
  compiled: "Compiled",
  warning: "Warning",
  failed: "Failed",
  pending: "Pending",
};

function SectionHealthGutter({
  sections,
  activeId,
  onSelect,
}: {
  sections: PaperSection[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div
      className="hairline-r flex flex-col items-stretch py-2 gap-1"
      style={{ width: 12, flex: "0 0 12px", background: "var(--color-bg-page)" }}
      aria-label="Section compile health"
    >
      {sections.map((s) => {
        const isActive = s.id === activeId;
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s.id)}
            title={`${s.name} — ${STATUS_LABEL[s.status]}${s.errorMessage ? `: ${s.errorMessage}` : ""}`}
            aria-label={`${s.name}: ${STATUS_LABEL[s.status]}`}
            className={cn(
              "block rounded-[2px] transition-opacity flex-1",
              isActive ? "opacity-100" : "opacity-70 hover:opacity-100",
            )}
            style={{
              minHeight: 18,
              background: STATUS_COLOR[s.status],
              boxShadow: isActive
                ? `0 0 0 1px var(--color-bg-page), 0 0 0 2px ${STATUS_COLOR[s.status]}`
                : undefined,
            }}
          />
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PDF tab
// ---------------------------------------------------------------------------

function PdfTab({ pdfUrl }: { pdfUrl?: string }) {
  const [pdfLib, setPdfLib] = React.useState<ReactPdfModule>(reactPdfModule);
  const [numPages, setNumPages] = React.useState<number | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    loadReactPdf().then((mod) => {
      if (!cancelled) setPdfLib(mod);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!pdfUrl) {
    return (
      <Placeholder
        icon={<FileText size={28} strokeWidth={1.25} />}
        title="No PDF yet"
        body="Run the Paper stage to compile this project's PDF. The rendered output will appear here."
      />
    );
  }

  if (!pdfLib) {
    return (
      <Placeholder
        icon={<Loader2 size={28} strokeWidth={1.25} className="animate-spin" />}
        title="Loading PDF viewer"
        body="If this persists, install react-pdf to enable PDF preview."
      />
    );
  }

  const { Document, Page } = pdfLib;

  return (
    <div className="px-4 py-4 flex flex-col items-center gap-3">
      <Document
        file={pdfUrl}
        onLoadSuccess={({ numPages: n }) => setNumPages(n)}
        onLoadError={(err: Error) => setLoadError(err.message)}
        loading={
          <div className="text-[12px] text-(--color-text-tertiary) py-12">
            Rendering PDF...
          </div>
        }
        error={
          <div className="text-[12px] text-(--color-status-red) py-12">
            Failed to load PDF: {loadError ?? "unknown error"}
          </div>
        }
        className="flex flex-col items-center gap-3"
      >
        {numPages
          ? Array.from({ length: numPages }, (_, i) => (
              <div
                key={i}
                className="surface-linear-card overflow-hidden"
                style={{ boxShadow: "var(--shadow-card)" }}
              >
                <Page
                  pageNumber={i + 1}
                  width={720}
                  renderAnnotationLayer={false}
                  renderTextLayer
                />
              </div>
            ))
          : null}
      </Document>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sections (markdown) tab
// ---------------------------------------------------------------------------

function SectionsTab({
  sections,
  sectionRefs,
  activeId,
  onActivate,
}: {
  sections: PaperSection[];
  sectionRefs: React.RefObject<Record<string, HTMLElement | null>>;
  activeId: string | null;
  onActivate: (id: string) => void;
}) {
  return (
    <div className="px-5 py-4 space-y-2">
      {sections.map((s) => {
        const isActive = s.id === activeId;
        return (
          <details
            key={s.id}
            ref={(el) => {
              sectionRefs.current[s.id] = el;
            }}
            open={isActive || s.status === "compiled" || s.status === "warning"}
            onToggle={(e) => {
              if ((e.currentTarget as HTMLDetailsElement).open) onActivate(s.id);
            }}
            className={cn(
              "group rounded-[8px] border overflow-hidden",
              "bg-(--color-bg-card) border-(--color-border-card)",
              isActive && "ring-1 ring-(--color-brand-interactive)/40",
            )}
          >
            <summary
              className={cn(
                "flex items-center gap-2 px-3 h-9 cursor-pointer list-none select-none",
                "text-[13px] font-medium text-(--color-text-primary-strong)",
                "[&::-webkit-details-marker]:hidden",
              )}
            >
              <ChevronDown
                size={14}
                strokeWidth={1.75}
                className="text-(--color-text-tertiary-spec) transition-transform group-open:rotate-0 -rotate-90"
              />
              <StatusDotInline status={s.status} />
              <span>{s.name}</span>
              <span className="ml-auto text-[11px] text-(--color-text-tertiary-spec)">
                {STATUS_LABEL[s.status]}
              </span>
            </summary>

            <div className="px-4 py-3 hairline-t text-[13px] leading-[1.65] text-(--color-text-secondary)">
              {s.markdown ? (
                <SimpleMarkdown source={s.markdown} />
              ) : (
                <p className="text-(--color-text-tertiary-spec) italic">
                  {s.status === "pending"
                    ? "Section not yet generated."
                    : "No markdown preview available."}
                </p>
              )}
              {s.errorMessage && (
                <div className="mt-3 flex items-start gap-2 px-3 py-2 rounded-[6px] bg-(--color-status-red)/8 border border-(--color-status-red)/30 text-[12px] text-(--color-status-red-spec)">
                  <AlertTriangle size={12} strokeWidth={1.75} className="mt-0.5 flex-none" />
                  <span className="font-mono">{s.errorMessage}</span>
                </div>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}

/**
 * Lightweight markdown renderer — no dependency, just enough to look right
 * in the demo. Phase 3 will swap this for `react-markdown`.
 */
function SimpleMarkdown({ source }: { source: string }) {
  const blocks = source.split(/\n\n+/);
  return (
    <div className="space-y-2.5">
      {blocks.map((b, i) => (
        <p key={i} className="whitespace-pre-wrap">
          {b.split(/(`[^`]+`)/g).map((chunk, j) =>
            chunk.startsWith("`") && chunk.endsWith("`") ? (
              <code
                key={j}
                className="font-mono text-[12px] px-1 py-[1px] rounded-[3px] bg-(--color-ghost-bg-hover) text-(--color-text-primary-strong)"
              >
                {chunk.slice(1, -1)}
              </code>
            ) : (
              <React.Fragment key={j}>{chunk}</React.Fragment>
            ),
          )}
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LaTeX source tab
// ---------------------------------------------------------------------------

function LatexTab({
  sections,
  sectionRefs,
  activeId,
  onActivate,
}: {
  sections: PaperSection[];
  sectionRefs: React.RefObject<Record<string, HTMLElement | null>>;
  activeId: string | null;
  onActivate: (id: string) => void;
}) {
  return (
    <div className="px-5 py-4 space-y-3">
      {sections.map((s) => {
        const isActive = s.id === activeId;
        return (
          <section
            key={s.id}
            ref={(el) => {
              sectionRefs.current[s.id] = el;
            }}
            onMouseEnter={() => onActivate(s.id)}
            className={cn(
              "rounded-[8px] border overflow-hidden",
              "bg-(--color-bg-card) border-(--color-border-card)",
              isActive && "ring-1 ring-(--color-brand-interactive)/40",
            )}
          >
            <header className="flex items-center gap-2 px-3 h-9 hairline-b">
              <StatusDotInline status={s.status} />
              <span className="text-[12.5px] font-medium text-(--color-text-primary-strong)">
                {s.name}
              </span>
              <span className="ml-auto text-[10.5px] font-mono text-(--color-text-tertiary-spec)">
                {s.id}.tex
              </span>
            </header>
            <pre
              className="px-4 py-3 overflow-auto text-[12px] leading-[1.65] text-(--color-text-secondary)"
              style={{
                fontFamily: "var(--font-mono)",
                tabSize: 2,
              }}
            >
              <code>
                {s.tex ??
                  (s.status === "pending"
                    ? "% Section not yet generated.\n"
                    : "% No LaTeX source available.\n")}
              </code>
            </pre>
            {s.errorMessage && (
              <div className="px-3 py-2 hairline-t flex items-start gap-2 text-[11.5px] text-(--color-status-red-spec) bg-(--color-status-red)/5">
                <AlertTriangle size={12} strokeWidth={1.75} className="mt-0.5 flex-none" />
                <span className="font-mono">{s.errorMessage}</span>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Failure tray
// ---------------------------------------------------------------------------

function FailureTray({
  section,
  totalFailed,
  onAutoFix,
  onManualFix,
  onSkip,
}: {
  section: PaperSection;
  totalFailed: number;
  onAutoFix: () => void;
  onManualFix: () => void;
  onSkip: () => void;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 hairline-t bg-(--color-status-red)/8">
      <AlertTriangle
        size={14}
        strokeWidth={1.75}
        className="text-(--color-status-red-spec) flex-none"
      />
      <div className="flex-1 min-w-0 text-[12.5px]">
        <span className="text-(--color-text-primary-strong) font-medium">
          {section.name}
        </span>
        <span className="text-(--color-text-tertiary-spec)"> failed to compile</span>
        {totalFailed > 1 && (
          <span className="text-(--color-text-tertiary-spec)">
            {" "}
            (+{totalFailed - 1} more)
          </span>
        )}
        {section.errorMessage && (
          <span className="ml-2 font-mono text-[11.5px] text-(--color-status-red-spec)/90 truncate">
            {section.errorMessage}
          </span>
        )}
      </div>
      <div className="flex items-center gap-1.5 flex-none">
        <TrayButton onClick={onAutoFix} icon={<Wrench size={12} strokeWidth={1.75} />}>
          Auto-fix
        </TrayButton>
        <TrayButton onClick={onManualFix} icon={<FileCode size={12} strokeWidth={1.75} />}>
          Manual fix
        </TrayButton>
        <TrayButton onClick={onSkip} icon={<SkipForward size={12} strokeWidth={1.75} />}>
          Skip section
        </TrayButton>
      </div>
    </div>
  );
}

function TrayButton({
  onClick,
  icon,
  children,
}: {
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[6px]",
        "text-[12px] font-medium",
        "glass-button",
      )}
    >
      {icon}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Shared bits
// ---------------------------------------------------------------------------

function StatusDotInline({ status }: { status: PaperSectionStatus }) {
  return (
    <span
      aria-hidden
      className="block rounded-full flex-none"
      style={{
        width: 8,
        height: 8,
        background: STATUS_COLOR[status],
        boxShadow: `0 0 0 2px var(--color-bg-card)`,
      }}
    />
  );
}

function Placeholder({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center px-6">
      <div className="text-(--color-text-quaternary-spec)">{icon}</div>
      <div className="text-[13px] font-medium text-(--color-text-primary-strong)">
        {title}
      </div>
      <p className="text-[12px] text-(--color-text-tertiary-spec) max-w-sm leading-[1.6]">
        {body}
      </p>
    </div>
  );
}
