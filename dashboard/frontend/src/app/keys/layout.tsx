import { DashboardShell } from "@/components/shell/dashboard-shell";

export default function KeysLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
