import { test, expect } from "./fixtures";

/**
 * Literature page (`/runs/[runId]/literature`) renders two panels:
 * the novelty composite-score card and the retrieval source breakdown.
 *
 * Both API endpoints are mocked with `page.route(...)` so the spec is
 * hermetic — the dashboard's Python backend doesn't have to be running.
 */

const RUN_ID = "test-run-id";

const FIXTURE_NOVELTY = {
  score: 0.74,
  max_similarity: 0.31,
  nearest_source_id: "10.1234/related-work",
  llm_score: 0.7,
  embedding_score: 0.78,
  agreement: true,
};

const FIXTURE_RETRIEVAL = {
  by_adapter: [
    { adapter: "openalex", count: 25, deduped: 5 },
    { adapter: "arxiv", count: 12, deduped: 2 },
    { adapter: "semantic_scholar", count: 9, deduped: 2 },
    { adapter: "crossref", count: 7, deduped: 1 },
    { adapter: "ads", count: 4, deduped: 0 },
    { adapter: "pubmed", count: 3, deduped: 1 },
  ],
  total_unique: 49,
  total_returned: 60,
  queries: ["dark energy equation of state", "Hubble tension"],
  samples: [
    {
      source_id: "10.1234/example-doi",
      title: "Sample paper on cosmology",
      adapter: "openalex",
    },
    {
      source_id: "arxiv:2403.12345",
      title: "Another paper",
      adapter: "arxiv",
    },
  ],
};

async function mockLiteratureApi(page: import("@playwright/test").Page) {
  await page.route(
    `**/api/v1/runs/${RUN_ID}/novelty`,
    async (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(FIXTURE_NOVELTY),
      }),
  );
  await page.route(
    `**/api/v1/runs/${RUN_ID}/retrieval_summary`,
    async (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(FIXTURE_RETRIEVAL),
      }),
  );
}

test.describe("run literature signals", () => {
  test("renders novelty score and source breakdown bars", async ({ page }) => {
    await mockLiteratureApi(page);
    await page.goto(`/runs/literature?runId=${RUN_ID}`);

    // Page header
    await expect(
      page.getByRole("heading", { level: 1, name: "Literature signals" }),
    ).toBeVisible();
    await expect(page.getByText(RUN_ID, { exact: true })).toBeVisible();

    // Novelty card
    const novelty = page.getByTestId("novelty-score-card");
    await expect(novelty).toBeVisible();
    await expect(novelty.getByText("Novelty score")).toBeVisible();

    // 0.74 → "74%" rendered with green tone (high novelty ≥ 0.7)
    const scoreValue = page.getByTestId("novelty-score-value");
    await expect(scoreValue).toHaveText("74%");
    await expect(scoreValue).toHaveCSS(
      "color",
      "rgb(39, 166, 68)", // --color-status-green-spec = #27a644
    );

    // Subline lists the underlying scores + agreement check.
    const subline = page.getByTestId("novelty-score-subline");
    await expect(subline).toContainText("LLM");
    await expect(subline).toContainText("0.70");
    await expect(subline).toContainText("0.78");
    await expect(subline).toContainText("agreement");

    // Nearest prior work resolves to a doi.org URL.
    const nearest = page.getByTestId("novelty-nearest-link");
    await expect(nearest).toHaveAttribute(
      "href",
      "https://doi.org/10.1234/related-work",
    );

    // Source breakdown
    const breakdown = page.getByTestId("source-breakdown");
    await expect(breakdown).toBeVisible();
    await expect(breakdown.getByText("Retrieval sources")).toBeVisible();

    // Six adapter bars rendered.
    const bars = page.getByTestId("source-breakdown-bar");
    await expect(bars).toHaveCount(6);

    // Summary line.
    const summary = page.getByTestId("source-breakdown-summary");
    await expect(summary).toContainText("49");
    await expect(summary).toContainText("60");
    await expect(summary).toContainText("6");
    await expect(summary).toContainText("adapters");

    // Sample-source list.
    const samples = page.getByTestId("source-breakdown-samples");
    await expect(samples).toBeVisible();
    await expect(
      samples.getByRole("link", { name: /10\.1234\/example-doi/ }),
    ).toHaveAttribute("href", "https://doi.org/10.1234/example-doi");
  });

  test("renders amber tone for moderate novelty", async ({ page }) => {
    await page.route(
      `**/api/v1/runs/${RUN_ID}/novelty`,
      async (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            score: 0.5,
            max_similarity: 0.5,
            nearest_source_id: null,
            llm_score: 0.4,
            embedding_score: 0.6,
            agreement: false,
          }),
        }),
    );
    await page.route(
      `**/api/v1/runs/${RUN_ID}/retrieval_summary`,
      async (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            by_adapter: [],
            total_unique: 0,
            total_returned: 0,
            queries: [],
            samples: [],
          }),
        }),
    );

    await page.goto(`/runs/literature?runId=${RUN_ID}`);
    const scoreValue = page.getByTestId("novelty-score-value");
    await expect(scoreValue).toHaveText("50%");
    await expect(scoreValue).toHaveCSS(
      "color",
      "rgb(240, 191, 0)", // --color-status-amber-spec = #f0bf00
    );
    // Empty retrieval state surfaces.
    await expect(page.getByTestId("source-breakdown-empty")).toBeVisible();
  });

  test("renders red tone for low novelty", async ({ page }) => {
    await page.route(
      `**/api/v1/runs/${RUN_ID}/novelty`,
      async (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            score: 0.2,
            max_similarity: 0.9,
            nearest_source_id: "arxiv:2403.99999",
            llm_score: 0.15,
            embedding_score: 0.25,
            agreement: true,
          }),
        }),
    );
    await page.route(
      `**/api/v1/runs/${RUN_ID}/retrieval_summary`,
      async (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(FIXTURE_RETRIEVAL),
        }),
    );

    await page.goto(`/runs/literature?runId=${RUN_ID}`);
    const scoreValue = page.getByTestId("novelty-score-value");
    await expect(scoreValue).toHaveText("20%");
    await expect(scoreValue).toHaveCSS(
      "color",
      "rgb(235, 87, 87)", // --color-status-red-spec = #eb5757
    );
  });

  test("renders empty states when score not computed", async ({ page }) => {
    await page.route(
      `**/api/v1/runs/${RUN_ID}/novelty`,
      async (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            score: null,
            max_similarity: null,
            nearest_source_id: null,
            llm_score: null,
            embedding_score: null,
            agreement: null,
          }),
        }),
    );
    await page.route(
      `**/api/v1/runs/${RUN_ID}/retrieval_summary`,
      async (route) =>
        route.fulfill({
          status: 404,
          body: "",
        }),
    );

    await page.goto(`/runs/literature?runId=${RUN_ID}`);
    await expect(page.getByTestId("novelty-score-empty")).toBeVisible();
    await expect(page.getByText("Novelty score not computed.")).toBeVisible();
    await expect(page.getByTestId("source-breakdown-empty")).toBeVisible();
    await expect(page.getByText("No retrieval has run yet.")).toBeVisible();
  });
});
