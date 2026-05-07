import type { Metadata } from "next";
import { DashboardShell } from "@/components/shell/dashboard-shell";

export const metadata: Metadata = { title: "Tools — Plato" };

export default function ToolsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
