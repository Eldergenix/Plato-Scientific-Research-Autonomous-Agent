"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { FolderPlus, Plus, Search, Sparkles } from "lucide-react";
import { TabPills } from "@/components/shell/tab-pills";
import { StatusIcon } from "@/components/views/status-icon";
import { CreateProjectModal } from "@/components/projects/create-project-modal";
import { api } from "@/lib/api";
import {
  cn,
  formatCost,
  formatRelativeTime,
  formatTokens,
} from "@/lib/utils";
import type { Project, StageStatus } from "@/lib/types";

/* -----------------------------------------------------------------------------
 * Types
 * ---------------------------------------------------------------------------*/

type FilterTab = "all" | "active" | "completed";

const TABS: ReadonlyArray<{ id: FilterTab; label: string }> = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "completed", label: "Completed" },
] as const;

/* -----------------------------------------------------------------------------
 * Helpers
 * ---------------------------------------------------------------------------*/

/**
 * djb2-style string hash → 32-bit unsigned int. Used to pick a deterministic
 * avatar palette entry per project name.
 */
function hashString(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

/** 8-color avatar palette tuned to the Linear-dark surface. */
const AVATAR_PALETTE: ReadonlyArray<{ bg: string; fg: string }> = [
  { bg: "#5E6AD2", fg: "#F2F3FF" }, // indigo
  { bg: "#2A6F6A", fg: "#E6F8F5" }, // teal
  { bg: "#10A37F", fg: "#E7FFF7" }, // green
  { bg: "#EB5757", fg: "#FFEAEA" }, // red
  { bg: "#F0BF00", fg: "#1A1500" }, // amber
  { bg: "#BB87FC", fg: "#1B1124" }, // purple
  { bg: "#4EA7FC", fg: "#0B1B33" }, // blue
  { bg: "#FF7236", fg: "#1F0F08" }, // orange
];

function avatarFor(name: string) {
  const idx = hashString(name) % AVATAR_PALETTE.length;
  return {
    ...AVATAR_PALETTE[idx],
    letter: (name.trim()[0] ?? "·").toUpperCase(),
  };
}

/** Aggregate a project's stage statuses into a single rollup status. */
function rollupStatus(project: Project): StageStatus {
  const stages = Object.values(project.stages);
  if (project.activeRun) return "running";
  if (stages.some((s) => s.status === "running")) return "running";
  if (stages.some((s) => s.status === "failed")) return "failed";
  if (stages.length > 0 && stages.every((s) => s.status === "done")) return "done";
  return "empty";
}

function doneCount(project: Project): number {
  return Object.values(project.stages).filter((s) => s.status === "done").length;
}

function totalStageCount(project: Project): number {
  return Object.values(project.stages).length;
}

/* -----------------------------------------------------------------------------
 * Subcomponents
 * ---------------------------------------------------------------------------*/

function Avatar({ name }: { name: string }) {
  const av = avatarFor(name);
  return (
    <span
      className="flex size-[20px] flex-none items-center justify-center rounded-full text-[10px] font-medium"
      style={{ backgroundColor: av.bg, color: av.fg }}
      aria-label={`avatar ${name}`}
    >
      {av.letter}
    </span>
  );
}

function MetaPill({ children }: { children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex h-[22px] flex-none items-center rounded-full border border-[#262628] bg-[#0f1010]",
        "px-2 font-mono text-[11px] font-medium tabular-nums text-(--color-text-row-meta)",
      )}
    >
      {children}
    </span>
  );
}

function ProjectRow({
  project,
  onSelect,
}: {
  project: Project;
  onSelect: () => void;
}) {
  const status = rollupStatus(project);
  const done = doneCount(project);
  const total = totalStageCount(project);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className={cn(
        "group flex h-12 cursor-pointer items-center gap-2 px-4",
        "border-b border-[#141416]/60 transition-colors",
        "hover:bg-[rgba(255,255,255,0.02)]",
      )}
      data-project-id={project.id}
    >
      <StatusIcon status={status} />

      <span
        className="truncate text-[13px] font-medium text-(--color-text-row-title)"
        style={{ letterSpacing: "-0.01em" }}
      >
        {project.name}
      </span>

      <span className="flex-none text-[12px] text-(--color-text-quaternary-spec)" aria-hidden>
        ·
      </span>

      <span className="flex-none truncate text-[12px] text-(--color-text-row-meta)">
        {done}/{total} stages done
      </span>

      <span className="ml-auto flex flex-none items-center gap-1.5">
        <MetaPill>{formatTokens(project.totalTokens)} tok</MetaPill>
        <MetaPill>{formatCost(project.totalCostCents)}</MetaPill>
        <Avatar name={project.name} />
        <span
          className="w-[60px] flex-none text-right text-[12px] font-medium text-(--color-text-row-meta)"
          title={project.updatedAt}
        >
          {formatRelativeTime(project.updatedAt)}
        </span>
      </span>
    </div>
  );
}

function GroupHeader({ label, count }: { label: string; count: number }) {
  return (
    <header
      className="flex h-9 items-center gap-2 px-4"
      style={{ background: "linear-gradient(90deg, #161b19 0%, #171718 100%)" }}
    >
      <span className="text-[13px] font-medium text-(--color-text-secondary-spec)">
        {label}
      </span>
      <span className="text-[13px] font-medium text-(--color-text-progress-meta)">
        {count}
      </span>
    </header>
  );
}

function NewProjectButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-full px-3",
        "bg-(--color-brand-indigo) text-[12px] font-medium leading-none text-white",
        "shadow-[var(--shadow-elevated)] transition-colors duration-100",
        "hover:bg-(--color-brand-interactive)",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
        "focus-visible:ring-offset-2 focus-visible:ring-offset-(--color-bg-page)",
      )}
    >
      <Plus size={12} strokeWidth={1.75} />
      New project
    </button>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 py-16 text-center">
      <span
        className="flex size-12 items-center justify-center rounded-[12px] border border-(--color-border-card) bg-(--color-bg-card)"
        aria-hidden
      >
        <Sparkles size={20} strokeWidth={1.5} className="text-(--color-brand-hover)" />
      </span>
      <div className="flex flex-col gap-1">
        <h2 className="text-[15px] font-medium text-(--color-text-primary-strong)">
          No projects yet
        </h2>
        <p className="max-w-[320px] text-[13px] text-(--color-text-row-meta)">
          Spin up a research project — Plato will guide you from data to a peer-reviewed draft.
        </p>
      </div>
      <button
        type="button"
        onClick={onCreate}
        className={cn(
          "mt-2 inline-flex h-8 items-center gap-1.5 rounded-full px-3.5",
          "bg-(--color-brand-indigo) text-[13px] font-medium text-white",
          "shadow-[var(--shadow-elevated)] transition-colors hover:bg-(--color-brand-interactive)",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
        )}
      >
        <FolderPlus size={13} strokeWidth={1.75} />
        Create your first project
      </button>
    </div>
  );
}

/* -----------------------------------------------------------------------------
 * Page
 * ---------------------------------------------------------------------------*/

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = React.useState<Project[] | null>(null);
  const [tab, setTab] = React.useState<FilterTab>("all");
  const [query, setQuery] = React.useState("");
  const [modalOpen, setModalOpen] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    api
      .listProjects()
      .then((list) => {
        if (!cancelled) setProjects(list);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load projects");
        setProjects([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = React.useMemo(() => {
    const list = projects ?? [];
    const q = query.trim().toLowerCase();
    return list.filter((p) => {
      if (q && !p.name.toLowerCase().includes(q)) return false;
      const status = rollupStatus(p);
      if (tab === "active") return p.activeRun != null || status === "running";
      if (tab === "completed") return status === "done";
      return true;
    });
  }, [projects, query, tab]);

  const groups = React.useMemo(() => {
    const active: Project[] = [];
    const all: Project[] = [];
    for (const p of filtered) {
      if (p.activeRun != null) active.push(p);
      else all.push(p);
    }
    return { active, all };
  }, [filtered]);

  const handleCreated = React.useCallback(
    (project: Project) => {
      setProjects((prev) => (prev ? [project, ...prev] : [project]));
      router.push("/");
    },
    [router],
  );

  const handleSelect = React.useCallback(() => {
    // Today the workspace view lives at "/" and renders the most-recent
    // project; future routing can use `/workspace/[id]`.
    router.push("/");
  }, [router]);

  const isEmpty = projects != null && projects.length === 0;

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-(--color-bg-page) text-(--color-text-primary)">
      {/* Page header strip */}
      <div className="hairline-b flex h-11 flex-none items-center justify-between gap-2 px-4">
        <h1 className="text-[15px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
          Projects
        </h1>
        <NewProjectButton onClick={() => setModalOpen(true)} />
      </div>

      {/* Filter bar */}
      <div className="hairline-b flex h-11 flex-none items-center justify-between gap-2 px-4 py-2">
        <TabPills
          tabs={TABS}
          activeId={tab}
          onSelect={(id) => setTab(id as FilterTab)}
          ariaLabel="Project filter"
        />
        <label className="relative flex items-center">
          <Search
            size={11}
            strokeWidth={1.75}
            className="pointer-events-none absolute left-2 text-(--color-text-tertiary-spec)"
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search projects"
            className={cn(
              "h-6 w-[200px] rounded-[6px] border border-[#262628] bg-[#141415] pl-6 pr-2",
              "font-mono text-[12px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary-spec)",
              "transition-colors hover:border-[#34343a]",
              "focus-visible:border-(--color-brand-indigo) focus-visible:outline-none",
            )}
          />
        </label>
      </div>

      {/* Body */}
      <div className="flex flex-1 min-h-0 flex-col overflow-y-auto">
        {error ? (
          <div className="hairline-b bg-(--color-status-red)/10 px-4 py-2 text-[12px] text-(--color-status-red)">
            {error}
          </div>
        ) : null}

        {projects == null ? (
          <div className="flex flex-1 items-center justify-center text-[13px] text-(--color-text-row-meta)">
            Loading projects...
          </div>
        ) : isEmpty ? (
          <EmptyState onCreate={() => setModalOpen(true)} />
        ) : filtered.length === 0 ? (
          <div className="flex flex-1 items-center justify-center text-[13px] text-(--color-text-row-meta)">
            No projects match your filters.
          </div>
        ) : (
          <div className="flex flex-col">
            {groups.active.length > 0 ? (
              <section>
                <GroupHeader label="Active" count={groups.active.length} />
                <div className="flex flex-col">
                  {groups.active.map((p) => (
                    <ProjectRow key={p.id} project={p} onSelect={handleSelect} />
                  ))}
                </div>
              </section>
            ) : null}

            {groups.all.length > 0 ? (
              <section>
                <GroupHeader label="All projects" count={groups.all.length} />
                <div className="flex flex-col">
                  {groups.all.map((p) => (
                    <ProjectRow key={p.id} project={p} onSelect={handleSelect} />
                  ))}
                </div>
              </section>
            ) : null}
          </div>
        )}
      </div>

      <CreateProjectModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        onCreated={handleCreated}
      />
    </div>
  );
}
