"use client";

import { RouteError } from "@/components/shell/route-error";

export default function KeysError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Keys page failed to load" />;
}
