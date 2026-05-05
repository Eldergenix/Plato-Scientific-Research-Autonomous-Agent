import type { Metadata } from "next";
import LiteratureClient from "./literature-client";

export const metadata: Metadata = {
  title: "Literature — Plato",
};

export default function Page({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  return <LiteratureClient params={params} />;
}
