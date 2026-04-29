import { DashboardShell } from "@/components/shell/dashboard-shell";

export default function CostsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
