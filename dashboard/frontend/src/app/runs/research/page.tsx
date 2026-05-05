"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import ResearchClient from "./research-client";

function PageInner() {
  const sp = useSearchParams();
  const runId = sp.get("runId") ?? "";
  return <ResearchClient runId={runId} />;
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <PageInner />
    </Suspense>
  );
}
