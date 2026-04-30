import { test, expect } from "@playwright/test";

/**
 * Run detail page (`/runs/[runId]`) renders three panels:
 * manifest, validation report, and the claims × sources evidence matrix.
 *
 * The browser fetches `/api/v1/runs/.../{manifest,evidence_matrix,validation_report}`
 * — we intercept those calls with `page.route(...)` so the spec is hermetic
 * and doesn't need the backend running.
 */

const RUN_ID = "test-run-id";

const FIXTURE_MANIFEST = {
  run_id: RUN_ID,
  workflow: "get_paper",
  started_at: "2026-04-29T10:00:00Z",
  ended_at: "2026-04-29T10:05:00Z",
  status: "success",
  domain: "astro",
  git_sha: "abcdef1234567890",
  project_sha: "1111222233334444",
  models: { idea_maker: "gemini-2.0-flash", reviewer: "claude-haiku-4-5" },
  prompt_hashes: {},
  seeds: {},
  source_ids: ["10.1234/example-doi", "arxiv:2403.12345"],
  cost_usd: 0.0421,
  tokens_in: 12500,
  tokens_out: 4200,
  error: null,
};

const FIXTURE_EVIDENCE = {
  claims: [
    {
      id: "claim-1",
      text: "Dark energy density is constant across cosmic time.",
      source_id: "src-1",
    },
    {
      id: "claim-2",
      text: "The Hubble tension persists in late-universe measurements.",
      source_id: "src-2",
    },
  ],
  evidence_links: [
    {
      claim_id: "claim-1",
      source_id: "src-1",
      support: "supports",
      strength: "strong",
    },
    {
      claim_id: "claim-2",
      source_id: "src-2",
      support: "neutral",
      strength: "moderate",
    },
  ],
  sources: [
    { id: "src-1", title: "Planck 2018 results", url: "https://example.com/planck" },
    { id: "src-2", title: "SH0ES collaboration H0 measurement", url: null },
  ],
};

const FIXTURE_VALIDATION = {
  validation_rate: 0.85,
  total_references: 20,
  verified_references: 17,
  failures: [
    { source_id: "ref-5", reason: "doi_unresolvable", detail: "DOI returned 404" },
    { source_id: "ref-12", reason: "url_dead", detail: null },
  ],
};

async function mockManifestApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/runs/test-run-id/manifest", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_MANIFEST),
    });
  });
  await page.route("**/api/v1/runs/test-run-id/evidence_matrix", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_EVIDENCE),
    });
  });
  await page.route("**/api/v1/runs/test-run-id/validation_report", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_VALIDATION),
    });
  });
}

test.describe("run detail", () => {
  test("renders manifest, validation report, and evidence matrix", async ({ page }) => {
    await mockManifestApi(page);
    await page.goto(`/runs/${RUN_ID}`);

    // Page header echoes the run id.
    await expect(page.getByRole("heading", { level: 1, name: "Run detail" })).toBeVisible();
    await expect(page.getByText(RUN_ID, { exact: true })).toBeVisible();

    // Manifest panel
    const manifest = page.getByTestId("manifest-panel");
    await expect(manifest).toBeVisible();
    await expect(manifest.getByText("Run manifest")).toBeVisible();
    await expect(manifest.getByText("get_paper")).toBeVisible();
    await expect(manifest.getByText("astro")).toBeVisible();
    await expect(manifest.getByText("success")).toBeVisible();
    await expect(manifest.getByText(/Tokens in/i)).toBeVisible();
    await expect(manifest.getByText(/Tokens out/i)).toBeVisible();
    await expect(manifest.getByText("$0.0421")).toBeVisible();
    // The model role + value renders from the table
    await expect(manifest.getByText("idea_maker")).toBeVisible();
    await expect(manifest.getByText("gemini-2.0-flash")).toBeVisible();
    // Source links: DOI should resolve to doi.org href
    const doiLink = manifest.getByRole("link", { name: /10\.1234\/example-doi/ });
    await expect(doiLink).toBeVisible();
    await expect(doiLink).toHaveAttribute("href", "https://doi.org/10.1234/example-doi");
    const arxivLink = manifest.getByRole("link", { name: /arxiv:2403\.12345/ });
    await expect(arxivLink).toHaveAttribute("href", "https://arxiv.org/abs/2403.12345");

    // Validation report
    const validation = page.getByTestId("validation-report-card");
    await expect(validation).toBeVisible();
    await expect(validation.getByText("Validation report")).toBeVisible();
    await expect(page.getByTestId("validation-rate")).toHaveText("85.0%");
    await expect(validation.getByText(/17 \/ 20 references verified/)).toBeVisible();
    await expect(validation.getByText("Failures")).toBeVisible();

    // Evidence matrix
    const matrix = page.getByTestId("evidence-matrix-table");
    await expect(matrix).toBeVisible();
    await expect(matrix.getByText("Claims × sources")).toBeVisible();
    const rows = matrix.getByTestId("evidence-matrix-row");
    await expect(rows).toHaveCount(2);
    await expect(matrix.getByText(/Dark energy density is constant/)).toBeVisible();
    await expect(matrix.getByText(/Hubble tension/)).toBeVisible();
    await expect(matrix.getByText("supports")).toBeVisible();
    await expect(matrix.getByText("neutral")).toBeVisible();
    // Source with URL renders as a link.
    await expect(matrix.getByRole("link", { name: /Planck 2018 results/ })).toBeVisible();
  });

  test("evidence matrix renders empty state when API returns empty arrays", async ({ page }) => {
    await page.route("**/api/v1/runs/test-run-id/manifest", async (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(FIXTURE_MANIFEST),
      }),
    );
    await page.route("**/api/v1/runs/test-run-id/evidence_matrix", async (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ claims: [], evidence_links: [] }),
      }),
    );
    await page.route("**/api/v1/runs/test-run-id/validation_report", async (route) =>
      route.fulfill({ status: 404, body: "" }),
    );

    await page.goto(`/runs/${RUN_ID}`);
    await expect(page.getByTestId("evidence-matrix-empty")).toBeVisible();
    await expect(
      page.getByText("No evidence links yet — claim extraction not run."),
    ).toBeVisible();
  });
});
