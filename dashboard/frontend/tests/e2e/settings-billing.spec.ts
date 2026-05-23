import { test, expect } from "./fixtures";

test.describe("settings/billing", () => {
  test("links to account and organization settings", async ({ page }) => {
    await page.goto("/settings");

    const accountLink = page.getByRole("link", { name: /Account/ });
    const organizationLink = page.getByRole("link", { name: /Organization/ });

    await expect(accountLink).toBeVisible();
    await expect(organizationLink).toBeVisible();
    await expect(accountLink).toHaveAttribute(
      "href",
      "/settings/account",
    );
    await expect(organizationLink).toHaveAttribute(
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
    test.skip(
      process.env.PLAYWRIGHT_EXPECT_HOSTED_BILLING_CONFIG_ERROR === "1",
      "Hosted billing config mode replaces the self-hosted billing fallback.",
    );

    await page.goto("/settings/billing");

    await expect(page.getByRole("heading", { level: 1, name: "Labs & billing" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: "Free BYOK" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: "Pro" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: "Researcher" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: "Lab Standard" })).toBeVisible();
    await expect(page.getByText("2 papers / week").first()).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Hosted billing disabled" })).toBeVisible();
    await expect(page.getByText("NEXT_PUBLIC_PLATO_AUTH_PROVIDER=clerk")).toBeVisible();
  });
});

test.describe("settings/billing hosted config boundary", () => {
  test.skip(
    process.env.PLAYWRIGHT_EXPECT_HOSTED_BILLING_CONFIG_ERROR !== "1",
    "Run with hosted billing requested but Clerk auth disabled.",
  );

  test("fails loud when hosted billing is requested without Clerk auth", async ({ page }) => {
    await page.goto("/settings/billing");

    await expect(page.getByTestId("billing-auth-config-error")).toBeVisible();
    await expect(page.getByText("Hosted billing is misconfigured")).toBeVisible();
    await expect(
      page.getByText("NEXT_PUBLIC_PLATO_HOSTED_BILLING=enabled requires Clerk auth"),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Hosted billing disabled" })).toHaveCount(0);
    await expect(page.getByText("hosted config error")).toBeVisible();
  });
});
