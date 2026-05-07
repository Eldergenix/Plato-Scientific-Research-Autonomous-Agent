import { test as base, expect, type Page, type Route } from "@playwright/test";

/**
 * Plato e2e fixture: ships safe default auth + workspace mocks so
 * app-shell tests don't depend on whatever backend happens to be warm.
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "**/api/v1";
const DEFAULT_PROJECT_ID = "e2e-workspace-project";

const DEFAULT_PROJECT = {
  id: DEFAULT_PROJECT_ID,
  name: "E2E workspace project",
  journal: "NONE",
  created_at: "2026-04-29T10:00:00Z",
  updated_at: "2026-04-29T10:00:00Z",
  total_tokens: 0,
  total_cost_cents: 0,
  user_id: null,
  cost_caps: null,
  approvals: null,
  stages: {
    data: { id: "data", label: "Data", status: "done" },
    idea: { id: "idea", label: "Idea", status: "done" },
    literature: { id: "literature", label: "Lit", status: "empty" },
    method: { id: "method", label: "Method", status: "empty" },
    results: { id: "results", label: "Results", status: "empty" },
    paper: { id: "paper", label: "Paper", status: "empty" },
    referee: { id: "referee", label: "Referee", status: "empty" },
  },
  active_run: null,
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

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
    await page.route(`${API_BASE}/health`, (route) =>
      json(route, { ok: true, demo_mode: false }),
    );
    await page.route(`${API_BASE}/capabilities`, (route) =>
      json(route, {
        is_demo: false,
        allowed_stages: [
          "data",
          "idea",
          "literature",
          "method",
          "results",
          "paper",
          "referee",
        ],
        max_concurrent_runs: 2,
        notes: [],
      }),
    );
    await page.route(`${API_BASE}/projects`, async (route) => {
      if (route.request().method() === "GET") {
        await json(route, [DEFAULT_PROJECT]);
        return;
      }
      await json(route, DEFAULT_PROJECT);
    });
    await page.route(`${API_BASE}/projects/${DEFAULT_PROJECT_ID}`, (route) =>
      json(route, DEFAULT_PROJECT),
    );
    await page.route(`${API_BASE}/projects/${DEFAULT_PROJECT_ID}/plots`, (route) =>
      json(route, []),
    );
    await page.route(
      `${API_BASE}/projects/${DEFAULT_PROJECT_ID}/idea_history`,
      (route) => json(route, { entries: [] }),
    );
    await page.route(`${API_BASE}/projects/${DEFAULT_PROJECT_ID}/cost_caps`, (route) =>
      json(route, { budget_cents: null, stop_on_exceed: false }),
    );
    await page.route(`${API_BASE}/projects/${DEFAULT_PROJECT_ID}/approvals`, (route) =>
      json(route, { per_stage: {}, auto_skip: false }),
    );
    await page.route(`${API_BASE}/keys/status`, (route) =>
      json(route, {
        openai: "in_app",
        anthropic: "unset",
        gemini: "unset",
        perplexity: "unset",
        semantic_scholar: "unset",
      }),
    );
    await page.route(`${API_BASE}/projects/*/runs/*/events`, (route) =>
      route.fulfill({
        status: 204,
        contentType: "text/event-stream",
        body: "",
      }),
    );
    await use(page);
  },
});

// Re-export the underlying type surface so specs that previously
// imported ``Page`` / ``Route`` from ``@playwright/test`` keep working
// after the fixture flip — they only need to swap the import source,
// not the symbol list.
export { expect };
export type { Page, Route };
