import type { Metadata } from "next";
import { DashboardShell } from "@/components/shell/dashboard-shell";

export const metadata: Metadata = { title: "Costs — Plato" };

export default function CostsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
