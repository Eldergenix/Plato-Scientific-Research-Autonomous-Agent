import { test, expect } from "./fixtures";

/**
 * Run reviews page (`/runs/[runId]/reviews`) renders:
 *   - revision counter ("Revision N of M" + progress dots)
 *   - reviewer panel with 4 axis cards (methodology / statistics / novelty / writing)
 *
 * The page fetches `/api/v1/runs/<id>/critiques`. We intercept it with
 * `page.route(...)` so the spec is hermetic.
 */

const RUN_ID = "test-run";

const LONG_RATIONALE =
  "Effect size estimation relies on a simple two-sample t-test, but the underlying distribution is heavy-tailed and the reported p-value should be re-derived against a non-parametric baseline (Mann-Whitney U or a permutation test). The reviewer flags this as a recurring weakness across the methods section: the assumption of normality is repeated in §3.2 and §3.4 without diagnostic plots, and Bonferroni correction is applied unevenly.";

const FIXTURE_PAYLOAD = {
  critiques: {
    methodology: {
      severity: 4,
      rationale: LONG_RATIONALE,
      issues: [
        {
          section: "methods",
          issue: "n=12 is underpowered",
          fix: "Run a power analysis or expand the cohort.",
        },
      ],
    },
    statistics: {
      severity: 3,
      rationale: "Multiple-comparisons correction unclear in §3.2.",
      issues: [],
    },
    novelty: {
      severity: 1,
      rationale: "Modest delta over Smith 2024.",
      issues: [],
    },
    writing: {
      severity: 0,
      rationale: "Clear prose throughout.",
      issues: [],
    },
  },
  digest: {
    max_severity: 4,
    iteration: 1,
    issues: [
      {
        reviewer: "methodology",
        section: "methods",
        issue: "n=12 is underpowered",
      },
    ],
  },
  revision_state: { iteration: 1, max_iterations: 3 },
};

async function mockCritiquesApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/runs/test-run/critiques", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_PAYLOAD),
    });
  });
}

test.describe("run reviews", () => {
  test("renders iteration badge, four axis cards, and expands a long rationale", async ({
    page,
  }) => {
    await mockCritiquesApi(page);
    await page.goto(`/runs/reviews?runId=${RUN_ID}`);

    // Page header echoes the run id.
    await expect(
      page.getByRole("heading", { level: 1, name: "Run reviews" }),
    ).toBeVisible();
    await expect(page.getByText(RUN_ID, { exact: true })).toBeVisible();

    // Revision counter
    const counter = page.getByTestId("revision-counter");
    await expect(counter).toBeVisible();
    await expect(page.getByTestId("revision-counter-label")).toHaveText(
      "Revision 1 of 3",
    );
    await expect(page.getByTestId("revision-counter-dots")).toBeVisible();

    // Reviewer panel + iteration badge
    const panel = page.getByTestId("critique-panel");
    await expect(panel).toBeVisible();
    await expect(panel.getByText("Reviewer panel")).toBeVisible();
    await expect(page.getByTestId("critique-iteration-badge")).toHaveText(
      "Iteration 1 / 3",
    );

    // Four axis cards present
    await expect(page.getByTestId("critique-axis-methodology")).toBeVisible();
    await expect(page.getByTestId("critique-axis-statistics")).toBeVisible();
    await expect(page.getByTestId("critique-axis-novelty")).toBeVisible();
    await expect(page.getByTestId("critique-axis-writing")).toBeVisible();

    // Methodology issue list renders the fix line
    const methodology = page.getByTestId("critique-axis-methodology");
    await expect(methodology.getByText("n=12 is underpowered")).toBeVisible();
    await expect(methodology.getByText(/Run a power analysis/)).toBeVisible();

    // Long rationale is truncated at first; "Show more" reveals the rest.
    const rationale = methodology.getByTestId("critique-rationale");
    await expect(rationale).not.toContainText("Bonferroni correction");
    const toggle = methodology.getByTestId("critique-rationale-toggle");
    await expect(toggle).toHaveText(/Show more/);
    await toggle.click();
    await expect(rationale).toContainText("Bonferroni correction");
    await expect(toggle).toHaveText(/Show less/);
  });

  test("renders empty state when reviewers haven't run yet", async ({ page }) => {
    await page.route("**/api/v1/runs/test-run/critiques", async (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          critiques: {},
          digest: null,
          revision_state: null,
        }),
      }),
    );

    await page.goto(`/runs/reviews?runId=${RUN_ID}`);

    // Counter falls back to its idle copy.
    await expect(
      page.getByText("No revision in progress."),
    ).toBeVisible();

    // Panel renders the "haven't run yet" message and no axis cards.
    await expect(
      page.getByText(/Reviewers haven.?t run yet/),
    ).toBeVisible();
    await expect(page.getByTestId("critique-axis-methodology")).toHaveCount(0);
  });
});
