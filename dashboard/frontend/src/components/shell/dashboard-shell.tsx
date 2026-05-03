"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";
import { Menu } from "lucide-react";
import { Sidebar } from "@/components/shell/sidebar";
import { CommandPalette } from "@/components/shell/command-palette";
import { BottomBar } from "@/components/shell/bottom-bar";
import { CapabilitiesBanner } from "@/components/shell/capabilities-banner";
import { CreateProjectModal } from "@/components/projects/create-project-modal";
import { Sheet } from "@/components/ui/sheet";
import { api } from "@/lib/api";

/**
 * Wrap any non-workspace page so it inherits the Linear sidebar + bottom bar.
 *
 * The home (workspace) page does NOT use this — it has a specialized
 * multi-pane layout with TopBar + tabs + AgentLogStream + StageDetail
 * navigation that lives at the page level. Other pages (Projects, Models,
 * Costs, Activity, Keys) opt in via this wrapper.
 *
 * Responsive layout:
 *   - md+ : sidebar is a permanent left rail (existing behaviour).
 *   - <md : sidebar is hidden behind a hamburger that opens the
 *           {@link Sheet} drawer. The drawer auto-closes on route change
 *           so users navigating from the sheet land on a clean page.
 */
export function DashboardShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = React.useState(false);
  const [cmdOpen, setCmdOpen] = React.useState(false);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [mobileNavOpen, setMobileNavOpen] = React.useState(false);
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

  // Auto-close the mobile drawer on route change so a navigation
  // initiated from inside the drawer doesn't leave it overlaying the
  // destination page.
  React.useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-(--color-bg-page) text-(--color-text-primary)">
      {/* Desktop sidebar — hidden below the md breakpoint so the
          hamburger drawer can take over without overlapping content. */}
      <div className="hidden md:flex">
        <Sidebar
          collapsed={collapsed}
          onToggle={() => setCollapsed((c) => !c)}
          onOpenCommand={() => setCmdOpen(true)}
          onCreateProject={() => setCreateOpen(true)}
        />
      </div>

      {/* Mobile drawer — same Sidebar component inside a Sheet. We
          override the panel width to a touch-friendly 280 so labels
          aren't truncated on phone-width viewports. */}
      <Sheet
        open={mobileNavOpen}
        onOpenChange={setMobileNavOpen}
        title="Navigation"
        srOnly
        side="left"
        hideCloseButton
        className="w-[280px]"
      >
        <Sidebar
          collapsed={false}
          onToggle={() => setMobileNavOpen(false)}
          onOpenCommand={() => {
            setMobileNavOpen(false);
            setCmdOpen(true);
          }}
          onCreateProject={() => {
            setMobileNavOpen(false);
            setCreateOpen(true);
          }}
        />
      </Sheet>

      <div className="flex-1 min-w-0 flex flex-col">
        {/* Mobile-only sticky header with hamburger trigger. The
            md:hidden breakpoint matches the desktop-sidebar visibility
            so the two never coexist on screen. */}
        <div
          className="flex h-12 items-center gap-2 px-3 hairline-b bg-(--color-bg-marketing) md:hidden"
          data-testid="mobile-shell-header"
        >
          <button
            type="button"
            aria-label="Open navigation"
            data-testid="mobile-nav-trigger"
            onClick={() => setMobileNavOpen(true)}
            className="size-8 inline-flex items-center justify-center rounded-[6px] text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)"
          >
            <Menu size={16} strokeWidth={1.75} />
          </button>
          <span className="text-[13px] font-medium text-(--color-text-primary)">
            Plato
          </span>
        </div>

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
