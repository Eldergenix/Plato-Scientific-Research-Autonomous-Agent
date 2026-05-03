"use client";

import { RouteError } from "@/components/shell/route-error";

export default function LoopError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Loop dashboard failed to load" />;
}
