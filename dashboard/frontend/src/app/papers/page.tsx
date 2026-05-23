"use client";

import * as React from "react";
import Link from "next/link";
import {
  Activity,
  AtSign,
  BarChart3,
  BookOpen,
  CalendarDays,
  CheckCircle2,
  Database,
  FileText,
  FlaskConical,
  GitBranch,
  Heart,
  LayoutGrid,
  Library,
  MessageCircle,
  Plus,
  RefreshCw,
  Rss,
  Search,
  Send,
  Share2,
  Trash2,
  UserRound,
  Users,
  X,
} from "lucide-react";
import { DashboardShell } from "@/components/shell/dashboard-shell";
import { TabPills } from "@/components/shell/tab-pills";
import Folder from "@/components/ui/folder";
import { Button } from "@/components/ui/button";
import { api, type PaperArtifacts, type RunRecord } from "@/lib/api";
import { dashboardApiBase } from "@/lib/api-base";
import type {
  Project,
  PublicationFeedAuthor,
  PublicationAuthor,
  PublicationSettings,
  PublicationTask,
  PublicationTaskKind,
  PublicationTaskStatus,
  ResearchPublication,
  StageId,
} from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";

const API_BASE = dashboardApiBase();

type FilterId = "all" | "papers" | "data" | "research" | "experiments" | "references";
type ArtifactKind = Exclude<FilterId, "all">;
type ViewMode = "feed" | "library";

interface PlotRecord {
  name: string;
  url: string;
}

interface CitationNode {
  id: string;
  title: string;
  authors?: string[];
  year?: number;
  venue?: string;
  url?: string;
  kind?: string;
}

interface CitationGraphPayload {
  seeds?: CitationNode[];
  expanded?: CitationNode[];
  edges?: Array<Record<string, unknown>>;
  stats?: {
    seed_count?: number;
    expanded_count?: number;
    edge_count?: number;
    duplicates_filtered?: number;
  };
}

interface ProjectLibrary {
  project: Project;
  paper: PaperArtifacts;
  plots: PlotRecord[];
  runs: RunRecord[];
  citations: CitationGraphPayload | null;
}

interface LibraryItem {
  id: string;
  kind: ArtifactKind;
  title: string;
  eyebrow: string;
  description: string;
  meta: string;
  searchText: string;
  href?: string;
}

const FILTERS: Array<{ id: FilterId; label: string }> = [
  { id: "all", label: "All" },
  { id: "papers", label: "Papers" },
  { id: "data", label: "Data" },
  { id: "research", label: "Research" },
  { id: "experiments", label: "Experiments" },
  { id: "references", label: "References" },
];

const VIEW_TABS: Array<{ id: ViewMode; label: string }> = [
  { id: "feed", label: "Feed" },
  { id: "library", label: "Library" },
];

const STAGE_LABELS: Record<StageId, string> = {
  data: "Data",
  idea: "Idea",
  literature: "Literature",
  method: "Method",
  results: "Results",
  paper: "Paper",
  referee: "Referee",
};

const FOLDER_COLORS = ["#5E6AD2", "#10A37F", "var(--color-status-purple)", "#4EA7FC", "#F0BF00", "#FF7236"];
const TASK_KINDS: Array<{ id: PublicationTaskKind; label: string }> = [
  { id: "section", label: "Section" },
  { id: "review", label: "Review" },
  { id: "completion", label: "Completion" },
  { id: "other", label: "Other" },
];
const TASK_STATUSES: Array<{ id: PublicationTaskStatus; label: string }> = [
  { id: "todo", label: "To do" },
  { id: "in_progress", label: "In progress" },
  { id: "blocked", label: "Blocked" },
  { id: "done", label: "Done" },
];

function emptyPublicationSettings(): PublicationSettings {
  return { authors: [], dates: {}, tasks: [] };
}

function searchable(parts: Array<string | number | null | undefined>): string {
  return parts
    .filter((part) => part !== null && part !== undefined)
    .join(" ")
    .toLowerCase();
}

function makeClientId(prefix: string): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}_${crypto.randomUUID().slice(0, 8)}`;
  }
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function toDateInput(value?: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString().slice(0, 10);
}

function fromDateInput(value: string): string | null {
  return value ? `${value}T00:00:00.000Z` : null;
}

function normalizePublicationSettings(settings: PublicationSettings): PublicationSettings {
  return {
    authors: settings.authors
      .map((author, index) => ({
        ...author,
        name: author.name.trim(),
        email: author.email?.trim() || null,
        affiliation: author.affiliation?.trim() || null,
        role: author.role.trim() || "Author",
        order: index,
      }))
      .filter((author) => author.name || author.email || author.affiliation),
    dates: {
      target: settings.dates.target ?? null,
      submitted: settings.dates.submitted ?? null,
      accepted: settings.dates.accepted ?? null,
      published: settings.dates.published ?? null,
    },
    tasks: settings.tasks
      .map((task) => ({
        ...task,
        title: task.title.trim(),
        section: task.section?.trim() || null,
        assignee: task.assignee?.trim() || null,
        assignee_email: task.assignee_email?.trim() || null,
        notes: task.notes?.trim() || null,
        completed_at: task.status === "done" ? task.completed_at ?? new Date().toISOString() : null,
      }))
      .filter((task) => task.title || task.section || task.assignee || task.assignee_email),
  };
}

async function fetchPlots(projectId: string): Promise<PlotRecord[]> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/plots`, {
    credentials: "include",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) return [];
  return (await response.json()) as PlotRecord[];
}

