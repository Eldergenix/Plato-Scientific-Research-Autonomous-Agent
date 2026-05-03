import { test, expect } from "./fixtures";

/**
 * Sidebar navigation: Projects, Models, Costs.
 *
 * Each click should land on the corresponding route and surface its
 * <h1> heading. "Keys" is reachable only by direct URL (not in the
 * sidebar) so it's verified separately.
 */
test.describe("navigation", () => {
  test("sidebar links navigate to Projects, Models, Costs", async ({ page }) => {
    await page.goto("/");

    const sidebar = page.getByRole("complementary", { name: /primary navigation/i });

    // Models
    await sidebar.getByRole("link", { name: "Models" }).click();
    await expect(page).toHaveURL(/\/models$/);
    await expect(page.getByRole("heading", { level: 1, name: "Models" })).toBeVisible();

    // Costs
    await page.goto("/");
    await page.getByRole("complementary", { name: /primary navigation/i })
      .getByRole("link", { name: "Costs" })
      .click();
    await expect(page).toHaveURL(/\/costs$/);
    await expect(page.getByRole("heading", { level: 1, name: "Costs" })).toBeVisible();

    // Projects: the sidebar "Projects" link now points to "/projects".
    await page.goto("/");
    await page.getByRole("complementary", { name: /primary navigation/i })
      .getByRole("link", { name: "Projects", exact: true })
      .click();
    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
  });

  test("Keys page is reachable by direct URL", async ({ page }) => {
    await page.goto("/keys");
    await expect(page.getByRole("heading", { level: 1, name: /API keys/i })).toBeVisible();
  });
});
