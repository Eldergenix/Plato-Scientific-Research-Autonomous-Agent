"use client";

import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown, FolderPlus, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Journal, Project } from "@/lib/types";

/* -----------------------------------------------------------------------------
 * Types
 * ---------------------------------------------------------------------------*/

export interface CreateProjectModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (project: Project) => void;
}

interface Template {
  id: string;
  label: string;
  description: string;
}

/* -----------------------------------------------------------------------------
 * Constants
 * ---------------------------------------------------------------------------*/

const TEMPLATES: ReadonlyArray<Template> = [
  {
    id: "astro-gw",
    label: "Astro / GW data",
    description:
      "Strain time series from LIGO/Virgo/KAGRA detectors (HDF5).\nSampling rate: 16384 Hz. Channels: H1, L1, V1.\nGoal: characterise post-merger ringdown spectra and quasi-normal modes.",
  },
  {
    id: "tabular-ml",
    label: "Tabular ML",
    description:
      "Tabular dataset (CSV) with ~120k rows and 47 features.\nTarget: binary classification of customer churn.\nGoal: train a calibrated model and surface the most predictive features.",
  },
  {
    id: "biology-omics",
    label: "Biology omics",
    description:
      "Single-cell RNA-seq counts (10x Genomics, ~50k cells, ~20k genes).\nMetadata: tissue, donor, condition.\nGoal: identify differentially expressed genes between conditions.",
  },
];

const JOURNALS: ReadonlyArray<{ id: Journal; label: string }> = [
  { id: "NONE", label: "No journal target" },
  { id: "AAS", label: "AAS" },
  { id: "APS", label: "APS" },
  { id: "ICML", label: "ICML" },
  { id: "JHEP", label: "JHEP" },
  { id: "NeurIPS", label: "NeurIPS" },
  { id: "PASJ", label: "PASJ" },
];

/* -----------------------------------------------------------------------------
 * Subcomponents
 * ---------------------------------------------------------------------------*/

function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block size-3 animate-spin rounded-full border-[1.5px] border-white/40 border-t-white"
    />
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[12px] font-medium text-(--color-text-secondary-spec)">
      {children}
    </label>
  );
}

function TemplateCard({
  template,
  active,
  onSelect,
}: {
  template: Template;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex flex-col items-start gap-1 rounded-[6px] border px-2.5 py-2 text-left transition-colors",
        "min-h-[44px] flex-1 basis-0",
        active
          ? "border-(--color-brand-indigo) bg-(--color-brand-indigo)/10"
          : "border-[#262628] bg-[#141415] hover:border-[#34343a]",
      )}
    >
      <span className="flex items-center gap-1.5 text-[12px] font-medium text-(--color-text-primary)">
        <Sparkles size={11} strokeWidth={1.75} className="text-(--color-brand-hover)" />
        {template.label}
      </span>
      <span className="line-clamp-1 text-[11px] text-(--color-text-tertiary-spec)">
        {template.description.split("\n")[0]}
      </span>
    </button>
  );
}

