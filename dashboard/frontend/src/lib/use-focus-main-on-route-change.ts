"use client";

import * as React from "react";

// Form-control nodes whose focus we must not steal. INPUT covers most
// text fields, TEXTAREA covers multiline notes, and SELECT covers
// native dropdowns. contenteditable handles rich-text editors (Monaco
// has its own focus management but uses contenteditable on the input
// surface). We intentionally do not include BUTTON — those should
// yield to the route change since the click handler has already run.
const FORM_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

function isUserTypingInForm(): boolean {
  if (typeof document === "undefined") return false;
  const active = document.activeElement;
  if (!active) return false;
  if (FORM_TAGS.has(active.tagName)) return true;
  if (active instanceof HTMLElement && active.isContentEditable) return true;
  return false;
}

/**
 * Move keyboard focus to the page's `<main>` landmark whenever the
 * pathname changes. Without this, sidebar-driven navigation leaves
 * focus on the sidebar link, forcing keyboard users to Tab through
 * the entire sidebar again on every page change.
 *
 * The `<main>` element must declare `tabIndex={-1}` so we can focus
 * it programmatically. We use `preventScroll` so the focus shift
 * doesn't yank the viewport.
 *
 * Skipped while the user is typing in a form control — we don't want
 * to interrupt mid-type if a route change happens to fire in the
 * background (e.g. an external prefetch / NavigationApi update).
 */
export function useFocusMainOnRouteChange(pathname: string): void {
  // Track first render so we don't steal focus on initial mount —
  // browsers already place focus correctly on first load (usually
  // body or whatever has autofocus), and stealing it here would
  // override that.
  const isFirstRenderRef = React.useRef(true);

  React.useEffect(() => {
    if (isFirstRenderRef.current) {
      isFirstRenderRef.current = false;
      return;
    }
    if (isUserTypingInForm()) return;
    const main = document.querySelector<HTMLElement>("main");
    main?.focus({ preventScroll: true });
  }, [pathname]);
}
