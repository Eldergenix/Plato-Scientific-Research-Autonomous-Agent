import type { Metadata } from "next";
import EvalsClient from "./evals-client";

export const metadata: Metadata = {
  title: "Evals — Plato",
  description: "Aggregated evaluation metrics across the most recent benchmark runs.",
};

export default function EvalsPage() {
  return <EvalsClient />;
}
