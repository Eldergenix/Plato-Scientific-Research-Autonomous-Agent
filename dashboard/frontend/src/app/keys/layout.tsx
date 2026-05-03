import type { Metadata } from "next";
import { DashboardShell } from "@/components/shell/dashboard-shell";

export const metadata: Metadata = { title: "API Keys — Plato" };

export default function KeysLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
