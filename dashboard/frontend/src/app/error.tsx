"use client";

import { RouteError } from "@/components/shell/route-error";

// Next.js renders this when any child route throws a runtime error during
// render or in a Server Component. Using the shared RouteError component
// keeps the recovery UX consistent across the app — a single Try Again
// button that resets the boundary instead of forcing a full page reload.
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError error={error} reset={reset} />;
}
