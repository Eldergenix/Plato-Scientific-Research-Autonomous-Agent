import { DashboardShell } from "@/components/shell/dashboard-shell";

export default function LoopLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
