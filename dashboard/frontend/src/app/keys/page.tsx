import type { Metadata } from "next";
import KeysClient from "./keys-client";

// Iter 18 — RSC chrome over the client-rendered key-management UI.
// The page-level `metadata` export lets Next.js emit a per-route <title>
// on the server. Client island owns key fetch / save / clear flows.
export const metadata: Metadata = {
  title: "API keys — Plato",
  description:
    "Per-provider LLM API keys. Stored locally on the dashboard host.",
};

export default function KeysPage() {
  return <KeysClient />;
}
