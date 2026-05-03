import type { Metadata } from "next";

interface Params {
  runId: string;
}

// Server-side metadata so the browser tab + history entry name the
// run instead of the generic "Plato — Scientific Research Dashboard"
// title set by the root layout. Runs through Next.js's metadata
// merging — only the title field is overridden here.
export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { runId } = await params;
  return {
    title: `Run ${runId} — Plato`,
  };
}

export default function RunDetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
