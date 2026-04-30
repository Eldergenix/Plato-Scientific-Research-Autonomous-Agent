import { test, expect, type Page } from "@playwright/test";

/**
 * Stream 8 (F8) — autonomous research loop UI.
 *
 * Backend is mocked at the network layer so these tests run with no
 * dashboard backend. We mock GET /loop, POST /loop/start, GET /loop/{id}/status,
 * GET /loop/{id}/tsv, and POST /loop/{id}/stop.
 */

const RUNNING_LOOP = {
  loop_id: "abc123def456",
  status: "running",
  iterations: 7,
  kept: 4,
  discarded: 3,
  best_composite: 0.4523,
  started_at: "2026-04-29T10:00:00+00:00",
  tsv_path: "/tmp/plato-fake/runs.tsv",
  error: null,
};

const NEW_LOOP = {
  loop_id: "newloopid000",
  status: "running",
  iterations: 0,
  kept: 0,
  discarded: 0,
  best_composite: 0.0,
  started_at: "2026-04-29T11:00:00+00:00",
  tsv_path: "/tmp/plato-new/runs.tsv",
  error: null,
};

const TSV_ROWS = [
  {
    iter: 1,
    timestamp: "2026-04-29T10:00:30+00:00",
    composite: 0.2,
    status: "keep",
    description: "baseline",
  },
  {
    iter: 2,
    timestamp: "2026-04-29T10:01:00+00:00",
    composite: 0.4523,
    status: "keep",
    description: "composite improved",
  },
  {
    iter: 3,
    timestamp: "2026-04-29T10:01:30+00:00",
    composite: 0.3,
    status: "discard",
    description: "composite worse",
  },
];

const API_BASE = "http://127.0.0.1:7878/api/v1";

async function mockLoopApi(page: Page) {
  // Capabilities + projects must answer something so the dashboard shell loads
  // without spamming the console.
  await page.route(`${API_BASE}/capabilities`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        is_demo: false,
        allowed_stages: ["data", "idea", "method", "literature"],
        max_concurrent_runs: 2,
        notes: [],
      }),
    }),
  );
  await page.route(`${API_BASE}/projects`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );

  await page.route(`${API_BASE}/loop`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([RUNNING_LOOP]),
    }),
  );

  await page.route(`${API_BASE}/loop/start`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(NEW_LOOP),
    }),
  );

  await page.route(`${API_BASE}/loop/${RUNNING_LOOP.loop_id}/status`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(RUNNING_LOOP),
    }),
  );
  await page.route(`${API_BASE}/loop/${RUNNING_LOOP.loop_id}/tsv`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rows: TSV_ROWS }),
    }),
  );

  await page.route(`${API_BASE}/loop/${NEW_LOOP.loop_id}/status`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(NEW_LOOP),
    }),
  );
  await page.route(`${API_BASE}/loop/${NEW_LOOP.loop_id}/tsv`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rows: [] }),
    }),
  );
}

test.describe("loop UI", () => {
  test("/loop lists active loops and opens the start dialog", async ({ page }) => {
    await mockLoopApi(page);
    await page.goto("/loop");

    await expect(
      page.getByRole("heading", { level: 1, name: /Autonomous loops/i }),
    ).toBeVisible();

    // The mocked running loop renders a row with its loop_id and status.
    const row = page.locator('[data-testid="loop-row"]').first();
    await expect(row).toBeVisible();
    await expect(row).toContainText(RUNNING_LOOP.loop_id);
    await expect(row).toContainText("running");

    // Click "Start autonomous loop" → dialog opens with form fields.
    await page.getByTestId("loop-start-button").click();
    await expect(page.getByTestId("loop-start-dialog")).toBeVisible();
    await expect(page.getByTestId("loop-form-project-dir")).toBeVisible();
  });

  test("submitting the form posts /loop/start and redirects to detail page", async ({
    page,
  }) => {
    await mockLoopApi(page);

    let capturedBody: Record<string, unknown> | null = null;
    await page.unroute(`${API_BASE}/loop/start`);
    await page.route(`${API_BASE}/loop/start`, async (route) => {
      try {
        capturedBody = JSON.parse(route.request().postData() ?? "{}");
      } catch {
        capturedBody = null;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(NEW_LOOP),
      });
    });

    await page.goto("/loop");
    await page.getByTestId("loop-start-button").click();
    await expect(page.getByTestId("loop-start-dialog")).toBeVisible();
    await page.getByTestId("loop-form-project-dir").fill("/tmp/plato-new");
    await page.getByTestId("loop-form-max-iters").fill("3");

    // Wait for the start request before asserting URL change so we ride
    // out any compile-on-demand latency for the /loop/[loopId] route.
    const startReq = page.waitForRequest(
      (req) =>
        req.url().endsWith("/api/v1/loop/start") && req.method() === "POST",
    );
    await page.getByTestId("loop-form-submit").click();
    await startReq;

    await expect(page).toHaveURL(new RegExp(`/loop/${NEW_LOOP.loop_id}$`), {
      timeout: 15_000,
    });
    await expect(page.getByTestId("loop-detail-id")).toContainText(
      NEW_LOOP.loop_id,
    );

    const body = capturedBody as Record<string, unknown> | null;
    expect(body).not.toBeNull();
    expect(body?.project_dir).toBe("/tmp/plato-new");
    expect(body?.max_iters).toBe(3);
  });

  test("detail page shows status pill, counters, and history rows", async ({
    page,
  }) => {
    await mockLoopApi(page);
    await page.goto(`/loop/${RUNNING_LOOP.loop_id}`);

    await expect(page.getByTestId("loop-status-pill")).toHaveText("running");
    await expect(page.getByTestId("loop-iterations")).toHaveText(
      String(RUNNING_LOOP.iterations),
    );
    await expect(page.getByTestId("loop-kept")).toHaveText(
      String(RUNNING_LOOP.kept),
    );
    await expect(page.getByTestId("loop-discarded")).toHaveText(
      String(RUNNING_LOOP.discarded),
    );

    const rows = page.getByTestId("loop-history-rows").getByRole("row");
    await expect(rows).toHaveCount(TSV_ROWS.length);
  });

  test("Stop button confirms then flips status to stopped", async ({ page }) => {
    await mockLoopApi(page);

    let stopped = false;
    await page.route(
      `${API_BASE}/loop/${RUNNING_LOOP.loop_id}/stop`,
      (route) => {
        stopped = true;
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ...RUNNING_LOOP, status: "stopped" }),
        });
      },
    );

    await page.goto(`/loop/${RUNNING_LOOP.loop_id}`);
    await expect(page.getByTestId("loop-status-pill")).toHaveText("running");

    await page.getByTestId("loop-stop-button").click();
    // Confirm dialog from <ConfirmDialog>; click "Stop loop".
    await page.getByRole("button", { name: /^Stop loop$/ }).click();

    await expect(page.getByTestId("loop-status-pill")).toHaveText("stopped");
    expect(stopped).toBe(true);
  });
});
