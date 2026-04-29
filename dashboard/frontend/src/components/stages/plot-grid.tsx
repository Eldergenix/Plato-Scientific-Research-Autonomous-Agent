"use client";

import * as React from "react";
import Image from "next/image";
import {
  Image as ImageIcon,
  ImageOff,
  Edit3,
  Download,
  X,
  Trash2,
  MoreHorizontal,
} from "lucide-react";
import { cn, formatRelativeTime } from "@/lib/utils";

export interface PlotItem {
  name: string;
  url: string;
  caption?: string;
  createdAt?: string;
  generatingStep?: number;
}

export interface PlotGridProps {
  plots: PlotItem[];
  onReorder?: (reorderedNames: string[]) => void;
  onCaptionEdit?: (name: string, caption: string) => void;
  onOpenInEditor?: (name: string) => void;
  onDelete?: (name: string) => void;
}

type DropPosition = { index: number; before: boolean } | null;

export function PlotGrid({
  plots,
  onReorder,
  onCaptionEdit,
  onOpenInEditor,
  onDelete,
}: PlotGridProps) {
  const [lightboxIndex, setLightboxIndex] = React.useState<number | null>(null);
  const [dragIndex, setDragIndex] = React.useState<number | null>(null);
  const [dropTarget, setDropTarget] = React.useState<DropPosition>(null);

  // Editable captions: tracks which card is in edit mode + draft text.
  const [editing, setEditing] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState<string>("");

  const handleDragStart = (e: React.DragEvent<HTMLDivElement>, index: number) => {
    if (!onReorder) return;
    setDragIndex(index);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(index));
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>, index: number) => {
    if (dragIndex === null) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
    const before = e.clientX < rect.left + rect.width / 2;
    setDropTarget({ index, before });
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (dragIndex === null || dropTarget === null || !onReorder) {
      setDragIndex(null);
      setDropTarget(null);
      return;
    }
    const ordered = plots.map((p) => p.name);
    const [moved] = ordered.splice(dragIndex, 1);
    let target = dropTarget.index + (dropTarget.before ? 0 : 1);
    if (dragIndex < target) target -= 1;
    ordered.splice(target, 0, moved);
    onReorder(ordered);
    setDragIndex(null);
    setDropTarget(null);
  };

  const handleDragEnd = () => {
    setDragIndex(null);
    setDropTarget(null);
  };

  const startEditing = (name: string, current: string | undefined) => {
    setEditing(name);
    setDraft(current ?? "");
  };
  const commitEdit = (name: string) => {
    onCaptionEdit?.(name, draft);
    setEditing(null);
  };

  // ESC closes lightbox
  React.useEffect(() => {
    if (lightboxIndex === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightboxIndex(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightboxIndex]);

  if (plots.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
        <div className="size-12 rounded-full bg-(--color-ghost-bg) flex items-center justify-center mb-3">
          <ImageOff size={20} strokeWidth={1.4} className="text-(--color-text-quaternary)" />
        </div>
        <p className="text-[13px] text-(--color-text-secondary) font-medium">No plots yet</p>
        <p className="text-[12px] text-(--color-text-tertiary) mt-1">
          Run <code className="font-mono text-(--color-text-secondary)">get_results</code> to generate plots
        </p>
      </div>
    );
  }

  return (
    <>
      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}
        onDragEnd={handleDragEnd}
      >
        {plots.map((plot, index) => {
          const isDragging = dragIndex === index;
          const showIndicatorBefore =
            dropTarget?.index === index && dropTarget.before && dragIndex !== null;
          const showIndicatorAfter =
            dropTarget?.index === index && !dropTarget.before && dragIndex !== null;
          const isEditing = editing === plot.name;

          return (
            <div key={plot.name} className="relative">
              {showIndicatorBefore && <DropIndicator side="left" />}
              <div
                draggable={!!onReorder && !isEditing}
                onDragStart={(e) => handleDragStart(e, index)}
                onDragOver={(e) => handleDragOver(e, index)}
                onDrop={handleDrop}
                className={cn(
                  "group relative overflow-hidden rounded-[8px] border bg-(--color-bg-card) transition-opacity",
                  "border-(--color-border-card)",
                  isDragging && "opacity-40",
                )}
              >
                {/* Image */}
                <button
                  type="button"
                  onClick={() => setLightboxIndex(index)}
                  className="block w-full relative bg-(--color-bg-surface) cursor-zoom-in"
                  style={{ height: 180 }}
                  aria-label={`Open ${plot.name}`}
                >
                  <PlotImage url={plot.url} name={plot.name} />
                </button>

                {/* Hover actions */}
                <div className="pointer-events-none absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  <ActionChip
                    label="Download"
                    onClick={() => {
                      const a = document.createElement("a");
                      a.href = plot.url;
                      a.download = plot.name;
                      a.click();
                    }}
                  >
                    <Download size={12} strokeWidth={1.6} />
                  </ActionChip>
                  {onOpenInEditor && (
                    <ActionChip label="Open in editor" onClick={() => onOpenInEditor(plot.name)}>
                      <MoreHorizontal size={12} strokeWidth={1.6} />
                    </ActionChip>
                  )}
                  {onDelete && (
                    <ActionChip
                      label="Delete"
                      tone="danger"
                      onClick={() => {
                        if (confirm(`Delete ${plot.name}?`)) onDelete(plot.name);
                      }}
                    >
                      <Trash2 size={12} strokeWidth={1.6} />
                    </ActionChip>
                  )}
                </div>

                {/* Caption row */}
                <div className="px-3 py-2 hairline-t flex items-center gap-2 min-h-[36px]">
                  {isEditing ? (
                    <input
                      autoFocus
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onBlur={() => commitEdit(plot.name)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitEdit(plot.name);
                        else if (e.key === "Escape") setEditing(null);
                      }}
                      className="flex-1 min-w-0 bg-(--color-ghost-bg-hover) text-[12px] text-(--color-text-primary) rounded-[4px] px-1.5 py-0.5 outline-none border border-(--color-border-strong) focus:border-(--color-brand-interactive)"
                      placeholder="Add a caption…"
                    />
                  ) : (
                    <button
                      type="button"
                      onClick={() => onCaptionEdit && startEditing(plot.name, plot.caption)}
                      className={cn(
                        "flex-1 min-w-0 text-left text-[12px] truncate transition-colors",
                        plot.caption
                          ? "text-(--color-text-secondary)"
                          : "text-(--color-text-quaternary) italic",
                        onCaptionEdit && "hover:text-(--color-text-primary) cursor-text",
                      )}
                      title={plot.caption ?? "Add a caption"}
                    >
                      {plot.caption || "Add a caption…"}
                      {onCaptionEdit && (
                        <Edit3
                          size={10}
                          strokeWidth={1.5}
                          className="inline ml-1.5 text-(--color-text-quaternary) opacity-0 group-hover:opacity-100"
                        />
                      )}
                    </button>
                  )}
                  <span
                    className="ml-auto shrink-0 text-right font-mono"
                    style={{ fontSize: "10.5px", color: "#949496" }}
                  >
                    {plot.name}
                  </span>
                </div>
              </div>
              {showIndicatorAfter && <DropIndicator side="right" />}
            </div>
          );
        })}
      </div>

      {/* Lightbox */}
      {lightboxIndex !== null && plots[lightboxIndex] && (
        <Lightbox plot={plots[lightboxIndex]} onClose={() => setLightboxIndex(null)} />
      )}
    </>
  );
}

