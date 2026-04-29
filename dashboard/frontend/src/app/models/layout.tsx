import { DashboardShell } from "@/components/shell/dashboard-shell";

export default function ModelsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
