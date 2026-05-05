import { test, expect } from "./fixtures";

/**
 * Citation graph viewer: mocks ``GET /runs/:run_id/citation_graph`` with a
 * 3-seed × 5-expansion × 7-edge fixture, then verifies that:
 *
 * - The Graph tab renders all 8 nodes (3 seeds + 5 expanded).
 * - The List tab renders the Seeds and Expanded sections.
 * - The Stats tab shows correct metric values.
 * - Switching between tabs via Radix tab triggers works.
 */
test.describe("run citations viewer", () => {
  const RUN_ID = "run_demo";
  const PAYLOAD = {
    seeds: [
      { id: "S1", title: "Seed alpha", doi: "10.1000/seed1", openalex_id: "S1" },
      { id: "S2", title: "Seed beta",  doi: null,            openalex_id: "S2" },
      { id: "S3", title: "Seed gamma", doi: "10.1000/seed3", openalex_id: "S3" },
    ],
    expanded: [
      { id: "E1", title: "Expansion alpha-1", doi: "10.1000/exp1", openalex_id: "E1" },
      { id: "E2", title: "Expansion alpha-2", doi: null,           openalex_id: "E2" },
      { id: "E3", title: "Expansion beta-1",  doi: "10.1000/exp3", openalex_id: "E3" },
      { id: "E4", title: "Expansion gamma-1", doi: "10.1000/exp4", openalex_id: "E4" },
      { id: "E5", title: "Expansion shared",  doi: null,           openalex_id: "E5" },
    ],
    edges: [
      { from: "S1", to: "E1", kind: "references" },
      { from: "S1", to: "E2", kind: "references" },
      { from: "S1", to: "E5", kind: "references" },
      { from: "S2", to: "E3", kind: "references" },
      { from: "S2", to: "E5", kind: "cited_by" },
      { from: "S3", to: "E4", kind: "references" },
      { from: "S3", to: "E5", kind: "cited_by" },
    ],
    stats: {
      seed_count: 3,
      expanded_count: 5,
      edge_count: 7,
      duplicates_filtered: 2,
    },
  };

  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v1/runs/*/citation_graph", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PAYLOAD),
      });
    });
  });

  test("graph tab renders all 8 nodes", async ({ page }) => {
    await page.goto(`/runs/citations?runId=${RUN_ID}`);

    await expect(page.getByTestId("citation-graph-view")).toBeVisible();
    await expect(page.getByTestId("citation-graph-svg")).toBeVisible();

    // 3 seeds + 5 expanded = 8 SVG node groups.
    const nodes = page.locator(
      '[data-testid="citation-graph-nodes"] > [data-testid^="node-"]',
    );
    await expect(nodes).toHaveCount(8);

    // Verify side classification.
    await expect(
      page.locator('[data-testid="citation-graph-nodes"] [data-side="seed"]'),
    ).toHaveCount(3);
    await expect(
      page.locator('[data-testid="citation-graph-nodes"] [data-side="expanded"]'),
    ).toHaveCount(5);

    // 7 edges drawn.
    await expect(
      page.locator('[data-testid="citation-graph-edges"] path'),
    ).toHaveCount(7);
  });

  test("list tab shows Seeds and Expanded sections", async ({ page }) => {
    await page.goto(`/runs/citations?runId=${RUN_ID}`);

    await page.getByTestId("citation-tab-list").click();
    await expect(page.getByTestId("citation-tab-list")).toHaveAttribute(
      "data-state",
      "active",
    );

    await expect(page.getByTestId("citation-list")).toBeVisible();
    await expect(page.getByTestId("citation-list-seeds")).toBeVisible();
    await expect(page.getByTestId("citation-list-expanded")).toBeVisible();

    // 3 seed rows + 5 expanded rows = 8 citation rows total.
    await expect(page.locator('[data-testid^="citation-row-"]')).toHaveCount(8);

    // DOI link points at the canonical doi.org resolver.
    const firstDoiLink = page.getByTestId("doi-link-S1");
    await expect(firstDoiLink).toHaveAttribute(
      "href",
      "https://doi.org/10.1000/seed1",
    );
    await expect(firstDoiLink).toHaveAttribute("target", "_blank");
  });

  test("stats tab shows correct metric values", async ({ page }) => {
    await page.goto(`/runs/citations?runId=${RUN_ID}`);

    await page.getByTestId("citation-tab-stats").click();
    await expect(page.getByTestId("citation-stats")).toBeVisible();

    await expect(page.getByTestId("stat-seed-count")).toContainText("3");
    await expect(page.getByTestId("stat-expanded-count")).toContainText("5");
    await expect(page.getByTestId("stat-edge-count")).toContainText("7");
    await expect(page.getByTestId("stat-duplicates-filtered")).toContainText("2");

    await expect(page.getByTestId("top-cited-section")).toBeVisible();
  });

  test("tabs switch via radix triggers", async ({ page }) => {
    await page.goto(`/runs/citations?runId=${RUN_ID}`);

    // Default tab is "graph".
    await expect(page.getByTestId("citation-tab-graph")).toHaveAttribute(
      "data-state",
      "active",
    );

    // List → active.
    await page.getByTestId("citation-tab-list").click();
    await expect(page.getByTestId("citation-tab-list")).toHaveAttribute(
      "data-state",
      "active",
    );
    await expect(page.getByTestId("citation-list")).toBeVisible();

    // Stats → active.
    await page.getByTestId("citation-tab-stats").click();
    await expect(page.getByTestId("citation-tab-stats")).toHaveAttribute(
      "data-state",
      "active",
    );
    await expect(page.getByTestId("citation-stats")).toBeVisible();

    // Back to graph.
    await page.getByTestId("citation-tab-graph").click();
    await expect(page.getByTestId("citation-tab-graph")).toHaveAttribute(
      "data-state",
      "active",
    );
    await expect(page.getByTestId("citation-graph-svg")).toBeVisible();
  });
});
