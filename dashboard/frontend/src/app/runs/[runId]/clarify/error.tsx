"use client";

import { RouteError } from "@/components/shell/route-error";

export default function ClarifyError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Clarify failed to load" />;
}
