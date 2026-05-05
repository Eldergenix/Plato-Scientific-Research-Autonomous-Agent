"use client";

import * as React from "react";

/**
 * Re-fire the supplied refresh callback when the browser tab regains
 * visibility (user comes back from another tab) AND optionally on a
 * polling interval while the document is visible.
 *
 * Iter-11 motivation: the per-run-detail pages (research, literature,
 * citations, reviews) used to fetch once at mount and never re-fetch.
 * If a run finished while the page was open, the user saw stale data
 * forever. The page-level ``useProject`` SSE subscription doesn't
 * cover these sub-pages because they only know ``runId`` (not ``pid``)
 * and don't share the project hook's state.
 *
 * The pragmatic fix is a focus + interval refresh — covers the
 * common case (user kicks off a run, navigates away, comes back to
 * check) without standing up an SSE subscription per sub-page.
 */
export function useFocusRefresh(
  refresh: () => void,
  options: {
    /** ms; ``null`` disables interval polling. Defaults to 15 000. */
    intervalMs?: number | null;
    /** Whether to fire once on mount (besides the initial render). */
    runOnMount?: boolean;
    /** When false, neither the focus listener nor the interval runs. */
    enabled?: boolean;
  } = {},
): void {
  const { intervalMs = 15_000, runOnMount = false, enabled = true } = options;

  // Stash the callback in a ref so the effect can read the latest
  // closure without re-subscribing every render.
  const cbRef = React.useRef(refresh);
  React.useEffect(() => {
    cbRef.current = refresh;
  }, [refresh]);

  React.useEffect(() => {
    if (!enabled || typeof window === "undefined") return;
    let timer: ReturnType<typeof setInterval> | null = null;

    const onVisible = () => {
      if (document.visibilityState === "visible") {
        cbRef.current();
      }
    };
    document.addEventListener("visibilitychange", onVisible);

    if (intervalMs && intervalMs > 0) {
      timer = setInterval(() => {
        if (document.visibilityState === "visible") {
          cbRef.current();
        }
      }, intervalMs);
    }
    if (runOnMount) {
      cbRef.current();
    }
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      if (timer !== null) clearInterval(timer);
    };
  }, [enabled, intervalMs, runOnMount]);
}
