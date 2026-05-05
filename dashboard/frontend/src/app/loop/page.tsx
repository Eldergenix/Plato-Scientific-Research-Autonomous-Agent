import type { Metadata } from "next";
import LoopClient from "./loop-client";

export const metadata: Metadata = {
  title: "Autonomous loop — Plato",
  description: "Run Plato unattended under a time, iteration, and cost budget.",
};

export default function LoopPage() {
  return <LoopClient />;
}
