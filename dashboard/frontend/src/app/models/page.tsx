import type { Metadata } from "next";
import ModelsClient from "./models-client";

// Iter 18 — RSC chrome over the client-rendered model catalogue. The
// search / sort / filter UI stays a client island; the RSC just exports
// metadata so /models gets its own browser-tab title.
export const metadata: Metadata = {
  title: "Models — Plato",
  description:
    "LLM catalogue across providers — context window, pricing, and capabilities.",
};

export default function ModelsPage() {
  return <ModelsClient />;
}
