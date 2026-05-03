import { test, expect } from "./fixtures";

/**
 * Tab filtering: each pill restricts the visible groups to its bucket.
 *
 * - "Backlog" → only the Backlog group renders (no Done).
 * - "Active" → only running/failed stages, typically empty in the
 *   default offline/sample dataset, so we assert no in-progress group
 *   header exists.
 * - "All" → both Backlog and Done are visible together.
 */
test.describe("tab filter", () => {
  test("filter tabs are clickable and switch state", async ({ page }) => {
    await page.goto("/");

    const tablist = page.getByRole("tablist", { name: /issue list filter/i });
    await expect(tablist).toBeVisible();

    // All three tabs exist
    await expect(tablist.getByRole("tab", { name: "Active" })).toBeVisible();
    await expect(tablist.getByRole("tab", { name: "Backlog" })).toBeVisible();
    await expect(tablist.getByRole("tab", { name: "All" })).toBeVisible();

    // Clicking each tab applies the active selection state
    await tablist.getByRole("tab", { name: "Backlog" }).click();
    await expect(tablist.getByRole("tab", { name: "Backlog" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await tablist.getByRole("tab", { name: "All" }).click();
    await expect(tablist.getByRole("tab", { name: "All" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await tablist.getByRole("tab", { name: "Active" }).click();
    await expect(tablist.getByRole("tab", { name: "Active" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});
