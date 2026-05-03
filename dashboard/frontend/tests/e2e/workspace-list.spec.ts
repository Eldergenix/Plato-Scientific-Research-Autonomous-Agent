import { test, expect } from "./fixtures";

/**
 * Workspace list: clicking the "All" tab reveals grouped issues, and
 * clicking a row drills into a stage detail. The "Back to all stages"
 * link returns to the list view.
 */
test.describe("workspace list", () => {
  test("All tab shows groups; row click drills into stage detail", async ({ page }) => {
    await page.goto("/");

    // Click the "All" tab pill in the topbar.
    await page
      .getByRole("tablist", { name: /issue list filter/i })
      .getByRole("tab", { name: "All" })
      .click();

    // At least one of the group headers should be visible.
    const groupHeader = page.getByText(/^(Backlog|Done|In Progress|Failed)$/).first();
    await expect(groupHeader).toBeVisible();

    // Click the first issue row (a div role="button" with PLATO-N text).
    const firstRow = page.locator("[data-stage]").first();
    await expect(firstRow).toBeVisible();
    await firstRow.click();

    // Stage detail surfaces a "Back to all stages" link/button.
    const back = page.getByRole("button", { name: /back to all stages/i });
    await expect(back).toBeVisible();

    // Returning lands us back on the workspace list.
    await back.click();
    await expect(page.locator("[data-stage]").first()).toBeVisible();
  });
});
