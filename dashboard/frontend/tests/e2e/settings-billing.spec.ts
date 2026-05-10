import { test, expect } from "./fixtures";

test.describe("settings/billing", () => {
  test("links to account and organization settings", async ({ page }) => {
    await page.goto("/settings");

    await expect(page.getByTestId("settings-link-account")).toBeVisible();
    await expect(page.getByTestId("settings-link-organization")).toBeVisible();
    await expect(page.getByTestId("settings-link-account")).toHaveAttribute(
      "href",
      "/settings/account",
    );
    await expect(page.getByTestId("settings-link-organization")).toHaveAttribute(
      "href",
      "/settings/organization",
    );
  });

  test("renders self-hosted account and organization fallbacks", async ({ page }) => {
    await page.goto("/settings/account");
    await expect(page.getByRole("heading", { level: 1, name: "Account" })).toBeVisible();
    await expect(page.getByTestId("account-settings-fallback")).toBeVisible();
    await expect(page.getByText("Local sign-in is active")).toBeVisible();
    await expect(page.getByText("Your User ID scopes projects")).toBeVisible();

    await page.goto("/settings/organization");
    await expect(page.getByRole("heading", { level: 1, name: "Organization" })).toBeVisible();
    await expect(page.getByTestId("organization-settings-fallback")).toBeVisible();
    await expect(page.getByText("Clerk Organizations become Plato Labs")).toBeVisible();
  });

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
