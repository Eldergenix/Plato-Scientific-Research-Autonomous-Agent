"use client";

// Next.js renders this when any /settings/* route component throws.
// Keeping the segment-level scope means a crash in /settings/domains
// doesn't take down /settings/executors or the sidebar shell.
import { RouteError } from "@/components/shell/route-error";

export default function SettingsError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} label="Settings page failed to load" />;
}