async function fetchCitationGraph(runId: string): Promise<CitationGraphPayload | null> {
  const response = await fetch(`${API_BASE}/runs/${runId}/citation_graph`, {
    credentials: "include",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 404 || !response.ok) return null;
  return (await response.json()) as CitationGraphPayload;
}

function latestRun(runs: RunRecord[], stages: StageId[]): RunRecord | undefined {
  return runs
    .filter((run) => stages.includes(run.stage))
    .sort((a, b) => {
      const aTime = Date.parse(a.finishedAt ?? a.startedAt ?? "");
      const bTime = Date.parse(b.finishedAt ?? b.startedAt ?? "");
      return (Number.isFinite(bTime) ? bTime : 0) - (Number.isFinite(aTime) ? aTime : 0);
    })[0];
}

async function loadProjectLibrary(project: Project): Promise<ProjectLibrary> {
  const shouldLoadPaper =
    project.stages.paper.status === "done" ||
    project.stages.paper.status === "stale";
  const [paper, plots, runs] = await Promise.all([
    shouldLoadPaper
      ? api.getPaperArtifacts(project.id).catch(() => ({ sections: [] }))
      : Promise.resolve({ sections: [] }),
    fetchPlots(project.id).catch(() => []),
    api.listRuns(project.id).catch(() => []),
  ]);
  const citationRun = latestRun(runs, ["literature", "paper", "referee"]);
  const citations = citationRun ? await fetchCitationGraph(citationRun.id).catch(() => null) : null;
  return { project, paper, plots, runs, citations };
}

function citationNodes(graph: CitationGraphPayload | null): CitationNode[] {
  if (!graph) return [];
  const byId = new Map<string, CitationNode>();
  for (const node of [...(graph.seeds ?? []), ...(graph.expanded ?? [])]) {
    byId.set(node.id, node);
  }
  return Array.from(byId.values());
}

function buildItems(entry: ProjectLibrary): LibraryItem[] {
  const { project, paper, plots, runs, citations } = entry;
  const nodes = citationNodes(citations);
  const items: LibraryItem[] = [];
  const resultsRun = latestRun(runs, ["results"]);
  const literatureRun = latestRun(runs, ["literature"]);

  if (paper.pdfUrl || paper.sections.length > 0 || project.stages.paper.status === "done") {
    const sections = paper.sections.length > 0
      ? paper.sections
      : [{ id: "paper", name: "Generated paper", markdown: "", tex: "", status: "compiled" as const }];
    sections.forEach((section, index) => {
      const description =
        section.markdown?.slice(0, 220) ||
        section.tex?.slice(0, 220) ||
        "Compiled manuscript and parsed LaTeX section from the paper stage.";
      items.push({
        id: `${project.id}:paper:${section.id}`,
        kind: "papers",
        title: section.name || `Paper section ${index + 1}`,
        eyebrow: "Paper",
        description,
        meta: paper.pdfUrl ? "PDF available" : section.status,
        href: paper.pdfUrl,
        searchText: searchable([
          project.name,
          "paper manuscript latex pdf",
          section.name,
          section.markdown,
          section.tex,
          section.status,
        ]),
      });
    });
  }

  items.push({
    id: `${project.id}:data`,
    kind: "data",
    title: "Project data package",
    eyebrow: "Data",
    description:
      project.stages.data.progressLabel ||
      "Data stage outputs, source files, tables, and derived materials attached to this project.",
    meta: `${STAGE_LABELS.data}: ${project.stages.data.status}`,
    searchText: searchable([
      project.name,
      "data table dataset source file",
      project.stages.data.status,
      project.stages.data.progressLabel,
      project.stages.data.model,
    ]),
  });

  if (literatureRun || nodes.length > 0) {
    items.push({
      id: `${project.id}:research`,
      kind: "research",
      title: "Research trail",
      eyebrow: "Research",
      description: "Literature, novelty, counter-evidence, and retrieval outputs generated during research runs.",
      meta: literatureRun ? formatRelativeTime(literatureRun.finishedAt ?? literatureRun.startedAt ?? "") : "No run time",
      href: literatureRun ? `/runs/${encodeURIComponent(literatureRun.id)}/literature` : undefined,
      searchText: searchable([
        project.name,
        "research literature novelty counter evidence retrieval",
        literatureRun?.id,
        literatureRun?.status,
        literatureRun?.mode,
      ]),
    });
  }

  if (resultsRun || plots.length > 0) {
    if (plots.length === 0) {
      items.push({
        id: `${project.id}:experiments`,
        kind: "experiments",
        title: "Experiments and figures",
        eyebrow: "Experiments",
        description: "Generated graphs, diagrams, plots, tables, and execution outputs from the results stage.",
        meta: "Results run",
        href: resultsRun ? `/runs/${encodeURIComponent(resultsRun.id)}` : undefined,
        searchText: searchable([
          project.name,
          "experiment results graph plot diagram table",
          resultsRun?.id,
          resultsRun?.status,
        ]),
      });
    } else {
      plots.forEach((plot) => {
        items.push({
          id: `${project.id}:plot:${plot.name}`,
          kind: "experiments",
          title: plot.name.replace(/\.[^.]+$/, ""),
          eyebrow: "Graph",
          description: "Generated plot, graph, or diagram from the results stage.",
          meta: plot.name,
          href: plot.url,
          searchText: searchable([
            project.name,
            "experiment results graph plot diagram table",
            plot.name,
            resultsRun?.id,
            resultsRun?.status,
          ]),
        });
      });
    }
  }

  nodes.forEach((node) => {
    items.push({
      id: `${project.id}:reference:${node.id}`,
      kind: "references",
      title: node.title || "Untitled source",
      eyebrow: "Reference",
      description: [node.authors?.join(", "), node.year, node.venue].filter(Boolean).join(" · ") ||
        "Citation graph source.",
      meta: node.venue ?? node.kind ?? "Citation",
      href: node.url || (literatureRun ? `/runs/${encodeURIComponent(literatureRun.id)}/citations` : undefined),
      searchText: searchable([
        project.name,
        "reference citation source bibliography",
        node.title,
        node.authors?.join(" "),
        node.year,
        node.venue,
        node.kind,
      ]),
    });
  });

  return items;
}

function visibleItems(entry: ProjectLibrary, filter: FilterId): LibraryItem[] {
  const items = buildItems(entry);
  return filter === "all" ? items : items.filter((item) => item.kind === filter);
}

function filterItems(entry: ProjectLibrary, filter: FilterId, query: string): LibraryItem[] {
  const items = visibleItems(entry, filter);
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter((item) => item.searchText.includes(q));
}

function splitListInput(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function publicationSearchText(publication: ResearchPublication): string {
  return searchable([
    publication.title,
    publication.description,
    publication.creatorName,
    publication.creatorAffiliation,
    publication.authors.map((author) => `${author.name} ${author.affiliation ?? ""}`).join(" "),
    publication.taggedAuthors.map((author) => `${author.name} ${author.affiliation ?? ""}`).join(" "),
    publication.tags.join(" "),
  ]);
}

function filterPublications(
  publications: ResearchPublication[],
  filter: FilterId,
  query: string,
): ResearchPublication[] {
  if (filter !== "all" && filter !== "papers") return [];
  const q = query.trim().toLowerCase();
  if (!q) return publications;
  return publications.filter((publication) => publicationSearchText(publication).includes(q));
}

function mergePublication(
  publications: ResearchPublication[],
  next: ResearchPublication,
): ResearchPublication[] {
  const found = publications.some((publication) => publication.id === next.id);
  if (!found) return [next, ...publications];
  return publications.map((publication) => (publication.id === next.id ? next : publication));
}

function displayAuthors(publication: ResearchPublication): PublicationFeedAuthor[] {
  return publication.authors.length > 0
    ? publication.authors
    : [
        {
          name: publication.creatorName,
          affiliation: publication.creatorAffiliation,
          avatarUrl: publication.creatorAvatarUrl,
          userId: publication.creatorUserId,
        },
      ];
}

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] ?? "P") + (parts[1]?.[0] ?? "");
}

