"use client";

import { RouteError } from "@/components/shell/route-error";

export default function CostsError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Cost ledger failed to load" />;
}
