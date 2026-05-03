import { test, expect, type Page } from "./fixtures";

/**
 * /settings/executors renders four executor entries fetched from
 * /api/v1/executors and lets the user pick one as default via
 * /api/v1/user/executor_preferences. Both endpoints are mocked here so
 * the spec runs without the backend.
 */

// Iter-21 update: after iter-18/20 made local_jupyter / modal / e2b
// real implementations, the backend probes their SDKs and reports
// kind="real" when available or kind="lazy" when missing — never
// "stub" for shipped backends. The fixture mirrors that. We retain
// one synthetic "stub" entry in a separate test to exercise the
// stub-warning render path without hard-coding modal/e2b as fakes.
const FIXTURE_EXECUTORS = {
  default: "cmbagent",
  executors: [
    {
      name: "cmbagent",
      available: true,
      kind: "real" as const,
      description:
        "Historical default. Wraps cmbagent's planning + control loop.",
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
      kind: "lazy" as const,
      description: "Modal Labs sandbox executor.",
    },
    {
      name: "e2b",
      available: false,
      kind: "lazy" as const,
      description: "E2B Code Interpreter sandbox executor.",
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

  test("kind=stub backend surfaces the stub warning callout", async ({ page }) => {
    // Iter-21 update: modal/e2b are no longer stubs (backend probes the
    // SDK at request time), so the stub warning render path is now only
    // exercised by an explicitly-stub backend. We add a synthetic
    // "future_backend" entry with kind="stub" so the test still pins
    // the warning's render contract without hard-coding modal/e2b as
    // stubs in the fixture.
    const stubFixture = {
      ...FIXTURE_EXECUTORS,
      executors: [
        ...FIXTURE_EXECUTORS.executors,
        {
          name: "future_backend",
          available: false,
          kind: "stub" as const,
          description: "Synthetic stub backend used to exercise the warning UI.",
        },
      ],
    };
    await page.route("**/api/v1/executors", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(stubFixture),
      });
    });
    await page.route(
      "**/api/v1/user/executor_preferences",
      async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ default_executor: "future_backend" }),
          });
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ default_executor: "future_backend" }),
        });
      },
    );
    await page.goto("/settings/executors");

    const card = page.getByTestId("executor-card");
    await expect(card).toBeVisible();
    await expect(
      card.getByRole("heading", { name: "future_backend" }),
    ).toBeVisible();
    await expect(card.getByTestId("executor-stub-warning")).toBeVisible();
    await expect(
      card.getByText(/registered as a stub/i),
    ).toBeVisible();

    // Real backends (modal/e2b are now kind="lazy" not "stub") must NOT
    // show the stub warning even when selected as default.
    await page.unroute("**/api/v1/executors");
    await page.unroute("**/api/v1/user/executor_preferences");
    await mockExecutorApis(page);
    await page.reload();
    const realCard = page.getByTestId("executor-card");
    await expect(realCard).toBeVisible();
    await expect(realCard.getByTestId("executor-stub-warning")).toHaveCount(0);
  });
});
