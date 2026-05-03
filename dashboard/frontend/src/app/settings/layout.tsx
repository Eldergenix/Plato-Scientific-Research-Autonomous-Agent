import type { Metadata } from "next";
import { DashboardShell } from "@/components/shell/dashboard-shell";

// Server-side metadata for the /settings/* segment so the browser tab
// shows "Settings — Plato" instead of the generic root title. Sub-
// pages can override this with their own ``metadata`` export.
export const metadata: Metadata = {
  title: "Settings — Plato",
};

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
