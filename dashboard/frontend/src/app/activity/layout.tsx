import { DashboardShell } from "@/components/shell/dashboard-shell";

export default function ActivityLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
