import type { Metadata } from "next";
import ProjectsClient from "./projects-client";

// Iter 18 — RSC chrome over the client-rendered list. The page-level
// `metadata` export lets Next.js emit a per-route <title> on the server
// before any client JS evaluates; impossible while page.tsx itself was
// "use client". The client component owns all the interactive state
// (search, tab pills, create-modal) so the existing Playwright route
// mocks keep working unchanged.
export const metadata: Metadata = {
  title: "Projects — Plato",
  description: "All Plato projects across stages and statuses.",
};

export default function ProjectsPage() {
  return <ProjectsClient />;
}
