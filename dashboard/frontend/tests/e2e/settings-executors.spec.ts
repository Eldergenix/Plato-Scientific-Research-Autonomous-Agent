import { test, expect, type Page } from "./fixtures";

/**
 * /settings/executors renders four executor entries fetched from
 * /api/v1/executors and lets the user pick one as default via
 * /api/v1/user/executor_preferences. Both endpoints are mocked here so
 * the spec runs without the backend.
 */

const FIXTURE_EXECUTORS = {
  default: "cmbagent",
  executors: [
    {
      name: "cmbagent",
      available: true,
      kind: "real" as const,
      description:
        "Default backend. Wraps cmbagent's planning + control loop.",
    },
    {
      name: "local_jupyter",
      available: false,
      kind: "lazy" as const,
      description: "Run generated code in a local Jupyter kernel.",
    },
    {
      name: "modal",
      available: false,
      kind: "stub" as const,
      description: "Modal Labs sandbox executor. Stub.",
    },
    {
      name: "e2b",
      available: false,
      kind: "stub" as const,
      description: "E2B sandbox executor. Stub.",
    },
  ],
};

async function mockExecutorApis(page: Page) {
  await page.route("**/api/v1/executors", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_EXECUTORS),
    });
  });
  await page.route(
    "**/api/v1/user/executor_preferences",
    async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ default_executor: "cmbagent" }),
        });
        return;
      }
      // PUT — echo the body back.
      const body = route.request().postDataJSON() as {
        default_executor: string;
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ default_executor: body.default_executor }),
      });
    },
  );
}

test.describe("/settings/executors", () => {
  test("renders four executors and shows the default card", async ({ page }) => {
    await mockExecutorApis(page);
    await page.goto("/settings/executors");

    await expect(
      page.getByRole("heading", { level: 1, name: "Executors" }),
    ).toBeVisible();

    // Open the selector dropdown and verify all four executors render.
    const trigger = page.getByTestId("executor-selector-trigger");
    await expect(trigger).toBeVisible();
    await trigger.click();

    for (const name of ["cmbagent", "local_jupyter", "modal", "e2b"]) {
      await expect(page.getByTestId(`executor-option-${name}`)).toBeVisible();
    }

    // Close the menu and confirm the default card is for cmbagent.
    await page.keyboard.press("Escape");
    const card = page.getByTestId("executor-card");
    await expect(card).toBeVisible();
    await expect(
      card.getByRole("heading", { name: "cmbagent" }),
    ).toBeVisible();
  });

  test("selecting e2b surfaces the stub warning callout", async ({ page }) => {
    await mockExecutorApis(page);
    await page.goto("/settings/executors");

    // Stub items aren't selectable from the radix menu, so we fall back to
    // matching the underlying state through a programmatic click on the
    // cmbagent option first to confirm the menu is interactive, then we
    // verify the stub-warning callout never appears for cmbagent.
    let card = page.getByTestId("executor-card");
    await expect(card).toBeVisible();
    await expect(
      card.getByTestId("executor-stub-warning"),
    ).toHaveCount(0);

    // Switch to local_jupyter via the menu — that's a non-stub picker
    // exercise — and confirm no stub warning shows.
    await page.getByTestId("executor-selector-trigger").click();
    await page.getByTestId("executor-option-local_jupyter").click();
    card = page.getByTestId("executor-card");
    await expect(
      card.getByRole("heading", { name: "local_jupyter" }),
    ).toBeVisible();
    await expect(card.getByTestId("executor-stub-warning")).toHaveCount(0);

    // Stubs (modal, e2b) are disabled in the radix menu — programmatically
    // surface them via the React state hatch by intercepting the click on
    // a disabled item: instead, drive the same code path by re-routing
    // the API to make e2b the persisted default and reload — that hits
    // the stub-warning render path without needing the user to pick it.
    await page.unroute("**/api/v1/user/executor_preferences");
    await page.route(
      "**/api/v1/user/executor_preferences",
      async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ default_executor: "e2b" }),
          });
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ default_executor: "e2b" }),
        });
      },
    );
    await page.reload();
    card = page.getByTestId("executor-card");
    await expect(card).toBeVisible();
    await expect(card.getByRole("heading", { name: "e2b" })).toBeVisible();
    await expect(card.getByTestId("executor-stub-warning")).toBeVisible();
    await expect(
      card.getByText(/Modal\/E2B require their respective SDKs/),
    ).toBeVisible();
  });
});
