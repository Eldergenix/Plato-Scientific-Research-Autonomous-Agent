"use client";

import { RouteError } from "@/components/shell/route-error";

export default function LiteratureError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Literature failed to load" />;
}
