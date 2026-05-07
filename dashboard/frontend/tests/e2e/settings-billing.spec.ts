import { test, expect } from "./fixtures";

test.describe("settings/billing", () => {
  test("renders Labs billing contract in self-hosted mode", async ({ page }) => {
    await page.goto("/settings/billing");

    await expect(page.getByRole("heading", { level: 1, name: "Labs & billing" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: "Free BYOK" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: "Pro" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: "Researcher" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: "Lab Standard" })).toBeVisible();
    await expect(page.getByText("2 papers / week")).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Hosted billing disabled" })).toBeVisible();
    await expect(page.getByText("NEXT_PUBLIC_PLATO_AUTH_PROVIDER=clerk")).toBeVisible();
  });
});
