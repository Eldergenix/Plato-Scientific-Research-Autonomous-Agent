import { test, expect } from "./fixtures";

/**
 * Top-level smoke test: every page-load surface is present and rendered.
 *
 * Asserts the sidebar workspace name, a non-empty topbar title, and at
 * least one filter tab pill ("Active" / "Backlog" / "All"). Captures a
 * screenshot for visual regression baselining.
 */
test.describe("smoke", () => {
  test("home page renders sidebar, topbar, and filter pills", async ({ page }) => {
    await page.goto("/");

    // Sidebar: workspace label "Plato" lives in the top-left chip.
    const sidebar = page.getByRole("complementary", { name: /primary navigation/i });
    await expect(sidebar).toBeVisible();
    await expect(sidebar.getByText("Plato", { exact: true })).toBeVisible();

    // Topbar: project name renders as <h1> with a non-empty string.
    const projectTitle = page.locator("header[role='banner'] h1").first();
    await expect(projectTitle).toBeVisible();
    const titleText = (await projectTitle.textContent()) ?? "";
    expect(titleText.trim().length).toBeGreaterThan(0);

    // At least one filter pill should be present in the tablist.
    const tablist = page.getByRole("tablist", { name: /issue list filter/i });
    await expect(tablist).toBeVisible();
    const tabCount = await tablist.getByRole("tab").count();
    expect(tabCount).toBeGreaterThanOrEqual(1);
    await expect(
      tablist.getByRole("tab").filter({ hasText: /^(Active|Backlog|All)$/ }).first(),
    ).toBeVisible();

    // Visual regression baseline.
    await page.screenshot({ path: "test-results/smoke-home.png", fullPage: false });
  });
});
