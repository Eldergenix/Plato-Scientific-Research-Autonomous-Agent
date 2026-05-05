import { RouteLoading } from "@/components/shell/route-loading";

// Iter-10: Next.js streams this while /keys hydrates. Without this
// file the heavyweight KeysClient island left a blank body on first
// route transition.
export default function Loading() {
  return <RouteLoading label="Loading keys…" />;
}
