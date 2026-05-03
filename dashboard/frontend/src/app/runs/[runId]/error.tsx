"use client";

import { RouteError } from "@/components/shell/route-error";

export default function RunDetailError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Run detail failed to load" />;
}
