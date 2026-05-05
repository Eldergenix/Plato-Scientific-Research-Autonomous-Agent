import type { Metadata } from "next";
import ActivityClient from "./activity-client";

export const metadata: Metadata = {
  title: "Activity — Plato",
  description: "Recent runs, agent activity, and event timeline.",
};

export default function ActivityPage() {
  return <ActivityClient />;
}
