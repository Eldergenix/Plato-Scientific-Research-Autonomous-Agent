import { DashboardShell } from "@/components/shell/dashboard-shell";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
