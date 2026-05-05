import LoopDetailClient from "./client";

export async function generateStaticParams() {
  return [{ loopId: "_" }];
}

export default function Page() {
  return <LoopDetailClient />;
}
