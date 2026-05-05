import type { Metadata } from "next";
import ResearchClient from "./research-client";

export const metadata: Metadata = {
  title: "Research signals — Plato",
};

export default function Page({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  return <ResearchClient params={params} />;
}