export default function PapersPage() {
  return (
    <DashboardShell>
      <PapersContent />
    </DashboardShell>
  );
}

function PapersContent() {
  const [entries, setEntries] = React.useState<ProjectLibrary[]>([]);
  const [publications, setPublications] = React.useState<ResearchPublication[]>([]);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState<FilterId>("all");
  const [view, setView] = React.useState<ViewMode>("feed");
  const [query, setQuery] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [feedError, setFeedError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    setFeedError(null);
    try {
      const [projects, feed] = await Promise.all([
        api.listProjects(),
        api.listPublications({ limit: 100 }).catch((err) => {
          setFeedError(err instanceof Error ? err.message : "Failed to load publication feed.");
          return [] as ResearchPublication[];
        }),
      ]);
      const loaded = await Promise.all(projects.map(loadProjectLibrary));
      setEntries(loaded);
      setPublications(feed);
      setSelectedId((current) => current ?? loaded[0]?.project.id ?? null);
    } catch (err) {
      setEntries([]);
      setError(err instanceof Error ? err.message : "Failed to load papers.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const filteredEntries = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return entries.filter((entry) => {
      const items = filterItems(entry, filter, query);
      if (items.length === 0) return false;
      if (!q) return true;
      return (
        entry.project.name.toLowerCase().includes(q) ||
        items.some((item) => item.searchText.includes(q))
      );
    });
  }, [entries, filter, query]);

  const selected = filteredEntries.find((entry) => entry.project.id === selectedId) ?? filteredEntries[0] ?? null;
  const selectedItems = selected ? filterItems(selected, filter, query) : [];
  const filteredPublications = React.useMemo(
    () => filterPublications(publications, filter, query),
    [publications, filter, query],
  );
  const visibleArtifactCount = React.useMemo(
    () => filteredEntries.reduce((sum, entry) => sum + filterItems(entry, filter, query).length, 0),
    [filteredEntries, filter, query],
  );
  const handlePublicationChanged = React.useCallback((publication: ResearchPublication) => {
    setPublications((current) => mergePublication(current, publication));
  }, []);
  const handlePublicationSettingsUpdated = React.useCallback(
    (projectId: string, settings: PublicationSettings) => {
      setEntries((current) =>
        current.map((entry) =>
          entry.project.id === projectId
            ? {
                ...entry,
                project: {
                  ...entry.project,
                  publicationSettings: settings,
                  updatedAt: new Date().toISOString(),
                },
              }
            : entry,
        ),
      );
    },
    [],
  );

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <header className="hairline-b flex flex-none flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Library size={17} strokeWidth={1.75} className="text-(--color-brand-hover)" />
          <div className="min-w-0">
            <h1 className="text-[18px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
              Papers
            </h1>
            <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
              Research feed and project folders for generated manuscripts.
            </p>
          </div>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <TabPills
            tabs={VIEW_TABS}
            activeId={view}
            onSelect={(id) => setView(id as ViewMode)}
            ariaLabel="Papers view"
          />
          <Button className="w-full sm:w-auto" variant="ghost" size="sm" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw size={13} className={cn(loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </header>

      <section className="hairline-b flex flex-none flex-col gap-3 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <TabPills
            tabs={FILTERS}
            activeId={filter}
            onSelect={(id) => setFilter(id as FilterId)}
            className="max-w-full overflow-x-auto pb-0.5"
            ariaLabel="Paper library filter"
          />
          <label className="flex h-9 min-w-0 items-center gap-2 rounded-[7px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-3 shadow-[var(--shadow-glass)] xl:w-[360px]">
            <Search size={13} className="text-(--color-text-tertiary)" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search papers, data, citations"
              className="min-w-0 flex-1 bg-transparent font-mono text-[12px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary) focus:outline-none"
            />
            {query ? (
              <button
                type="button"
                onClick={() => setQuery("")}
                aria-label="Clear search"
                className="flex size-5 items-center justify-center rounded-full text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)"
              >
                <X size={12} />
              </button>
            ) : null}
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-(--color-text-row-meta)">
          <span className="rounded-full border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2 py-1">
            {filteredEntries.length} {filteredEntries.length === 1 ? "project" : "projects"}
          </span>
          <span className="rounded-full border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2 py-1">
            {visibleArtifactCount} {visibleArtifactCount === 1 ? "artifact" : "artifacts"}
          </span>
          <span className="rounded-full border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2 py-1">
            {filteredPublications.length} {filteredPublications.length === 1 ? "post" : "posts"}
          </span>
          {query ? (
            <span className="min-w-0 truncate rounded-full border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2 py-1 font-mono">
              query: {query}
            </span>
          ) : null}
        </div>
      </section>

      {error ? (
        <div className="mx-4 mt-3 flex flex-none items-center gap-2 rounded-[8px] border border-(--color-status-red-spec) px-3 py-2 text-[12px] text-(--color-status-red-spec)">
          {error}
        </div>
      ) : null}

      {view === "feed" ? (
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:overflow-hidden xl:grid-cols-[minmax(0,1fr)_400px]">
          <section className="flex-none px-4 py-4 lg:min-h-0 lg:overflow-y-auto lg:px-5 lg:py-5" data-testid="publication-feed">
            {feedError ? (
              <div className="mb-3 rounded-[8px] border border-(--color-status-amber-spec) px-3 py-2 text-[12px] text-(--color-status-amber-spec)">
                {feedError}
              </div>
            ) : null}
            {loading ? (
              <PublicationFeedSkeleton />
            ) : filteredPublications.length === 0 ? (
              <EmptyPublicationFeed />
            ) : (
              <div className="mx-auto flex w-full max-w-[760px] flex-col">
                {filteredPublications.map((publication) => (
                  <PublicationPost
                    key={publication.id}
                    publication={publication}
                    onChanged={handlePublicationChanged}
                  />
                ))}
              </div>
            )}
          </section>

          <aside className="hairline-t flex-none px-4 py-4 lg:min-h-0 lg:border-l lg:border-t-0 lg:border-(--color-border-standard) lg:overflow-y-auto lg:px-5 lg:py-5">
            <PublishPanel
              entry={selected}
              onPublished={handlePublicationChanged}
              onOpenLibrary={() => setView("library")}
            />
          </aside>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:grid lg:grid-cols-[minmax(300px,0.82fr)_minmax(0,1.18fr)] lg:overflow-hidden xl:grid-cols-[minmax(420px,0.9fr)_minmax(0,1.1fr)]">
          <section className="flex-none px-4 py-4 lg:min-h-0 lg:overflow-y-auto lg:px-5 lg:py-5">
            {loading ? (
              <FolderSkeleton />
            ) : filteredEntries.length === 0 ? (
              <EmptyLibrary />
            ) : (
              <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,190px),1fr))] gap-3 lg:grid-cols-[repeat(auto-fit,minmax(190px,1fr))] xl:gap-4">
                {filteredEntries.map((entry, index) => (
                  <ProjectFolderCard
                    key={entry.project.id}
                    entry={entry}
                    active={selected?.project.id === entry.project.id}
                    color={FOLDER_COLORS[index % FOLDER_COLORS.length]}
                    onSelect={() => setSelectedId(entry.project.id)}
                  />
                ))}
              </div>
            )}
          </section>

          <section className="hairline-t flex-none px-4 py-4 lg:min-h-0 lg:border-l lg:border-t-0 lg:border-(--color-border-standard) lg:overflow-y-auto lg:px-5 lg:py-5">
            {selected ? (
              <ProjectDetail
                entry={selected}
                items={selectedItems}
                filter={filter}
                query={query}
                onFilter={setFilter}
                onPublicationSettingsUpdated={handlePublicationSettingsUpdated}
              />
            ) : (
              <EmptyLibrary />
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function ProjectFolderCard({
  entry,
  active,
  color,
  onSelect,
}: {
  entry: ProjectLibrary;
  active: boolean;
  color: string;
  onSelect: () => void;
}) {
  const previewItems = buildItems(entry).slice(0, 3);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "surface-linear-card group flex min-h-[202px] flex-col items-start gap-4 p-4 text-left transition-colors",
        "hover:border-(--color-border-strong) sm:p-[18px]",
        active && "border-(--color-brand-indigo) shadow-[var(--shadow-glass-active)]",
      )}
    >
      <div className="flex h-[104px] w-full items-center justify-center rounded-[8px] bg-(--color-bg-pill-inactive)">
        <Folder
          color={color}
          size={0.86}
          className="origin-center"
          items={previewItems.map((item) => (
            <PaperSlip key={item.id} item={item} />
          ))}
        />
      </div>
      <div className="min-w-0 self-stretch">
        <h2 className="truncate text-[13px] font-medium text-(--color-text-primary-strong)">
          {entry.project.name}
        </h2>
        <p className="mt-1 line-clamp-2 text-[12px] text-(--color-text-row-meta)">
          {previewItems[0]?.description ?? "No generated paper artifacts yet."}
        </p>
      </div>
      <div className="mt-auto flex flex-wrap gap-1.5">
        <MiniMetric icon={FileText} label={`${entry.paper.sections.length || (entry.paper.pdfUrl ? 1 : 0)} papers`} />
        <MiniMetric icon={BarChart3} label={`${entry.plots.length} graphs`} />
        <MiniMetric icon={BookOpen} label={`${citationNodes(entry.citations).length} refs`} />
      </div>
    </button>
  );
}

