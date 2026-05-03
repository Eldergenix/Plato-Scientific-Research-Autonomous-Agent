"use client";

import { RouteError } from "@/components/shell/route-error";

export default function ActivityError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Activity feed failed to load" />;
}
