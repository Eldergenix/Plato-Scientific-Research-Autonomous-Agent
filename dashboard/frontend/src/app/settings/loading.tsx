import { RouteLoading } from "@/components/shell/route-loading";

// Streamed by Next.js while /settings/* segments hydrate. Without
// this file the user sees a blank screen during the route transition.
export default function Loading() {
  return <RouteLoading label="Loading settings…" />;
}
