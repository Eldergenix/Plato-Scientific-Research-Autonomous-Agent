import { test, expect } from "./fixtures";

/**
 * Sidebar navigation: Projects, Models, Costs.
 *
 * Each click should land on the corresponding route and surface its
 * <h1> heading. "Keys" is reachable only by direct URL (not in the
 * sidebar) so it's verified separately.
 */
test.describe("navigation", () => {
  test.describe.configure({ mode: "serial" });

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

  test("models, keys, and settings own their page scroll", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 520 });

    for (const path of ["/models", "/keys", "/settings"]) {
      await page.goto(path);
      const scroller = page.locator("#main-content > div").first();

      await expect(scroller).toHaveCSS(
        "overflow-y",
        "auto",
      );
      await expect
        .poll(() =>
          scroller.evaluate((node) => ({
            clientHeight: node.clientHeight,
            scrollHeight: node.scrollHeight,
          })),
        )
        .toMatchObject({ clientHeight: expect.any(Number), scrollHeight: expect.any(Number) });

      const didScroll = await scroller.evaluate((node) => {
        node.scrollTop = node.scrollHeight;
        return node.scrollTop > 0;
      });
      expect(didScroll).toBe(true);
    }
  });

  test("recommended model assignments accept typed model ids", async ({ page }) => {
    await page.goto("/models");

    const ideaModel = page.getByLabel("Idea model");
    await expect(ideaModel).toHaveValue("gpt-4.1");

    await ideaModel.fill("openai/custom-research-model");
    await ideaModel.blur();
    await expect(ideaModel).toHaveValue("openai/custom-research-model");

    await page.reload();
    await expect(page.getByLabel("Idea model")).toHaveValue(
      "openai/custom-research-model",
    );
  });
});
