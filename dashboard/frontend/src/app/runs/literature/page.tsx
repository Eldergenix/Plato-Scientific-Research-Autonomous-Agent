"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import LiteratureClient from "./literature-client";

function PageInner() {
  const sp = useSearchParams();
  const runId = sp.get("runId") ?? "";
  return <LiteratureClient runId={runId} />;
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <PageInner />
    </Suspense>
  );
}
