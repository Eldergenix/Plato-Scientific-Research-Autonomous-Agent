import { test, expect } from "./fixtures";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3201";
const SELECTED_PROJECT_STORAGE_KEY = "plato:selected-project-id";

function makeProject(id: string, name: string, updatedAt: string) {
  const stage = (stageId: string, label: string) => ({
    id: stageId,
    label,
    status: "empty",
    model: null,
    duration_ms: null,
    last_run_at: null,
    origin: null,
    progress_label: null,
  });

  return {
    id,
    name,
    created_at: updatedAt,
    updated_at: updatedAt,
    journal: "NONE",
    stages: {
      data: stage("data", "Data"),
      idea: stage("idea", "Idea"),
      literature: stage("literature", "Lit"),
      method: stage("method", "Method"),
      results: stage("results", "Results"),
      paper: stage("paper", "Paper"),
      referee: stage("referee", "Referee"),
    },
    active_run: null,
    total_tokens: 0,
    total_cost_cents: 0,
    user_id: null,
    cost_caps: null,
    approvals: null,
  };
}

test.describe("projects page", () => {
  test("surfaces a plain-text backend error without tripping over the response body", async ({
    page,
  }) => {
    await page.route("**/api/v1/projects", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "text/plain",
        body: "Backend exploded",
      });
    });

    await page.goto("/projects");

    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    await expect(page.getByText("Backend exploded", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Failed to execute 'text' on 'Response': body stream already read"),
    ).toHaveCount(0);
  });

  test("opens the project created from the projects page in the workspace", async ({
    page,
  }) => {
    const existingProject = makeProject(
      "older-route-default",
      "Existing workspace project",
      "2026-05-06T12:00:00.000Z",
    );
    const createdProject = makeProject(
      "created-from-projects-page",
      "Created from Projects E2E",
      "2026-05-01T12:00:00.000Z",
    );
    let projects = [existingProject];

    await page.route("**/api/v1/projects/*/plots", async (route) => {
      expect(route.request().headers()["cookie"]).toContain("plato_user=alice");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      });
    });
    await page.route("**/api/v1/projects/*/runs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      });
    });
    await page.route("**/api/v1/projects", async (route) => {
      if (route.request().method() === "POST") {
        projects = [createdProject, existingProject];
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(createdProject),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(projects),
      });
    });

    await page.addInitScript((key) => {
      if (window.location.pathname === "/projects") {
        window.localStorage.removeItem(key);
      }
    }, SELECTED_PROJECT_STORAGE_KEY);
    await page.context().addCookies([
      {
        name: "plato_user",
        value: "alice",
        url: BASE_URL,
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
    await page.goto("/projects");

    await page
      .locator("main")
      .getByRole("button", { name: "New project" })
      .click();
    await page
      .getByRole("dialog", { name: "New project" })
      .getByRole("textbox", { name: "e.g. GW231123 ringdown analysis" })
      .fill(createdProject.name);
    await page.getByRole("button", { name: "Create project" }).click();

    await expect(page).toHaveURL("/");
    await expect(
      page.getByRole("heading", { name: createdProject.name }),
    ).toBeVisible();

    await page.goto("/keys");
    await expect(
      page.getByRole("button", { name: createdProject.name }),
    ).toBeVisible();
  });

  test("rolls back and explains failed project deletion", async ({ page }) => {
    const lockedProject = makeProject(
      "locked-lab-project",
      "Locked Lab Project",
      "2026-05-06T12:00:00.000Z",
    );

    await page.route("**/api/v1/projects/locked-lab-project", async (route) => {
      if (route.request().method() === "DELETE") {
        await route.fulfill({
          status: 403,
          contentType: "text/plain",
          body: "Project belongs to another Lab",
        });
        return;
      }
      await route.fallback();
    });
    await page.route("**/api/v1/projects", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([lockedProject]),
      });
    });
    page.on("dialog", (dialog) => dialog.accept());

    await page.goto("/projects");
    const projectRow = page.locator('[data-project-id="locked-lab-project"]');
    await expect(projectRow).toBeVisible();

    await page.getByLabel("Delete project Locked Lab Project").click();

    await expect(projectRow).toBeVisible();
    await expect(
      page.getByText("Could not delete Locked Lab Project: Project belongs to another Lab"),
    ).toBeVisible();
  });
});
