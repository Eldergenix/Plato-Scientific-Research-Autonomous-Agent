import type { Metadata } from "next";
import ToolsClient from "./tools-client";

export const metadata: Metadata = {
  title: "Tools — Plato",
  description: "Manage built-in tools, bundled MCP servers, and custom MCP entries.",
};

export default function ToolsPage() {
  return <ToolsClient />;
}
