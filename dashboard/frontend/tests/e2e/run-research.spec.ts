import { test, expect } from "./fixtures";

/**
 * /runs/[runId]/research surfaces counter-evidence + gap-detector signals.
 *
 * Both API endpoints are mocked so the test is hermetic — it exercises
 * the rendering layer only. The dev-server proxy points the page at
 * 127.0.0.1:7878 by default; we intercept that origin instead of the
 * frontend's baseURL so route matching works regardless of how
 * NEXT_PUBLIC_API_BASE was configured at build time.
 */
test.describe("run research signals", () => {
  test("counter-evidence + gaps render with grouped sections", async ({ page }) => {
    const counterEvidence = {
      sources: [
        {
          id: "src_a",
          title: "Failed replication of an earlier transformer scaling claim",
          venue: "NeurIPS",
          year: 2024,
          doi: "10.1234/abc",
          arxiv_id: null,
          url: null,
        },
        {
          id: "src_b",
          title: "Null result for proposed alpha-correction in Bayesian fits",
          venue: "MNRAS",
          year: 2023,
          doi: null,
          arxiv_id: "2403.12345",
          url: null,
        },
      ],
      queries_used: [
        "transformer scaling fail to replicate",
        "transformer scaling null result",
        "transformer scaling limitations",
      ],
    };

    const gaps = {
      gaps: [
        {
          kind: "contradiction",
          description:
            "Claim 'c1' has both supporting and refuting evidence across 3 sources",
          severity: 4,
          evidence: ["10.1000/foo", "10.1000/bar", "10.1000/baz"],
        },
        {
          kind: "coverage",
          description: "Idea keyword 'graph' appears in 0 of 5 retrieved sources.",
          severity: 4,
          evidence: ["graph"],
        },
        {
          kind: "homogeneity",
          description:
            "All 5 retrieved sources mention method keyword 'transformer'.",
          severity: 3,
          evidence: ["transformer"],
        },
      ],
    };

    await page.route("**/api/v1/runs/run_test/counter_evidence", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(counterEvidence),
      }),
    );
    await page.route("**/api/v1/runs/run_test/gaps", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(gaps),
      }),
    );

    await page.goto("/runs/run_test/research");

    // Header carries the run id so the user can confirm context.
    await expect(page.getByTestId("research-header")).toContainText("run_test");

    // Counter-evidence list: both sources rendered, each with a trigger badge.
    const counterList = page.getByTestId("counter-evidence-list");
    await expect(counterList).toBeVisible();
    const rows = counterList.getByTestId("counter-evidence-row");
    await expect(rows).toHaveCount(2);
    const triggerBadges = counterList.getByTestId("counter-evidence-trigger");
    await expect(triggerBadges).toHaveCount(2);
    // First source title contains "fail to replicate" so the badge picks it up.
    await expect(triggerBadges.first()).toHaveText(/fail to replicate/i);

    // Gaps panel: three groups, one per kind, with a total-severity pill.
    const gapsPanel = page.getByTestId("gaps-panel");
    await expect(gapsPanel).toBeVisible();
    await expect(gapsPanel.getByTestId("gaps-total-severity")).toContainText(
      /severity\s+11/i,
    );
    const groups = gapsPanel.getByTestId("gap-group");
    await expect(groups).toHaveCount(3);
    await expect(
      gapsPanel.locator("[data-testid='gap-group'][data-kind='contradiction']"),
    ).toBeVisible();
    await expect(
      gapsPanel.locator("[data-testid='gap-group'][data-kind='coverage']"),
    ).toBeVisible();
    await expect(
      gapsPanel.locator("[data-testid='gap-group'][data-kind='homogeneity']"),
    ).toBeVisible();
  });

  test("empty payloads render the empty-state copy", async ({ page }) => {
    await page.route("**/api/v1/runs/run_empty/counter_evidence", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ sources: [], queries_used: [] }),
      }),
    );
    await page.route("**/api/v1/runs/run_empty/gaps", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ gaps: [] }),
      }),
    );

    await page.goto("/runs/run_empty/research");

    await expect(page.getByTestId("counter-evidence-empty")).toContainText(
      /no counter-evidence search has run yet/i,
    );
    await expect(page.getByTestId("gaps-empty")).toContainText(
      /gap analysis hasn't run yet/i,
    );
  });
});