function JournalSelect({
  value,
  onChange,
  disabled,
}: {
  value: Journal;
  onChange: (v: Journal) => void;
  disabled?: boolean;
}) {
  const current = JOURNALS.find((j) => j.id === value) ?? JOURNALS[0];
  return (
    <Select.Root value={value} onValueChange={(v) => onChange(v as Journal)} disabled={disabled}>
      <Select.Trigger
        className={cn(
          "inline-flex w-full items-center justify-between gap-2 rounded-[6px] border border-[#262628] bg-[#141415] px-2.5",
          "h-8 text-[13px] font-medium text-(--color-text-primary)",
          "hover:border-[#34343a] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
          "disabled:opacity-50",
        )}
        aria-label="Journal target"
      >
        <Select.Value>{current.label}</Select.Value>
        <Select.Icon>
          <ChevronDown size={12} strokeWidth={1.75} className="text-(--color-text-tertiary-spec)" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={4}
          className={cn(
            "z-[60] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-[8px]",
            "border border-(--color-border-card) bg-(--color-bg-card) shadow-[var(--shadow-dialog)]",
          )}
        >
          <Select.Viewport className="p-1">
            {JOURNALS.map((j) => (
              <Select.Item
                key={j.id}
                value={j.id}
                className={cn(
                  "relative flex h-7 cursor-pointer items-center gap-2 rounded-[4px] pl-6 pr-2",
                  "text-[13px] text-(--color-text-secondary-spec)",
                  "data-[highlighted]:bg-(--color-ghost-bg-hover) data-[highlighted]:text-(--color-text-primary)",
                  "data-[highlighted]:outline-none",
                )}
              >
                <Select.ItemIndicator className="absolute left-1.5 inline-flex items-center">
                  <Check size={12} strokeWidth={2} className="text-(--color-brand-hover)" />
                </Select.ItemIndicator>
                <Select.ItemText>{j.label}</Select.ItemText>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}

/* -----------------------------------------------------------------------------
 * CreateProjectModal
 * ---------------------------------------------------------------------------*/

export function CreateProjectModal({
  open,
  onOpenChange,
  onCreated,
}: CreateProjectModalProps) {
  const [name, setName] = React.useState("");
  const [dataDescription, setDataDescription] = React.useState("");
  const [journal, setJournal] = React.useState<Journal>("NONE");
  const [activeTemplate, setActiveTemplate] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Reset state when the modal closes.
  React.useEffect(() => {
    if (!open) {
      setName("");
      setDataDescription("");
      setJournal("NONE");
      setActiveTemplate(null);
      setSubmitting(false);
      setError(null);
    }
  }, [open]);

  const canSubmit = name.trim().length > 0 && !submitting;

  const handleApplyTemplate = (template: Template) => {
    setActiveTemplate(template.id);
    setDataDescription(template.description);
  };

  const handleSubmit = async (
    e?: React.SyntheticEvent<HTMLFormElement>,
  ) => {
    e?.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const project = await api.createProject(
        name.trim(),
        dataDescription.trim() || undefined,
      );
      onCreated(project);
      onOpenChange(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to create project";
      setError(msg);
      setSubmitting(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=open]:fade-in-0"
        />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[560px] -translate-x-1/2 -translate-y-1/2",
            "surface-linear-card overflow-hidden",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          )}
          onPointerDownOutside={(e) => {
            if (submitting) e.preventDefault();
          }}
          onEscapeKeyDown={(e) => {
            if (submitting) e.preventDefault();
          }}
        >
          {/* Header */}
          <div className="flex h-11 items-center justify-between gap-2 border-b border-[#1D1D1F] px-4">
            <Dialog.Title className="flex items-center gap-2 text-[15px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
              <FolderPlus size={14} strokeWidth={1.75} className="text-(--color-brand-hover)" />
              New project
            </Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              disabled={submitting}
              className={cn(
                "inline-flex size-7 items-center justify-center rounded-full text-(--color-text-tertiary-spec)",
                "transition-colors hover:bg-white/5 hover:text-(--color-text-primary)",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
                "disabled:opacity-40",
              )}
            >
              <X size={14} strokeWidth={1.75} />
            </Dialog.Close>
          </div>

          <form onSubmit={handleSubmit}>
            {/* Body */}
            <div className="flex flex-col gap-4 p-4">
              {/* Name field */}
              <div className="flex flex-col gap-1.5">
                <FieldLabel>Project name</FieldLabel>
                <input
                  autoFocus
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={submitting}
                  placeholder="e.g. GW231123 ringdown analysis"
                  className={cn(
                    "h-8 rounded-[6px] border border-[#262628] bg-[#141415] px-2.5",
                    "text-[13px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary-spec)",
                    "transition-colors hover:border-[#34343a]",
                    "focus-visible:border-(--color-brand-indigo) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-indigo)",
                    "disabled:opacity-50",
                  )}
                />
              </div>

              {/* Description field */}
              <div className="flex flex-col gap-1.5">
                <FieldLabel>Data description (optional)</FieldLabel>
                <textarea
                  value={dataDescription}
                  onChange={(e) => {
                    setDataDescription(e.target.value);
                    setActiveTemplate(null);
                  }}
                  disabled={submitting}
                  rows={5}
                  placeholder={
                    "Describe your data, format, and goals.\nExample:\nHDF5 strain files at 16384 Hz from H1, L1, V1.\nGoal: estimate ringdown QNM frequencies."
                  }
                  className={cn(
                    "min-h-[120px] resize-y rounded-[6px] border border-[#262628] bg-[#141415] px-2.5 py-2",
                    "text-[13px] leading-[1.5] text-(--color-text-primary) placeholder:text-(--color-text-quaternary-spec)",
                    "transition-colors hover:border-[#34343a]",
                    "focus-visible:border-(--color-brand-indigo) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-indigo)",
                    "disabled:opacity-50",
                  )}
                />
              </div>

              {/* Templates row */}
              <div className="flex flex-col gap-1.5">
                <FieldLabel>Starter templates</FieldLabel>
                <div className="flex items-stretch gap-1.5">
                  {TEMPLATES.map((t) => (
                    <TemplateCard
                      key={t.id}
                      template={t}
                      active={activeTemplate === t.id}
                      onSelect={() => handleApplyTemplate(t)}
                    />
                  ))}
                </div>
              </div>

              {/* Journal field */}
              <div className="flex flex-col gap-1.5">
                <FieldLabel>Journal target (optional)</FieldLabel>
                <JournalSelect
                  value={journal}
                  onChange={setJournal}
                  disabled={submitting}
                />
              </div>

              {error ? (
                <div className="rounded-[6px] border border-(--color-status-red)/30 bg-(--color-status-red)/10 px-2.5 py-1.5 text-[12px] text-(--color-status-red)">
                  {error}
                </div>
              ) : null}
            </div>

            {/* Footer */}
            <div className="hairline-t flex items-center justify-end gap-1.5 px-4 py-3">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={submitting}
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                disabled={!canSubmit}
              >
                {submitting ? <Spinner /> : null}
                {submitting ? "Creating..." : "Create project"}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