function PlotImage({ url, name }: { url: string; name: string }) {
  const [errored, setErrored] = React.useState(false);
  if (errored) {
    return (
      <div className="absolute inset-0 flex items-center justify-center">
        <ImageIcon size={28} strokeWidth={1.25} className="text-(--color-text-quaternary) opacity-50" />
      </div>
    );
  }
  return (
    <Image
      src={url}
      alt={name}
      fill
      unoptimized
      sizes="(max-width: 640px) 100vw, 320px"
      className="object-cover"
      onError={() => setErrored(true)}
    />
  );
}

function ActionChip({
  children,
  onClick,
  label,
  tone = "default",
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
  tone?: "default" | "danger";
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={cn(
        "pointer-events-auto inline-flex size-6 items-center justify-center rounded-full",
        "bg-(--color-bg-button-glass) shadow-(--shadow-icon-button) transition-colors",
        tone === "danger"
          ? "text-(--color-status-red) hover:bg-(--color-status-red)/15"
          : "text-(--color-text-tertiary) hover:text-(--color-text-primary) hover:bg-(--color-ghost-bg-hover)",
      )}
    >
      {children}
    </button>
  );
}

function DropIndicator({ side }: { side: "left" | "right" }) {
  return (
    <span
      aria-hidden
      className="absolute inset-y-0 w-0.5 rounded-full pointer-events-none"
      style={{
        [side]: "-6px",
        borderLeft: "2px dashed var(--color-brand-interactive)",
      } as React.CSSProperties}
    />
  );
}

