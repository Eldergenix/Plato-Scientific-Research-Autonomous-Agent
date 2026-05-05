import type { Metadata } from "next";
import RunDetailClient from "./run-detail-client";

export const metadata: Metadata = {
  title: "Run details — Plato",
};

export default function Page({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  return <RunDetailClient params={params} />;
}
