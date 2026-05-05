"use client";

import { RouteError } from "@/components/shell/route-error";

export default function LicensesError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Licenses failed to load" />;
}