function Lightbox({ plot, onClose }: { plot: PlotItem; onClose: () => void }) {
  const [imgError, setImgError] = React.useState(false);
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={plot.caption ?? plot.name}
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-6"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative grid max-h-[90vh] w-full max-w-6xl grid-cols-[1fr_280px] overflow-hidden rounded-[12px] border border-(--color-border-card) bg-(--color-bg-card) shadow-(--shadow-dialog)"
      >
        <div className="relative flex items-center justify-center bg-(--color-bg-page) overflow-hidden">
          {imgError ? (
            <ImageIcon size={48} strokeWidth={1.25} className="text-(--color-text-quaternary) opacity-50" />
          ) : (
            <Image
              src={plot.url}
              alt={plot.name}
              width={1200}
              height={900}
              unoptimized
              className="max-h-[90vh] w-auto h-auto object-contain"
              onError={() => setImgError(true)}
            />
          )}
        </div>
        <aside className="hairline-l bg-(--color-bg-marketing) p-4 overflow-auto">
          <div className="flex items-center justify-between">
            <h3 className="font-label">Plot</h3>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="inline-flex size-7 items-center justify-center rounded-full text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)"
            >
              <X size={14} strokeWidth={1.6} />
            </button>
          </div>
          <dl className="mt-3 space-y-2.5 text-[12px]">
            <Meta label="Caption" value={plot.caption || "—"} />
            <Meta label="Filename" value={plot.name} mono />
            {plot.generatingStep !== undefined && (
              <Meta label="Step" value={`#${plot.generatingStep}`} mono />
            )}
            {plot.createdAt && <Meta label="Created" value={formatRelativeTime(plot.createdAt)} />}
            <Meta label="URL" value={plot.url} mono truncate />
          </dl>
          <a
            href={plot.url}
            download={plot.name}
            className="mt-4 inline-flex items-center gap-1.5 rounded-[6px] border border-(--color-border-solid) bg-(--color-ghost-bg) px-2.5 py-1.5 text-[12px] text-(--color-text-secondary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)"
          >
            <Download size={12} strokeWidth={1.6} />
            Download
          </a>
        </aside>
      </div>
    </div>
  );
}

function Meta({
  label,
  value,
  mono,
  truncate,
}: {
  label: string;
  value: string;
  mono?: boolean;
  truncate?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-[11px] uppercase tracking-wider text-(--color-text-quaternary) font-medium pt-px">
        {label}
      </dt>
      <dd
        className={cn(
          "text-right text-(--color-text-primary)",
          mono && "font-mono text-[11.5px]",
          truncate && "truncate max-w-[180px]",
        )}
        title={truncate ? value : undefined}
      >
        {value}
      </dd>
    </div>
  );
}
