import { test, expect } from "./fixtures";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3001";
const SPLINE_VIEWER_SRC =
  "https://unpkg.com/@splinetool/viewer@1.12.94/build/spline-viewer.js";
const SPLINE_SCENE_URL =
  "https://prod.spline.design/L3ajUTEjDj55mxCT/scene.splinecode";

test.describe("landing", () => {
  test.beforeEach(async ({ page }) => {
    await page.route(SPLINE_VIEWER_SRC, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/javascript",
        body: "customElements.define('spline-viewer', class extends HTMLElement {})",
      });
    });
  });

  test("renders the full-viewport Spline scene and enter CTA", async ({ page }) => {
    await page.goto("/landing");

    const viewer = page.locator("spline-viewer");
    await expect(viewer).toHaveAttribute("url", SPLINE_SCENE_URL);

    const box = await viewer.boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(1200);
    expect(box?.height).toBeGreaterThanOrEqual(700);

    const enter = page.getByTestId("landing-enter");
    await expect(enter).toBeVisible();
    await expect(enter).toHaveText("enter");
    await expect(enter).toHaveAttribute("href", "/login?next=%2F");

    await enter.click();
    await expect(page).toHaveURL(/\/login\?next=%2F$/);
  });

  test("redirects tenant-authenticated visitors to the app root", async ({ page }) => {
    await page.context().addCookies([
      {
        name: "plato_user",
        value: "alice",
        url: BASE_URL,
      },
    ]);

    await page.goto("/landing");
    await page.waitForURL("**/");
    expect(new URL(page.url()).pathname).toBe("/");
  });
});
