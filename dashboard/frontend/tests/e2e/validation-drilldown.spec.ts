import { test, expect } from "@playwright/test";

/**
 * F13 — validation failures drilldown.
 *
 * The integration commit will surface the ValidationReportCard on
 * /runs/[runId]. Until that lands, we drive the card via a stable test
 * fixture page (/login/validation-demo) that this stream owns. The
 * fixture mounts the same component with five mock failures spanning
 * three reasons and three source types — enough to exercise grouping,
 * search, and CSV export.
 */

test.describe("validation drilldown", () => {
  test("search filters by reason substring", async ({ page }) => {
    await page.goto("/login/validation-demo");
    await expect(page.getByTestId("validation-report-card")).toBeVisible();
    await expect(page.getByTestId("validation-failures-panel")).toBeVisible();

    // All five failures rendered up front.
    await expect(page.getByTestId("validation-failure-row")).toHaveCount(5);

    // Type a reason substring; only matching rows remain.
    await page.getByTestId("validation-search").fill("timeout");
    await expect(page.getByTestId("validation-failure-row")).toHaveCount(1);

    // Search by source_id substring.
    await page.getByTestId("validation-search").fill("ss:abc");
    await expect(page.getByTestId("validation-failure-row")).toHaveCount(2);

    // No-match path renders an inline message instead of a list.
    await page.getByTestId("validation-search").fill("zzzzzz-nope");
    await expect(page.getByTestId("validation-no-matches")).toBeVisible();
    await expect(page.getByTestId("validation-failure-row")).toHaveCount(0);

    // Clearing brings everything back.
    await page.getByTestId("validation-search").fill("");
    await expect(page.getByTestId("validation-failure-row")).toHaveCount(5);
  });

  test("group-by-reason creates sub-headers and partitions failures", async ({
    page,
  }) => {
    await page.goto("/login/validation-demo");

    await page
      .getByTestId("validation-group-by")
      .selectOption("reason");

    // Three distinct reasons → three groups.
    const groups = page.getByTestId("validation-group");
    await expect(groups).toHaveCount(3);

    // Each group's count chip should sum to 5.
    const titles = await page
      .getByTestId("validation-group-toggle")
      .allTextContents();
    expect(titles.join(" ")).toContain("missing_abstract");
    expect(titles.join(" ")).toContain("fetch_timeout");
    expect(titles.join(" ")).toContain("schema_mismatch");

    // Switch to source_type — three source types → three groups.
    await page.getByTestId("validation-group-by").selectOption("source_type");
    await expect(groups).toHaveCount(3);
    const sourceTitles = await page
      .getByTestId("validation-group-toggle")
      .allTextContents();
    expect(sourceTitles.join(" ")).toContain("arxiv");
    expect(sourceTitles.join(" ")).toContain("crossref");
    expect(sourceTitles.join(" ")).toContain("semantic_scholar");
  });

  test("copy-csv writes a CSV body to the clipboard", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);

    // Stub navigator.clipboard.writeText so the test passes regardless
    // of headless-clipboard quirks; it also lets us read what was
    // written without round-tripping through the OS clipboard.
    await page.addInitScript(() => {
      const captured: string[] = [];
      // @ts-expect-error — intentional global for the test.
      window.__clipboardCaptured = captured;
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: async (text: string) => {
            captured.push(text);
          },
        },
      });
    });

    await page.goto("/login/validation-demo");
    await page.getByTestId("validation-copy-csv").click();

    const captured = await page.evaluate(
      // @ts-expect-error — populated by addInitScript above.
      () => (window.__clipboardCaptured as string[]) ?? [],
    );
    expect(captured.length).toBe(1);
    const csv = captured[0];
    // Header row + 5 data rows.
    const lines = csv.split("\n");
    expect(lines[0]).toBe("source_id,reason,detail");
    expect(lines.length).toBe(6);
    expect(csv).toContain("missing_abstract");
    expect(csv).toContain("arxiv:2403.00001");
  });
});
