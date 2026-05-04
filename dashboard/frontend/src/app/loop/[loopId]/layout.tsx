import type { Metadata } from "next";

interface Params {
  loopId: string;
}

export function generateStaticParams(): Params[] {
  return [];
}

export const dynamicParams = false;

// Server-side metadata so the browser tab + history entry name the
// loop instead of the parent layout's "Autonomous loops — Plato".
export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { loopId } = await params;
  return {
    title: `Loop ${loopId} — Plato`,
  };
}

export default function LoopDetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
