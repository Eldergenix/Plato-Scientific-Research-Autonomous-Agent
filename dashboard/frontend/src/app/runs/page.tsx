"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import RunDetailClient from "./run-detail-client";

// Static export can't enumerate every possible runId, so the route is
// non-dynamic and the runId travels in the query string: /runs?runId=xxx.
// useSearchParams must be wrapped in Suspense for the export build to pass.
function PageInner() {
  const sp = useSearchParams();
  const runId = sp.get("runId") ?? "";
  return <RunDetailClient runId={runId} />;
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <PageInner />
    </Suspense>
  );
}
