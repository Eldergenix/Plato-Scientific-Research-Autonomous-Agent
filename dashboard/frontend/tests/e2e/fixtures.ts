import { test as base, expect, type Page, type Route } from "@playwright/test";

/**
 * Plato e2e fixture: ships a safe default ``/auth/me`` mock so every
 * test that visits an auth-gated page lands on the dashboard rather
 * than getting bounced to ``/login``.
 *
 * Why this exists: when a real Plato backend happens to be running on
 * ``http://127.0.0.1:7878``, its ``/auth/me`` returns
 * ``{auth_required: true}``, which the dashboard's ``AuthProvider``
 * (see ``src/components/auth/auth-context.tsx``) interprets as "redirect
 * to /login". That made the entire e2e suite flake whenever a sibling
 * worktree had the dashboard backend warm. The fixture preempts that
 * by intercepting the call before the request reaches the wire and
 * returning the un-gated shape.
 *
 * Per-spec overrides still work because Playwright matches the
 * **last-registered** handler first. Tests that exercise the auth flow
 * itself (``auth.spec.ts``) install a broader ``/api/v1/auth/`` regex
 * AFTER fixture setup; that handler shadows ours for those tests
 * without any extra wiring.
 *
 * Import this file's ``test`` / ``expect`` instead of the ones from
 * ``@playwright/test`` to opt in.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

export const test = base.extend({
  page: async ({ page }, use) => {
    await page.route(`${API_BASE}/auth/me`, async (route) => {
      // Default: no user signed in, no auth required. Tests that care
      // about a specific user_id or want auth_required=true (e.g.
      // auth.spec.ts) install their own handler later, which wins.
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ user_id: null, auth_required: false }),
      });
    });
    await use(page);
  },
});

// Re-export the underlying type surface so specs that previously
// imported ``Page`` / ``Route`` from ``@playwright/test`` keep working
// after the fixture flip — they only need to swap the import source,
// not the symbol list.
export { expect };
export type { Page, Route };
