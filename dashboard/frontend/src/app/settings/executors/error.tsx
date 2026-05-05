"use client";

import { RouteError } from "@/components/shell/route-error";

export default function ExecutorsError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Executors failed to load" />;
}
