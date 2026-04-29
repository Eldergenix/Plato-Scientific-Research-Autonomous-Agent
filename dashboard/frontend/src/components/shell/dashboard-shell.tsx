"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/shell/sidebar";
import { CommandPalette } from "@/components/shell/command-palette";
import { BottomBar } from "@/components/shell/bottom-bar";
import { CapabilitiesBanner } from "@/components/shell/capabilities-banner";
import { CreateProjectModal } from "@/components/projects/create-project-modal";
import { api } from "@/lib/api";

/**
 * Wrap any non-workspace page so it inherits the Linear sidebar + bottom bar.
 *
 * The home (workspace) page does NOT use this — it has a specialized
 * multi-pane layout with TopBar + tabs + AgentLogStream + StageDetail
 * navigation that lives at the page level. Other pages (Projects, Models,
 * Costs, Activity, Keys) opt in via this wrapper.
 */
export function DashboardShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [collapsed, setCollapsed] = React.useState(false);
  const [cmdOpen, setCmdOpen] = React.useState(false);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [caps, setCaps] = React.useState<{ is_demo: boolean; notes: string[] } | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    api.capabilities()
      .then((c) => !cancelled && setCaps({ is_demo: c.is_demo, notes: c.notes }))
      .catch(() => !cancelled && setCaps(null));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-(--color-bg-page) text-(--color-text-primary)">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
        onOpenCommand={() => setCmdOpen(true)}
        onCreateProject={() => setCreateOpen(true)}
      />

      <div className="flex-1 min-w-0 flex flex-col">
        {caps?.is_demo && <CapabilitiesBanner isDemo notes={caps.notes} />}

        <div className="flex-1 min-h-0 flex flex-col p-1.5 pl-0">
          <main
            className="flex-1 min-h-0 flex flex-col bg-(--color-bg-card) overflow-hidden"
            style={{
              border: "1px solid var(--color-border-card)",
              borderRadius: 12,
              boxShadow:
                "0 4px 4px -1px rgba(0, 0, 0, 0.04), 0 1px 1px rgba(0, 0, 0, 0.08)",
            }}
          >
            {children}
          </main>

          <BottomBar
            onAskAi={() => setCmdOpen(true)}
            onOpenHistory={() => {
              /* run history panel — Phase 4 */
            }}
          />
        </div>
      </div>

      <CommandPalette
        open={cmdOpen}
        onOpenChange={setCmdOpen}
        onCreateProject={() => setCreateOpen(true)}
      />

      <CreateProjectModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => router.push("/")}
      />
    </div>
  );
}
