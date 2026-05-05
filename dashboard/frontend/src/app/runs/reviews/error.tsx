"use client";

import { RouteError } from "@/components/shell/route-error";

export default function ReviewsError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Reviews failed to load" />;
}
