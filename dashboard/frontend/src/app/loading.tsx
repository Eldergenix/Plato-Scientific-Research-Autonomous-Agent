import { RouteLoading } from "@/components/shell/route-loading";

// Next.js automatically renders this segment while the root layout's child
// component tree is suspending. Without it, the very first render of any
// /<route> shows a blank document until the JS bundle hydrates — a 200ms+
// FOUC on slow networks.
export default function Loading() {
  return <RouteLoading label="Loading workspace…" />;
}
