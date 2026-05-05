"use client";

import { RouteError } from "@/components/shell/route-error";

export default function DomainsError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Domains failed to load" />;
}
