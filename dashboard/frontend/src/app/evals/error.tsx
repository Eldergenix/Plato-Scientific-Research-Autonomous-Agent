"use client";

import { RouteError } from "@/components/shell/route-error";

export default function EvalsError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Evals page failed to load" />;
}
