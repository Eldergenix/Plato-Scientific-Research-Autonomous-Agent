"use client";

import * as React from "react";
import {
  AlertCircle,
  CheckCircle2,
  ClipboardCheck,
  FileCode2,
  KeyRound,
  Link2,
  Loader2,
  Network,
  Plus,
  RefreshCw,
  Search,
  Server,
  Sparkles,
  Trash2,
  Wrench,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { TabPills } from "@/components/shell/tab-pills";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import {
  api,
  type McpServerInfo,
  type McpStatus,
  type McpTransport,
  type ToolInfo,
  type ToolingState,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type TabId = "tools" | "mcp" | "custom";

const PAGE_TABS: Array<{ id: TabId; label: string }> = [
  { id: "tools", label: "Tools" },
  { id: "mcp", label: "MCP" },
  { id: "custom", label: "Custom MCP" },
];

const FIELD_CLASS = cn(
  "h-9 rounded-[6px] border border-(--color-border-pill) bg-(--color-bg-card) px-2.5",
  "text-[13px] text-(--color-text-primary) shadow-[var(--shadow-glass)] transition-colors",
  "placeholder:text-(--color-text-quaternary-spec)",
  "hover:border-(--color-border-strong) focus:border-(--color-brand-indigo) focus:outline-none",
);

function activeCount(items: Array<{ enabled: boolean }>): number {
  return items.filter((item) => item.enabled).length;
}

function titleize(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function categoryTone(category: string): "neutral" | "indigo" | "green" | "amber" | "lavender" {
  if (category === "retrieval" || category === "planning") return "indigo";
  if (category === "validation" || category === "security") return "green";
  if (category === "scientific_analysis" || category === "execution") return "amber";
  if (category === "docs" || category === "knowledge") return "lavender";
  return "neutral";
}

function statusTone(status: McpStatus): "neutral" | "green" | "amber" | "red" {
  if (status === "ok") return "green";
  if (status === "error") return "red";
  if (status === "inactive") return "neutral";
  return "amber";
}

function statusIcon(status: McpStatus): LucideIcon {
  if (status === "ok") return CheckCircle2;
  if (status === "error") return XCircle;
  if (status === "inactive") return AlertCircle;
  return RefreshCw;
}

function iconForTool(tool: ToolInfo): LucideIcon {
  if (tool.category === "retrieval") return Search;
  if (tool.category === "validation") return ClipboardCheck;
  if (tool.permissions.includes("filesystem_write")) return FileCode2;
  if (tool.permissions.includes("network")) return Network;
  if (tool.permissions.includes("llm")) return Sparkles;
  return Wrench;
}

export default function ToolsClient() {
  const [activeTab, setActiveTab] = React.useState<TabId>("tools");
  const [state, setState] = React.useState<ToolingState | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busyIds, setBusyIds] = React.useState<Set<string>>(new Set());

  const setBusy = React.useCallback((id: string, busy: boolean) => {
    setBusyIds((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const refresh = React.useCallback(async () => {
    setError(null);
    try {
      setState(await api.getTooling());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tooling configuration.");
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const patchTool = React.useCallback((tool: ToolInfo) => {
    setState((prev) => prev ? {
      ...prev,
      tools: prev.tools.map((item) => (item.id === tool.id ? tool : item)),
    } : prev);
  }, []);

  const patchMcp = React.useCallback((server: McpServerInfo) => {
    setState((prev) => {
      if (!prev) return prev;
      if (server.built_in) {
        return {
          ...prev,
          mcp_servers: prev.mcp_servers.map((item) => (item.id === server.id ? server : item)),
        };
      }
      return {
        ...prev,
        custom_mcp_servers: prev.custom_mcp_servers.map((item) => (item.id === server.id ? server : item)),
      };
    });
  }, []);

  const toggleTool = React.useCallback(async (tool: ToolInfo, enabled: boolean) => {
    const busyKey = `tool:${tool.id}`;
    setBusy(busyKey, true);
    setError(null);
    try {
      patchTool(await api.setToolEnabled(tool.id, enabled));
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to update ${tool.name}.`);
    } finally {
      setBusy(busyKey, false);
    }
  }, [patchTool, setBusy]);

  const toggleMcp = React.useCallback(async (server: McpServerInfo, enabled: boolean) => {
    const busyKey = `mcp:${server.id}`;
    setBusy(busyKey, true);
    setError(null);
    try {
      patchMcp(await api.setMcpEnabled(server.id, enabled));
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to update ${server.name}.`);
    } finally {
      setBusy(busyKey, false);
    }
  }, [patchMcp, setBusy]);

  const testMcp = React.useCallback(async (server: McpServerInfo) => {
    const busyKey = `test:${server.id}`;
    setBusy(busyKey, true);
    setError(null);
    try {
      patchMcp(await api.testMcpServer(server.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to test ${server.name}.`);
    } finally {
      setBusy(busyKey, false);
    }
  }, [patchMcp, setBusy]);

  const addCustomServer = React.useCallback((server: McpServerInfo) => {
    setState((prev) => prev ? {
      ...prev,
      custom_mcp_servers: [server, ...prev.custom_mcp_servers],
    } : prev);
  }, []);

  const removeCustomServer = React.useCallback((serverId: string) => {
    setState((prev) => prev ? {
      ...prev,
      custom_mcp_servers: prev.custom_mcp_servers.filter((server) => server.id !== serverId),
    } : prev);
  }, []);

  const tools = state?.tools ?? [];
  const mcpServers = state?.mcp_servers ?? [];
  const customServers = state?.custom_mcp_servers ?? [];

  return (
    <div className="flex h-full min-h-0 bg-(--color-bg-page) px-3 py-4 sm:px-6 sm:py-8">
      <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col gap-4">
        <header className="surface-linear-card p-4 sm:p-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Wrench size={18} strokeWidth={1.75} className="text-(--color-brand-hover)" />
                <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong) sm:text-[24px]">
                  Tools
                </h1>
              </div>
              <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
                {activeCount(tools)} built-in tools, {activeCount(mcpServers)} MCP servers, and {activeCount(customServers)} custom MCP entries active.
              </p>
            </div>
            <TabPills
              tabs={PAGE_TABS}
              activeId={activeTab}
              onSelect={(id) => setActiveTab(id as TabId)}
              ariaLabel="Tools page tabs"
              className="shrink-0"
            />
          </div>
        </header>

        {error ? (
          <div className="surface-linear-card border-(--color-status-red)/30 px-4 py-3 text-[12.5px] text-(--color-status-red)">
            {error}
          </div>
        ) : null}

        {!state ? (
          <section className="surface-linear-card flex min-h-64 items-center justify-center text-[13px] text-(--color-text-tertiary-spec)">
            <Loader2 size={16} className="mr-2 animate-spin" />
            Loading tooling configuration...
          </section>
        ) : null}

        {state && activeTab === "tools" ? (
          <ToolRegistryPanel
            tools={tools}
            busyIds={busyIds}
            onToggle={toggleTool}
          />
        ) : null}

        {state && activeTab === "mcp" ? (
          <McpRegistryPanel
            title="MCP servers"
            subtitle="Bundled MCP servers provided by Plato and validated through the MCP protocol."
            servers={mcpServers}
            busyIds={busyIds}
            onToggle={toggleMcp}
            onTest={testMcp}
          />
        ) : null}

        {state && activeTab === "custom" ? (
          <CustomMcpPanel
            servers={customServers}
            busyIds={busyIds}
            onAdd={addCustomServer}
            onRemove={removeCustomServer}
            onToggle={toggleMcp}
            onTest={testMcp}
            setBusy={setBusy}
            setError={setError}
          />
        ) : null}
      </div>
    </div>
  );
}

function ToolRegistryPanel({
  tools,
  busyIds,
  onToggle,
}: {
  tools: ToolInfo[];
  busyIds: Set<string>;
  onToggle: (tool: ToolInfo, enabled: boolean) => void;
}) {
  return (
    <section className="surface-linear-card flex min-h-0 flex-1 flex-col overflow-hidden">
      <PanelHeader
        title="Built-in tools"
        subtitle="Live tools registered in Plato's Python tool registry."
        meta={`${activeCount(tools)} of ${tools.length} active`}
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        {tools.map((tool, index) => (
          <ToolRow
            key={tool.id}
            tool={tool}
            busy={busyIds.has(`tool:${tool.id}`)}
            onCheckedChange={(next) => onToggle(tool, next)}
            className={index > 0 ? "border-t border-(--color-border-card)" : ""}
          />
        ))}
      </div>
    </section>
  );
}

function ToolRow({
  tool,
  busy,
  onCheckedChange,
  className,
}: {
  tool: ToolInfo;
  busy: boolean;
  onCheckedChange: (next: boolean) => void;
  className?: string;
}) {
  const Icon = iconForTool(tool);
  const permissions = tool.permissions.length ? tool.permissions.join(", ") : "no permission gates";
  return (
    <div className={cn("flex flex-col gap-3 px-4 py-3 transition-colors hover:bg-[rgba(255,255,255,0.02)] sm:flex-row sm:items-center sm:justify-between", className)}>
      <div className="flex min-w-0 items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-[8px] bg-(--color-bg-pill-inactive) text-(--color-text-tertiary-spec)">
          <Icon size={15} strokeWidth={1.7} />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13.5px] font-[510] text-(--color-text-primary-strong)">
              {titleize(tool.name)}
            </h3>
            <Pill tone={categoryTone(tool.category)}>{tool.category}</Pill>
          </div>
          <p className="mt-1 text-[12.5px] text-(--color-text-tertiary-spec)">
            {tool.description}
          </p>
          <p className="mt-1 font-mono text-[11px] text-(--color-text-quaternary-spec)">
            {tool.name} · {permissions}
          </p>
        </div>
      </div>
      <ActivationSwitch
        checked={tool.enabled}
        disabled={busy}
        onCheckedChange={onCheckedChange}
        label={`${tool.name} activation`}
      />
    </div>
  );
}

function McpRegistryPanel({
  title,
  subtitle,
  servers,
  busyIds,
  onToggle,
  onTest,
}: {
  title: string;
  subtitle: string;
  servers: McpServerInfo[];
  busyIds: Set<string>;
  onToggle: (server: McpServerInfo, enabled: boolean) => void;
  onTest: (server: McpServerInfo) => void;
}) {
  return (
    <section className="surface-linear-card overflow-hidden">
      <PanelHeader
        title={title}
        subtitle={subtitle}
        meta={`${activeCount(servers)} of ${servers.length} active`}
      />
      <div>
        {servers.map((server, index) => (
          <McpRow
            key={server.id}
            server={server}
            toggleBusy={busyIds.has(`mcp:${server.id}`)}
            testBusy={busyIds.has(`test:${server.id}`)}
            onToggle={onToggle}
            onTest={onTest}
            className={index > 0 ? "border-t border-(--color-border-card)" : ""}
          />
        ))}
      </div>
    </section>
  );
}

function McpRow({
  server,
  toggleBusy,
  testBusy,
  onToggle,
  onTest,
  onRemove,
  className,
}: {
  server: McpServerInfo;
  toggleBusy: boolean;
  testBusy: boolean;
  onToggle: (server: McpServerInfo, enabled: boolean) => void;
  onTest: (server: McpServerInfo) => void;
  onRemove?: (server: McpServerInfo) => void;
  className?: string;
}) {
  const StatusIcon = statusIcon(server.status);
  const toolsPreview = server.tools.length ? server.tools.slice(0, 5).join(", ") : "No tools listed yet";
  return (
    <div className={cn("flex flex-col gap-3 px-4 py-3 transition-colors hover:bg-[rgba(255,255,255,0.02)] lg:flex-row lg:items-center lg:justify-between", className)}>
      <div className="flex min-w-0 items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-[8px] bg-(--color-bg-pill-inactive) text-(--color-text-tertiary-spec)">
          {server.built_in ? <Server size={15} strokeWidth={1.75} /> : <Link2 size={15} strokeWidth={1.75} />}
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13.5px] font-[510] text-(--color-text-primary-strong)">
              {server.name}
            </h3>
            <Pill tone="indigo">{server.transport}</Pill>
            <Pill tone={statusTone(server.status)}>
              <StatusIcon size={11} strokeWidth={1.75} />
              {server.status}
            </Pill>
            {server.auth_configured ? (
              <span className="inline-flex items-center gap-1 text-[11.5px] text-(--color-text-tertiary-spec)">
                <KeyRound size={12} strokeWidth={1.75} />
                auth configured
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-[12.5px] text-(--color-text-tertiary-spec)">
            {server.description || "Custom MCP server"}
          </p>
          <p className="mt-1 truncate font-mono text-[11px] text-(--color-text-quaternary-spec)">
            {server.target}
          </p>
          <p className="mt-1 text-[11px] text-(--color-text-quaternary-spec)">
            {server.status_message}
          </p>
          {!server.status_message && server.tools.length ? (
            <p className="mt-1 truncate font-mono text-[11px] text-(--color-text-quaternary-spec)">
              {toolsPreview}{server.tools.length > 5 ? ` +${server.tools.length - 5} more` : ""}
            </p>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-2 lg:shrink-0">
        <Button
          type="button"
          variant="subtle"
          size="sm"
          disabled={testBusy}
          onClick={() => onTest(server)}
        >
          {testBusy ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} strokeWidth={1.75} />}
          Test
        </Button>
        <ActivationSwitch
          checked={server.enabled}
          disabled={toggleBusy}
          onCheckedChange={(next) => onToggle(server, next)}
          label={`${server.name} activation`}
        />
        {onRemove ? (
          <Button
            type="button"
            variant="subtle"
            size="iconSm"
            aria-label={`Remove ${server.name}`}
            onClick={() => onRemove(server)}
          >
            <Trash2 size={13} strokeWidth={1.75} />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function CustomMcpPanel({
  servers,
  busyIds,
  onAdd,
  onRemove,
  onToggle,
  onTest,
  setBusy,
  setError,
}: {
  servers: McpServerInfo[];
  busyIds: Set<string>;
  onAdd: (server: McpServerInfo) => void;
  onRemove: (serverId: string) => void;
  onToggle: (server: McpServerInfo, enabled: boolean) => void;
  onTest: (server: McpServerInfo) => void;
  setBusy: (id: string, busy: boolean) => void;
  setError: (message: string | null) => void;
}) {
  const [name, setName] = React.useState("");
  const [transport, setTransport] = React.useState<McpTransport>("stdio");
  const [target, setTarget] = React.useState("");
  const [auth, setAuth] = React.useState("");
  const [activate, setActivate] = React.useState(false);

  const canSubmit = name.trim().length > 0 && target.trim().length > 0;

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy("custom:create", true);
    setError(null);
    try {
      const server = await api.createCustomMcpServer({
        name: name.trim(),
        transport,
        target: target.trim(),
        auth: auth.trim(),
        enabled: activate,
      });
      onAdd(server);
      setName("");
      setTransport("stdio");
      setTarget("");
      setAuth("");
      setActivate(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add custom MCP server.");
    } finally {
      setBusy("custom:create", false);
    }
  };

  const remove = async (server: McpServerInfo) => {
    const busyKey = `remove:${server.id}`;
    setBusy(busyKey, true);
    setError(null);
    try {
      await api.deleteCustomMcpServer(server.id);
      onRemove(server.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to remove ${server.name}.`);
    } finally {
      setBusy(busyKey, false);
    }
  };

  return (
    <div className="space-y-4">
      <section className="surface-linear-card p-4 sm:p-5">
        <div className="mb-4 flex items-start gap-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-[8px] bg-(--color-bg-pill-inactive) text-(--color-brand-hover)">
            <Plus size={15} strokeWidth={1.75} />
          </span>
          <div>
            <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
              Add custom MCP
            </h2>
            <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
              Register a stdio command, streamable HTTP endpoint, or SSE endpoint for this user.
            </p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_140px_1.4fr]">
          <label className="flex flex-col gap-1.5">
            <span className="text-[11.5px] font-medium text-(--color-text-tertiary-spec)">
              Server name
            </span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Internal research MCP"
              className={FIELD_CLASS}
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-[11.5px] font-medium text-(--color-text-tertiary-spec)">
              Transport
            </span>
            <select
              value={transport}
              onChange={(event) => setTransport(event.target.value as McpTransport)}
              className={FIELD_CLASS}
            >
              <option value="stdio">stdio</option>
              <option value="http">http</option>
              <option value="sse">sse</option>
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-[11.5px] font-medium text-(--color-text-tertiary-spec)">
              Command or URL
            </span>
            <input
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              placeholder={transport === "stdio" ? "python -m my_mcp_server" : "https://mcp.example.com/mcp"}
              className={FIELD_CLASS}
            />
          </label>

          <label className="flex flex-col gap-1.5 lg:col-span-3">
            <span className="text-[11.5px] font-medium text-(--color-text-tertiary-spec)">
              Environment or headers
            </span>
            <textarea
              value={auth}
              onChange={(event) => setAuth(event.target.value)}
              placeholder={transport === "stdio" ? "API_KEY=..." : "Authorization: Bearer ..."}
              className={cn(FIELD_CLASS, "min-h-20 resize-y py-2 font-mono text-[12px]")}
            />
          </label>

          <label className="flex items-center gap-2 lg:col-span-3">
            <input
              type="checkbox"
              checked={activate}
              onChange={(event) => setActivate(event.target.checked)}
              className="size-4 accent-(--color-brand-indigo)"
            />
            <span className="text-[12px] text-(--color-text-tertiary-spec)">
              Activate and validate after adding
            </span>
          </label>

          <div className="lg:col-span-3">
            <Button type="submit" variant="primary" size="md" disabled={!canSubmit || busyIds.has("custom:create")}>
              {busyIds.has("custom:create") ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} strokeWidth={1.75} />}
              Add server
            </Button>
          </div>
        </form>
      </section>

      <section className="surface-linear-card overflow-hidden">
        <PanelHeader
          title="Custom MCP servers"
          subtitle="User-owned MCP servers persisted by the backend."
          meta={`${activeCount(servers)} of ${servers.length} active`}
        />

        {servers.length === 0 ? (
          <div className="px-4 py-10 text-center">
            <Server size={22} strokeWidth={1.75} className="mx-auto text-(--color-text-quaternary-spec)" />
            <p className="mt-3 text-[13px] text-(--color-text-primary)">
              No custom MCP servers yet.
            </p>
          </div>
        ) : (
          <div>
            {servers.map((server, index) => (
              <McpRow
                key={server.id}
                server={server}
                toggleBusy={busyIds.has(`mcp:${server.id}`)}
                testBusy={busyIds.has(`test:${server.id}`)}
                onToggle={onToggle}
                onTest={onTest}
                onRemove={(item) => void remove(item)}
                className={cn(index > 0 ? "border-t border-(--color-border-card)" : "", busyIds.has(`remove:${server.id}`) ? "opacity-50" : "")}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function PanelHeader({
  title,
  subtitle,
  meta,
}: {
  title: string;
  subtitle: string;
  meta: string;
}) {
  return (
    <div className="hairline-b flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-baseline sm:justify-between">
      <div>
        <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
          {title}
        </h2>
        <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
          {subtitle}
        </p>
      </div>
      <span className="text-[11.5px] text-(--color-text-tertiary-spec)">
        {meta}
      </span>
    </div>
  );
}

function ActivationSwitch({
  checked,
  disabled = false,
  onCheckedChange,
  label,
}: {
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (next: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "inline-flex h-5 w-9 shrink-0 items-center rounded-full border px-0.5 transition-[background-color,border-color,justify-content] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive) disabled:cursor-wait disabled:opacity-60",
        checked
          ? "border-(--color-brand-indigo) bg-(--color-brand-indigo)"
          : "border-(--color-border-pill) bg-(--color-bg-pill-inactive)",
        checked ? "justify-end" : "justify-start",
      )}
    >
      <span
        className={cn(
          "flex size-4 items-center justify-center rounded-full bg-white text-[9px] font-medium shadow-[var(--shadow-card)]",
          checked ? "text-(--color-brand-indigo)" : "text-(--color-text-quaternary-spec)",
        )}
        aria-hidden
      >
        {disabled ? <Loader2 size={9} className="animate-spin" /> : null}
      </span>
      <span className="sr-only">{checked ? "Active" : "Inactive"}</span>
    </button>
  );
}
