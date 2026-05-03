import type { Metadata } from "next";

// /login intentionally does NOT mount DashboardShell (no sidebar /
// topbar / cost meter). It's the standalone auth surface — keeping
// it shell-free avoids forcing the user to wait for the rest of the
// dashboard to hydrate just to type a user id.
export const metadata: Metadata = {
  title: "Sign in — Plato",
};

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
