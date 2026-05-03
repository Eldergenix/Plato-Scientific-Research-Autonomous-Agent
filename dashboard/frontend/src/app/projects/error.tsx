"use client";

import { RouteError } from "@/components/shell/route-error";

export default function ProjectsError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Projects list failed to load" />;
}
