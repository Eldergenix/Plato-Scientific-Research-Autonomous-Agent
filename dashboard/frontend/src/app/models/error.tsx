"use client";

import { RouteError } from "@/components/shell/route-error";

export default function ModelsError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Models failed to load" />;
}
