import type { Metadata } from "next";
import { DashboardShell } from "@/components/shell/dashboard-shell";

export const metadata: Metadata = { title: "Projects — Plato" };

export default function ProjectsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
