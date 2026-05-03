import type { Metadata } from "next";
import { DashboardShell } from "@/components/shell/dashboard-shell";

export const metadata: Metadata = { title: "Models — Plato" };

export default function ModelsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
