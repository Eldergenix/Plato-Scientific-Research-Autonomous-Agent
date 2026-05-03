import type { Metadata } from "next";
import CostsClient from "./costs-client";

// Iter 18 — RSC chrome over the client-rendered cost dashboard. Charts,
// filters, and CSV download stay in the client island; the RSC just
// emits the per-route metadata.
export const metadata: Metadata = {
  title: "Costs — Plato",
  description:
    "LLM token spend by provider, model, run, and project — over the active billing window.",
};

export default function CostsPage() {
  return <CostsClient />;
}
