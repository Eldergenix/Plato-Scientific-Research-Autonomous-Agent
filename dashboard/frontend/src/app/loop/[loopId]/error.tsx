"use client";

import { RouteError } from "@/components/shell/route-error";

export default function LoopDetailError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Loop detail failed to load" />;
}
