import { test, expect, type Route } from "./fixtures";

/**
 * /settings/licenses: license audit + SBOM viewer.
 *
 * Mocks both backend endpoints so the test stays deterministic and
 * doesn't depend on the (slow, environment-specific) license walk. The
 * fixture has 4 distributions, including one Proprietary entry that the
 * stats panel must surface as incompatible.
 */

const AUDIT_FIXTURE = {
  summary: { total: 4, compatible: 2, incompatible: 1, unknown: 1 },
  by_license: [
    { license: "MIT", count: 1, gpl3_compatible: true },
    { license: "Apache-2.0", count: 1, gpl3_compatible: true },
    { license: "Proprietary", count: 1, gpl3_compatible: false },
    { license: "UNKNOWN", count: 1, gpl3_compatible: false },
  ],
  distributions: [
    {
      name: "alpha-pkg",
      version: "1.2.3",
      license: "MIT",
      gpl3_compatible: true,
      source_url: "https://example.com/alpha",
    },
    {
      name: "beta-pkg",
      version: "0.9.0",
      license: "Apache-2.0",
      gpl3_compatible: true,
      source_url: null,
    },
    {
      name: "gamma-corp",
      version: "2.0.0",
      license: "Proprietary",
      gpl3_compatible: false,
      source_url: null,
    },
    {
      name: "mystery-lib",
      version: "0.0.1",
      license: null,
      gpl3_compatible: false,
      source_url: null,
    },
  ],
};

const SBOM_FIXTURE = {
  bomFormat: "CycloneDX",
  specVersion: "1.5",
  serialNumber: "urn:uuid:test-fixture",
  components: [
    { type: "library", name: "alpha-pkg", version: "1.2.3" },
    { type: "library", name: "beta-pkg", version: "0.9.0" },
    { type: "library", name: "gamma-corp", version: "2.0.0" },
  ],
};

async function mockBackend(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/license_audit", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(AUDIT_FIXTURE),
    });
  });
  await page.route("**/api/v1/sbom", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SBOM_FIXTURE),
    });
  });
}

test.describe("settings/licenses page", () => {
  test("renders stats, table, and SBOM summary from mocked endpoints", async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto("/settings/licenses");

    // Page header.
    await expect(
      page.getByRole("heading", { level: 1, name: "Licenses & SBOM" }),
    ).toBeVisible();

    // Stats: total / compatible / incompatible counts from the fixture.
    const stats = page.getByTestId("license-stats");
    await expect(stats).toBeVisible();
    await expect(page.getByTestId("license-stats-total")).toContainText("4");
    await expect(page.getByTestId("license-stats-compatible")).toContainText("2");
    await expect(page.getByTestId("license-stats-incompatible")).toContainText("1");
    await expect(page.getByTestId("license-stats-unknown")).toContainText("1");

    // Table renders one row per distribution.
    const rows = page.getByTestId("license-table-row");
    await expect(rows).toHaveCount(4);

    // SBOM panel surfaces spec version + component count.
    const sbom = page.getByTestId("sbom-summary");
    await expect(sbom).toBeVisible();
    await expect(sbom).toContainText("1.5");
    await expect(sbom).toContainText("3");
  });

  test("filtering by name narrows the table", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/settings/licenses");

    await expect(page.getByTestId("license-table-row")).toHaveCount(4);

    await page.getByTestId("license-table-search").fill("gamma");
    await expect(page.getByTestId("license-table-row")).toHaveCount(1);
    await expect(page.getByTestId("license-table-row")).toContainText("gamma-corp");

    // Header counter reflects the filter.
    await expect(page.getByTestId("license-table")).toContainText("1 of 4");

    // No-match path.
    await page.getByTestId("license-table-search").fill("zzzz-no-such-pkg");
    await expect(page.getByTestId("license-table-no-matches")).toBeVisible();
  });

  test("clicking the License header toggles sort direction", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/settings/licenses");

    const licenseSort = page.getByTestId("license-table-sort-license");

    // Default sort is by name ascending; License header has aria-sort="none".
    await expect(licenseSort).toHaveAttribute("aria-sort", "none");

    // First click → ascending license sort.
    await licenseSort.click();
    await expect(licenseSort).toHaveAttribute("aria-sort", "ascending");

    // Second click → descending.
    await licenseSort.click();
    await expect(licenseSort).toHaveAttribute("aria-sort", "descending");
  });

  test("Download SBOM button fires a fetch to /api/v1/sbom", async ({ page }) => {
    await mockBackend(page);

    let sbomFetchCount = 0;
    await page.route("**/api/v1/sbom", async (route: Route) => {
      sbomFetchCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(SBOM_FIXTURE),
      });
    });

    await page.goto("/settings/licenses");

    // The mount-time fetch lands first; reset the counter so we measure
    // only the click-driven request.
    await expect(page.getByTestId("sbom-summary")).toBeVisible();
    await expect.poll(() => sbomFetchCount).toBeGreaterThanOrEqual(1);
    const baseline = sbomFetchCount;

    // Stub URL.createObjectURL so the test environment doesn't need a
    // real Blob URL implementation. Capturing into window for later
    // assertion.
    await page.evaluate(() => {
      const w = window as unknown as { __sbomBlobs: Blob[] };
      w.__sbomBlobs = [];
      const origCreate = URL.createObjectURL.bind(URL);
      URL.createObjectURL = (b: Blob | MediaSource) => {
        if (b instanceof Blob) w.__sbomBlobs.push(b);
        return origCreate(b);
      };
    });

    const downloadPromise = page.waitForEvent("download").catch(() => null);
    await page.getByTestId("sbom-download-button").click();
    await downloadPromise;

    await expect.poll(() => sbomFetchCount).toBeGreaterThan(baseline);

    const blobCount = await page.evaluate(
      () => (window as unknown as { __sbomBlobs: Blob[] }).__sbomBlobs.length,
    );
    expect(blobCount).toBeGreaterThanOrEqual(1);
  });
});