function PaperSlip({ item }: { item: LibraryItem }) {
  return (
    <div className="flex h-full w-full flex-col justify-between overflow-hidden px-1.5 py-1 text-[#161718]">
      <span className="text-[7px] font-semibold uppercase tracking-[0.04em] text-[#5b5c60]">
        {item.eyebrow}
      </span>
      <span className="line-clamp-3 text-[8px] font-semibold leading-[1.15]">
        {item.title}
      </span>
    </div>
  );
}

function MiniMetric({
  icon: Icon,
  label,
}: {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  label: string;
}) {
  return (
    <span className="inline-flex h-6 items-center gap-1 rounded-full border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2 text-[11px] text-(--color-text-row-meta)">
      <Icon size={11} strokeWidth={1.7} />
      {label}
    </span>
  );
}

function PublishPanel({
  entry,
  onPublished,
  onOpenLibrary,
}: {
  entry: ProjectLibrary | null;
  onPublished: (publication: ResearchPublication) => void;
  onOpenLibrary: () => void;
}) {
  const [description, setDescription] = React.useState("");
  const [tags, setTags] = React.useState("");
  const [taggedAuthors, setTaggedAuthors] = React.useState("");
  const [publishing, setPublishing] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const hasPaper = Boolean(entry?.paper.pdfUrl || entry?.paper.sections.length);

  React.useEffect(() => {
    setDescription(entry ? buildItems(entry).find((item) => item.kind === "papers")?.description ?? "" : "");
    setTags("");
    setTaggedAuthors("");
    setMessage(null);
    setError(null);
  }, [entry?.project.id]);

  const publish = async () => {
    if (!entry) return;
    setPublishing(true);
    setMessage(null);
    setError(null);
    try {
      const publication = await api.publishProjectPublication(entry.project.id, {
        title: entry.project.name,
        description: description.trim() || undefined,
        tags: splitListInput(tags),
        tagged_authors: splitListInput(taggedAuthors).map((name) => ({ name })),
      });
      onPublished(publication);
      setMessage("Published to the research feed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to publish this paper.");
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <section className="surface-linear-card flex flex-col gap-3 p-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-[13px] font-medium text-(--color-text-primary-strong)">
            <Rss size={14} strokeWidth={1.75} className="text-(--color-brand-hover)" />
            Publish
          </h2>
          <Button size="sm" variant="ghost" onClick={onOpenLibrary}>
            <LayoutGrid size={13} />
            Library
          </Button>
        </div>
        {entry ? (
          <>
            <div className="rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) px-3 py-2">
              <p className="truncate text-[12px] font-medium text-(--color-text-primary-strong)">
                {entry.project.name}
              </p>
              <p className="mt-0.5 text-[11px] text-(--color-text-row-meta)">
                {entry.paper.pdfUrl ? "PDF ready" : entry.paper.sections.length ? "Paper sections ready" : "No paper artifact"}
              </p>
            </div>
            <TextAreaField
              label="Description"
              value={description}
              onChange={setDescription}
            />
            <TextField
              label="Tags"
              value={tags}
              onChange={setTags}
            />
            <TextField
              label="Tag authors"
              value={taggedAuthors}
              onChange={setTaggedAuthors}
            />
            <Button
              size="sm"
              variant="primary"
              onClick={() => void publish()}
              disabled={publishing || !hasPaper}
            >
              <Send size={13} />
              {publishing ? "Publishing" : "Publish paper"}
            </Button>
          </>
        ) : (
          <EmptySettingsRow label="Select a project from the library before publishing." />
        )}
        {error ? (
          <p className="rounded-[7px] border border-(--color-status-red-spec) px-3 py-2 text-[12px] text-(--color-status-red-spec)">
            {error}
          </p>
        ) : message ? (
          <p className="rounded-[7px] border border-(--color-status-green-spec) px-3 py-2 text-[12px] text-(--color-status-green-spec)">
            {message}
          </p>
        ) : null}
      </section>
      <section className="surface-linear-card flex flex-col gap-2 p-3">
        <h2 className="flex items-center gap-2 text-[13px] font-medium text-(--color-text-primary-strong)">
          <Users size={14} strokeWidth={1.75} className="text-(--color-brand-hover)" />
          Authors
        </h2>
        {entry?.project.publicationSettings?.authors.length ? (
          <div className="flex flex-col gap-2">
            {entry.project.publicationSettings.authors.map((author) => (
              <div key={author.id} className="flex min-w-0 items-center gap-2">
                <Avatar name={author.name || "Author"} />
                <div className="min-w-0">
                  <p className="truncate text-[12px] font-medium text-(--color-text-primary)">
                    {author.name || "Unnamed author"}
                  </p>
                  <p className="truncate text-[11px] text-(--color-text-row-meta)">
                    {author.affiliation || author.role}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptySettingsRow label="No authors assigned yet." />
        )}
      </section>
    </div>
  );
}

function PublicationPost({
  publication,
  onChanged,
}: {
  publication: ResearchPublication;
  onChanged: (publication: ResearchPublication) => void;
}) {
  const [liked, setLiked] = React.useState(false);
  const [comment, setComment] = React.useState("");
  const [tagAuthors, setTagAuthors] = React.useState("");
  const [busyAction, setBusyAction] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const authors = displayAuthors(publication);
  const lead = authors[0];
  const previewUrl = publication.firstPagePreviewUrl.includes("#")
    ? publication.firstPagePreviewUrl
    : `${publication.firstPagePreviewUrl}#page=1&toolbar=0&navpanes=0`;

  const runAction = async (action: string, fn: () => Promise<void>) => {
    setBusyAction(action);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setBusyAction(null);
    }
  };

  const submitComment = () =>
    runAction("comment", async () => {
      const text = comment.trim();
      if (!text) return;
      const saved = await api.commentOnPublication(publication.id, { body: text });
      onChanged({
        ...publication,
        commentCount: publication.commentCount + 1,
        comments: [...publication.comments, saved],
      });
      setComment("");
    });

  const toggleLike = () =>
    runAction("like", async () => {
      const next = liked
        ? await api.unlikePublication(publication.id)
        : await api.likePublication(publication.id);
      setLiked(!liked);
      onChanged(next);
    });

  const share = () =>
    runAction("share", async () => {
      const next = await api.sharePublication(publication.id, "link");
      onChanged(next);
      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(`${window.location.origin}/papers?publication=${publication.id}`);
        } catch {
          // Sharing has already succeeded; clipboard writes can be blocked by browser policy.
        }
      }
    });

  const tag = () =>
    runAction("tag", async () => {
      const authorsToTag = splitListInput(tagAuthors).map((name) => ({ name }));
      if (authorsToTag.length === 0) return;
      const next = await api.tagPublicationAuthors(publication.id, authorsToTag);
      onChanged(next);
      setTagAuthors("");
    });

  return (
    <article className="hairline-b bg-(--color-bg-base) px-1 py-4 sm:px-3" data-testid="publication-post">
      <div className="flex gap-3">
        <Avatar name={publication.creatorName} src={publication.creatorAvatarUrl ?? undefined} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <h2 className="text-[13px] font-semibold text-(--color-text-primary-strong)">
              {publication.creatorName}
            </h2>
            <span className="text-[11px] text-(--color-text-quaternary)">
              {formatRelativeTime(publication.publishedAt)}
            </span>
          </div>
          <p className="mt-0.5 truncate text-[12px] text-(--color-text-row-meta)">
            {publication.creatorAffiliation || lead?.affiliation || "Independent research"}
          </p>

          <h3 className="mt-3 text-[18px] font-medium leading-[1.25] tracking-[-0.01em] text-(--color-text-primary-strong)">
            {publication.title}
          </h3>
          <div className="mt-3 overflow-hidden rounded-[8px] border border-(--color-border-card) bg-[#f7f7f4]">
            <iframe
              title={`${publication.title} first page preview`}
              src={previewUrl}
              className="h-[280px] w-full bg-white"
            />
          </div>
          <p className="mt-3 text-[13px] leading-6 text-(--color-text-secondary)">
            {publication.description}
          </p>

          <div className="mt-3 flex flex-wrap gap-1.5">
            {publication.tags.map((tagValue) => (
              <span
                key={tagValue}
                className="rounded-full border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2 py-1 font-mono text-[11px] text-(--color-text-row-meta)"
              >
                #{tagValue}
              </span>
            ))}
          </div>

          {publication.taggedAuthors.length > 0 ? (
            <p className="mt-2 flex items-center gap-1.5 text-[12px] text-(--color-text-row-meta)">
              <AtSign size={12} />
              {publication.taggedAuthors.map((author) => author.name).join(", ")}
            </p>
          ) : null}

          <div className="mt-3 grid grid-cols-3 gap-2 border-y border-(--color-border-card) py-2">
            <FeedAction
              icon={MessageCircle}
              label={`${publication.commentCount} Comment`}
              disabled={busyAction !== null}
              onClick={() => document.getElementById(`comment-${publication.id}`)?.focus()}
            />
            <FeedAction
              icon={Heart}
              label={`${publication.likeCount} Like`}
              active={liked}
              disabled={busyAction !== null}
              onClick={() => void toggleLike()}
            />
            <FeedAction
              icon={Share2}
              label={`${publication.shareCount} Share`}
              disabled={busyAction !== null}
              onClick={() => void share()}
            />
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-[1fr_auto]">
            <input
              id={`comment-${publication.id}`}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Write a comment"
              aria-label={`Comment on ${publication.title}`}
              className="h-9 rounded-[7px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-3 text-[12px] text-(--color-text-primary) outline-none placeholder:text-(--color-text-quaternary) focus:border-(--color-brand-indigo)"
            />
            <Button size="sm" variant="ghost" onClick={() => void submitComment()} disabled={busyAction !== null}>
              <MessageCircle size={13} />
              Comment
            </Button>
          </div>

          <div className="mt-2 grid gap-2 md:grid-cols-[1fr_auto]">
            <input
              value={tagAuthors}
              onChange={(event) => setTagAuthors(event.target.value)}
              placeholder="Tag authors by name"
              aria-label={`Tag authors on ${publication.title}`}
              className="h-9 rounded-[7px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-3 text-[12px] text-(--color-text-primary) outline-none placeholder:text-(--color-text-quaternary) focus:border-(--color-brand-indigo)"
            />
            <Button size="sm" variant="ghost" onClick={() => void tag()} disabled={busyAction !== null}>
              <AtSign size={13} />
              Tag
            </Button>
          </div>

          {publication.comments.length > 0 ? (
            <div className="mt-3 flex flex-col gap-2">
              {publication.comments.slice(-2).map((item) => (
                <div key={item.id} className="rounded-[8px] bg-(--color-bg-pill-inactive) px-3 py-2">
                  <p className="text-[12px] font-medium text-(--color-text-primary)">
                    {item.userName}
                  </p>
                  <p className="mt-0.5 text-[12px] leading-5 text-(--color-text-row-meta)">
                    {item.body}
                  </p>
                </div>
              ))}
            </div>
          ) : null}

          {error ? (
            <p className="mt-3 rounded-[7px] border border-(--color-status-red-spec) px-3 py-2 text-[12px] text-(--color-status-red-spec)">
              {error}
            </p>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function FeedAction({
  icon: Icon,
  label,
  active,
  disabled,
  onClick,
}: {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex h-8 items-center justify-center gap-1.5 rounded-[7px] text-[12px] transition-colors",
        active
          ? "bg-(--color-brand-indigo)/10 text-(--color-brand-hover)"
          : "text-(--color-text-row-meta) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)",
        "disabled:cursor-not-allowed disabled:opacity-50",
      )}
    >
      <Icon size={13} strokeWidth={1.75} />
      <span className="truncate">{label}</span>
    </button>
  );
}

function Avatar({ name, src }: { name: string; src?: string | null }) {
  return src ? (
    <img
      src={src}
      alt=""
      className="size-10 flex-none rounded-full border border-(--color-border-card) object-cover"
    />
  ) : (
    <div className="flex size-10 flex-none items-center justify-center rounded-full border border-(--color-border-card) bg-(--color-bg-pill-inactive) font-mono text-[12px] text-(--color-text-primary)">
      {initialsFor(name).toUpperCase()}
    </div>
  );
}

function ProjectDetail({
  entry,
  items,
  filter,
  query,
  onFilter,
  onPublicationSettingsUpdated,
}: {
  entry: ProjectLibrary;
  items: LibraryItem[];
  filter: FilterId;
  query: string;
  onFilter: (filter: FilterId) => void;
  onPublicationSettingsUpdated: (projectId: string, settings: PublicationSettings) => void;
}) {
  const references = citationNodes(entry.citations);
  const q = query.trim().toLowerCase();
  const visiblePlots =
    q.length > 0
      ? entry.plots.filter((plot) => plot.name.toLowerCase().includes(q))
      : entry.plots;
  const visibleReferences =
    q.length > 0
      ? references.filter((reference) =>
          searchable([
            reference.title,
            reference.authors?.join(" "),
            reference.year,
            reference.venue,
            reference.kind,
          ]).includes(q),
        )
      : references;
  const showPlots = (filter === "all" || filter === "experiments") && visiblePlots.length > 0;
  const showReferences = (filter === "all" || filter === "references") && visibleReferences.length > 0;

  return (
    <div className="flex min-h-full flex-col gap-5">
      <div className="flex flex-col gap-3.5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-[18px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
              {entry.project.name}
            </h2>
            <p className="mt-1 text-[12px] text-(--color-text-row-meta)">
              Updated {formatRelativeTime(entry.project.updatedAt)}
            </p>
          </div>
          <span className="rounded-full border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2.5 py-1 font-mono text-[11px] text-(--color-text-row-meta)">
            {entry.project.journal}
          </span>
        </div>
        <TabPills
          tabs={FILTERS}
          activeId={filter}
          onSelect={(id) => onFilter(id as FilterId)}
          className="max-w-full overflow-x-auto pb-0.5"
          ariaLabel="Selected project artifact filter"
        />
      </div>

      <div className="grid gap-2 sm:grid-cols-3">
        <Metric label="Papers" value={String(entry.paper.sections.length || (entry.paper.pdfUrl ? 1 : 0))} />
        <Metric label="Graphs" value={String(entry.plots.length)} />
        <Metric label="References" value={String(references.length)} />
      </div>

      <PublicationSettingsPanel
        project={entry.project}
        onUpdated={(settings) => onPublicationSettingsUpdated(entry.project.id, settings)}
      />

      <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
        {items.length === 0 ? (
          <div className="surface-linear-card flex h-44 flex-col items-center justify-center gap-2 text-center md:col-span-2 2xl:col-span-3">
            <Library size={18} className="text-(--color-text-quaternary)" />
            <p className="text-[13px] text-(--color-text-row-meta)">
              No artifacts match this filter yet.
            </p>
          </div>
        ) : (
          items.map((item) => <ArtifactRow key={item.id} item={item} />)
        )}
      </div>

      {showPlots ? <PlotStrip plots={visiblePlots} /> : null}
      {showReferences ? <ReferenceList references={visibleReferences} /> : null}
    </div>
  );
}

function PublicationSettingsPanel({
  project,
  onUpdated,
}: {
  project: Project;
  onUpdated: (settings: PublicationSettings) => void;
}) {
  const [draft, setDraft] = React.useState<PublicationSettings>(
    () => project.publicationSettings ?? emptyPublicationSettings(),
  );
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setDraft(project.publicationSettings ?? emptyPublicationSettings());
    setMessage(null);
    setError(null);
  }, [project.id, project.publicationSettings]);

  const addAuthor = () => {
    setDraft((current) => ({
      ...current,
      authors: [
        ...current.authors,
        {
          id: makeClientId("auth"),
          name: "",
          email: "",
          affiliation: "",
          role: "Author",
          order: current.authors.length,
        },
      ],
    }));
  };

  const updateAuthor = (id: string, patch: Partial<PublicationAuthor>) => {
    setDraft((current) => ({
      ...current,
      authors: current.authors.map((author) => (author.id === id ? { ...author, ...patch } : author)),
    }));
  };

  const removeAuthor = (id: string) => {
    setDraft((current) => ({
      ...current,
      authors: current.authors.filter((author) => author.id !== id),
    }));
  };

  const addTask = () => {
    setDraft((current) => ({
      ...current,
      tasks: [
        ...current.tasks,
        {
          id: makeClientId("task"),
          title: "",
          kind: "section",
          section: "",
          assignee: "",
          assignee_email: "",
          status: "todo",
          due_at: null,
          completed_at: null,
          notes: "",
        },
      ],
    }));
  };

  const updateTask = (id: string, patch: Partial<PublicationTask>) => {
    setDraft((current) => ({
      ...current,
      tasks: current.tasks.map((task) => (task.id === id ? { ...task, ...patch } : task)),
    }));
  };

  const removeTask = (id: string) => {
    setDraft((current) => ({
      ...current,
      tasks: current.tasks.filter((task) => task.id !== id),
    }));
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const normalized = normalizePublicationSettings(draft);
      const saved = await api.updatePublicationSettings(project.id, normalized);
      setDraft(saved);
      onUpdated(saved);
      setMessage("Saved publication settings.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save publication settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="surface-linear-card flex flex-col gap-4 p-3 sm:p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-[13px] font-medium text-(--color-text-primary-strong)">
            <UserRound size={14} strokeWidth={1.75} className="text-(--color-brand-hover)" />
            Publication settings
          </h3>
          <p className="mt-1 text-[12px] leading-5 text-(--color-text-row-meta)">
            Manage authors, publication dates, section assignments, reviews, and completion work for this project.
          </p>
        </div>
        <Button size="sm" variant="primary" onClick={() => void save()} disabled={saving}>
          <CheckCircle2 size={13} />
          {saving ? "Saving" : "Save"}
        </Button>
      </div>

      {error ? (
        <p className="rounded-[7px] border border-(--color-status-red-spec) px-3 py-2 text-[12px] text-(--color-status-red-spec)">
          {error}
        </p>
      ) : message ? (
        <p className="rounded-[7px] border border-(--color-status-green-spec) px-3 py-2 text-[12px] text-(--color-status-green-spec)">
          {message}
        </p>
      ) : null}

      <div className="grid gap-3 2xl:grid-cols-[0.92fr_1.08fr]">
        <div className="flex min-w-0 flex-col gap-3">
          <SettingsBlock
            title="Authors"
            action={
              <Button size="sm" variant="ghost" onClick={addAuthor}>
                <Plus size={13} />
                Add
              </Button>
            }
          >
            {draft.authors.length === 0 ? (
              <EmptySettingsRow label="No authors assigned yet." />
            ) : (
              <div className="flex flex-col gap-2">
                {draft.authors.map((author, index) => (
                  <div key={author.id} className="rounded-[8px] border border-(--color-border-card) p-2.5">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] text-(--color-text-quaternary)">
                        Author {index + 1}
                      </span>
                      <IconButton label="Remove author" onClick={() => removeAuthor(author.id)} />
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <TextField
                        label="Name"
                        value={author.name}
                        onChange={(value) => updateAuthor(author.id, { name: value })}
                      />
                      <TextField
                        label="Role"
                        value={author.role}
                        onChange={(value) => updateAuthor(author.id, { role: value })}
                      />
                      <TextField
                        label="Email"
                        type="email"
                        value={author.email ?? ""}
                        onChange={(value) => updateAuthor(author.id, { email: value })}
                      />
                      <TextField
                        label="Affiliation"
                        value={author.affiliation ?? ""}
                        onChange={(value) => updateAuthor(author.id, { affiliation: value })}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </SettingsBlock>

          <SettingsBlock title="Dates" icon={<CalendarDays size={13} />}>
            <div className="grid gap-2 sm:grid-cols-2">
              {(["target", "submitted", "accepted", "published"] as const).map((field) => (
                <TextField
                  key={field}
                  label={field[0].toUpperCase() + field.slice(1)}
                  type="date"
                  value={toDateInput(draft.dates[field])}
                  onChange={(value) =>
                    setDraft((current) => ({
                      ...current,
                      dates: { ...current.dates, [field]: fromDateInput(value) },
                    }))
                  }
                />
              ))}
            </div>
          </SettingsBlock>
        </div>

        <SettingsBlock
          title="Tasks"
          action={
            <Button size="sm" variant="ghost" onClick={addTask}>
              <Plus size={13} />
              Add
            </Button>
          }
        >
          {draft.tasks.length === 0 ? (
            <EmptySettingsRow label="No Lab tasks assigned yet." />
          ) : (
            <div className="flex max-h-[580px] flex-col gap-2 overflow-y-auto pr-1">
              {draft.tasks.map((task) => (
                <div key={task.id} className="rounded-[8px] border border-(--color-border-card) p-2.5">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] text-(--color-text-quaternary)">
                      {TASK_KINDS.find((kind) => kind.id === task.kind)?.label ?? "Task"}
                    </span>
                    <IconButton label="Remove task" onClick={() => removeTask(task.id)} />
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <TextField
                      label="Task"
                      value={task.title}
                      className="sm:col-span-2"
                      onChange={(value) => updateTask(task.id, { title: value })}
                    />
                    <SelectField
                      label="Type"
                      value={task.kind}
                      options={TASK_KINDS}
                      onChange={(value) => updateTask(task.id, { kind: value as PublicationTaskKind })}
                    />
                    <SelectField
                      label="Status"
                      value={task.status}
                      options={TASK_STATUSES}
                      onChange={(value) => updateTask(task.id, { status: value as PublicationTaskStatus })}
                    />
                    <TextField
                      label="Section"
                      value={task.section ?? ""}
                      onChange={(value) => updateTask(task.id, { section: value })}
                    />
                    <TextField
                      label="Assignee"
                      value={task.assignee ?? ""}
                      onChange={(value) => updateTask(task.id, { assignee: value })}
                    />
                    <TextField
                      label="Assignee email"
                      type="email"
                      value={task.assignee_email ?? ""}
                      onChange={(value) => updateTask(task.id, { assignee_email: value })}
                    />
                    <TextField
                      label="Due"
                      type="date"
                      value={toDateInput(task.due_at)}
                      onChange={(value) => updateTask(task.id, { due_at: fromDateInput(value) })}
                    />
                    <TextAreaField
                      label="Notes"
                      value={task.notes ?? ""}
                      className="sm:col-span-2"
                      onChange={(value) => updateTask(task.id, { notes: value })}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </SettingsBlock>
      </div>
    </section>
  );
}

function SettingsBlock({
  title,
  icon,
  action,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) p-3">
      <div className="flex items-center justify-between gap-2">
        <h4 className="flex items-center gap-1.5 text-[12px] font-medium text-(--color-text-primary-strong)">
          {icon}
          {title}
        </h4>
        {action}
      </div>
      {children}
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  type = "text",
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: React.HTMLInputTypeAttribute;
  className?: string;
}) {
  return (
    <label className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span className="font-mono text-[10px] uppercase tracking-[0.04em] text-(--color-text-quaternary)">
        {label}
      </span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 min-w-0 rounded-[7px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2.5 text-[12px] text-(--color-text-primary) outline-none focus:border-(--color-brand-indigo)"
      />
    </label>
  );
}

function TextAreaField({
  label,
  value,
  onChange,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <label className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span className="font-mono text-[10px] uppercase tracking-[0.04em] text-(--color-text-quaternary)">
        {label}
      </span>
      <textarea
        value={value}
        rows={3}
        onChange={(event) => onChange(event.target.value)}
        className="min-w-0 resize-y rounded-[7px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2.5 py-2 text-[12px] leading-5 text-(--color-text-primary) outline-none focus:border-(--color-brand-indigo)"
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ id: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-[0.04em] text-(--color-text-quaternary)">
        {label}
      </span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 min-w-0 rounded-[7px] border border-(--color-border-pill) bg-(--color-bg-pill-inactive) px-2 text-[12px] text-(--color-text-primary) outline-none focus:border-(--color-brand-indigo)"
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function IconButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex size-7 items-center justify-center rounded-full text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-status-red-spec)"
    >
      <Trash2 size={13} />
    </button>
  );
}

function EmptySettingsRow({ label }: { label: string }) {
  return (
    <div className="rounded-[8px] border border-dashed border-(--color-border-card) px-3 py-4 text-center text-[12px] text-(--color-text-row-meta)">
      {label}
    </div>
  );
}

function ArtifactRow({ item }: { item: LibraryItem }) {
  const Icon =
    item.kind === "papers"
      ? FileText
      : item.kind === "data"
        ? Database
        : item.kind === "research"
          ? GitBranch
          : item.kind === "experiments"
            ? FlaskConical
            : BookOpen;

  const body = (
    <div className="surface-linear-card flex h-full min-h-[116px] items-start gap-3 p-3 transition-colors hover:border-(--color-border-strong)">
      <span className="mt-0.5 flex size-8 flex-none items-center justify-center rounded-[8px] bg-(--color-bg-pill-inactive) text-(--color-brand-hover)">
        <Icon size={15} strokeWidth={1.75} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] uppercase tracking-[0.04em] text-(--color-text-quaternary)">
            {item.eyebrow}
          </span>
          <span className="text-[11px] text-(--color-text-quaternary)">·</span>
          <span className="truncate text-[11px] text-(--color-text-row-meta)">{item.meta}</span>
        </div>
        <h3 className="mt-1 text-[13px] font-medium text-(--color-text-primary-strong)">
          {item.title}
        </h3>
        <p className="mt-1 line-clamp-3 text-[12px] leading-5 text-(--color-text-row-meta)">
          {item.description}
        </p>
      </div>
    </div>
  );

  return item.href ? (
    <Link href={item.href} target={item.href.startsWith("http") ? "_blank" : undefined}>
      {body}
    </Link>
  ) : (
    body
  );
}

function PlotStrip({ plots }: { plots: PlotRecord[] }) {
  if (plots.length === 0) return null;
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-[13px] font-medium text-(--color-text-primary-strong)">Graphs and diagrams</h3>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,150px),1fr))] gap-2">
        {plots.slice(0, 6).map((plot) => (
          <a
            key={plot.name}
            href={plot.url}
            target="_blank"
            rel="noreferrer"
            className="surface-linear-card block overflow-hidden"
          >
            <div className="flex aspect-[4/3] items-center justify-center bg-(--color-bg-surface)">
              <img src={plot.url} alt={plot.name} className="max-h-full max-w-full object-contain" />
            </div>
            <div className="truncate px-2 py-1.5 font-mono text-[11px] text-(--color-text-row-meta)">
              {plot.name}
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}

function ReferenceList({ references }: { references: CitationNode[] }) {
  if (references.length === 0) return null;
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-[13px] font-medium text-(--color-text-primary-strong)">Citation list</h3>
      <div className="surface-linear-card divide-y divide-(--color-border-card) overflow-hidden">
        {references.slice(0, 8).map((reference) => (
          <div key={reference.id} className="px-3 py-2">
            <p className="truncate text-[12px] font-medium text-(--color-text-primary-strong)">
              {reference.title}
            </p>
            <p className="mt-0.5 truncate text-[11px] text-(--color-text-row-meta)">
              {[reference.authors?.join(", "), reference.year, reference.venue].filter(Boolean).join(" · ")}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) px-3 py-2">
      <div className="text-[11px] font-medium uppercase tracking-[0.04em] text-(--color-text-quaternary)">
        {label}
      </div>
      <div className="mt-1 font-mono text-[18px] text-(--color-text-primary-strong)">
        {value}
      </div>
    </div>
  );
}

function FolderSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="surface-linear-card h-[184px] animate-shimmer" />
      ))}
    </div>
  );
}

function PublicationFeedSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-col gap-0">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="hairline-b flex gap-3 px-1 py-4 sm:px-3">
          <div className="size-10 flex-none rounded-full bg-(--color-bg-pill-inactive) animate-shimmer" />
          <div className="flex flex-1 flex-col gap-3">
            <div className="h-4 w-48 rounded bg-(--color-bg-pill-inactive) animate-shimmer" />
            <div className="h-6 w-3/4 rounded bg-(--color-bg-pill-inactive) animate-shimmer" />
            <div className="h-[240px] rounded-[8px] bg-(--color-bg-pill-inactive) animate-shimmer" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyPublicationFeed() {
  return (
    <div className="mx-auto flex h-64 max-w-[520px] flex-col items-center justify-center gap-3 text-center">
      <div className="flex size-10 items-center justify-center rounded-full bg-(--color-bg-pill-inactive) text-(--color-text-tertiary)">
        <Rss size={18} />
      </div>
      <p className="max-w-sm text-[13px] text-(--color-text-row-meta)">
        No published research papers match this view yet.
      </p>
    </div>
  );
}

function EmptyLibrary() {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
      <div className="flex size-10 items-center justify-center rounded-full bg-(--color-bg-pill-inactive) text-(--color-text-tertiary)">
        <Activity size={18} />
      </div>
      <p className="max-w-sm text-[13px] text-(--color-text-row-meta)">
        No generated paper artifacts are available yet.
      </p>
    </div>
  );
}
