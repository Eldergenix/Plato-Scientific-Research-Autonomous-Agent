"use client";

import { RouteError } from "@/components/shell/route-error";

export default function RootError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Something went wrong" />;
}
