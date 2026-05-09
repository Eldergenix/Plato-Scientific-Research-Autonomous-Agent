import { test, expect, type Route } from "./fixtures";

const PROJECT_ID = "feed-project";
const PDF_URL = `/api/v1/projects/${PROJECT_ID}/files/paper/main.pdf`;

function project() {
  const stage = (id: string, label: string, status = "empty") => ({
    id,
    label,
    status,
    model: null,
    duration_ms: null,
    last_run_at: null,
    origin: null,
    progress_label: null,
  });
  return {
    id: PROJECT_ID,
    name: "Dark matter lensing paper",
    journal: "AAS",
    created_at: "2026-05-01T12:00:00Z",
    updated_at: "2026-05-08T12:00:00Z",
    total_tokens: 0,
    total_cost_cents: 0,
    user_id: "alice",
    cost_caps: null,
    approvals: null,
    publication_settings: {
      authors: [
        {
          id: "auth_ada",
          name: "Ada Lovelace",
          affiliation: "Analytical Engine Lab",
          role: "Lead author",
          order: 0,
        },
      ],
      dates: {},
      tasks: [],
    },
    stages: {
      data: stage("data", "Data", "done"),
      idea: stage("idea", "Idea", "done"),
      literature: stage("literature", "Lit", "done"),
      method: stage("method", "Method", "done"),
      results: stage("results", "Results", "done"),
      paper: stage("paper", "Paper", "done"),
      referee: stage("referee", "Referee"),
    },
    active_run: null,
  };
}

function publication(overrides: Record<string, unknown> = {}) {
  return {
    id: "pub_seed",
    project_id: PROJECT_ID,
    creator_user_id: "alice",
    creator_name: "Ada Lovelace",
    creator_affiliation: "Analytical Engine Lab",
    creator_avatar_url: "https://example.test/ada.png",
    title: "Dark matter lensing paper",
    description: "A concise first-page summary of the published research paper.",
    paper_pdf_url: PDF_URL,
    first_page_preview_url: PDF_URL,
    source_run_id: null,
    source_stage: "paper",
    authors: [
      {
        id: "auth_ada",
        name: "Ada Lovelace",
        affiliation: "Analytical Engine Lab",
        role: "Lead author",
      },
    ],
    tagged_authors: [],
    tags: ["cosmology"],
    published_at: "2026-05-08T12:00:00Z",
    updated_at: "2026-05-08T12:00:00Z",
    like_count: 0,
    comment_count: 0,
    share_count: 0,
    comments: [],
    ...overrides,
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

test.describe("papers publication feed", () => {
  test("renders the timeline, keeps the library view, and wires social actions", async ({ page }) => {
    let currentPublication = publication();

    await page.route("**/api/v1/projects", (route) => json(route, [project()]));
    await page.route(`**/api/v1/projects/${PROJECT_ID}/plots`, (route) => json(route, []));
    await page.route(`**/api/v1/projects/${PROJECT_ID}/runs`, (route) => json(route, []));
    await page.route(`**/api/v1/projects/${PROJECT_ID}/files/paper/main.pdf`, (route) =>
      route.fulfill({ status: 200, contentType: "application/pdf", body: "%PDF-1.5\n" }),
    );
    await page.route(`**/api/v1/projects/${PROJECT_ID}/files/paper/main.tex`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/plain",
        body: "\\section{Abstract} Lensing summary.",
      }),
    );
    await page.route("**/api/v1/publications?limit=100", (route) =>
      json(route, { publications: [currentPublication] }),
    );
    await page.route(`**/api/v1/projects/${PROJECT_ID}/publications`, async (route) => {
      currentPublication = publication({
        id: "pub_created",
        title: "Dark matter lensing paper",
        description: "Shared from the publish panel.",
      });
      await json(route, currentPublication, 201);
    });
    await page.route("**/api/v1/publications/*/likes/me", async (route) => {
      currentPublication = publication({ like_count: route.request().method() === "PUT" ? 1 : 0 });
      await json(route, currentPublication);
    });
    await page.route("**/api/v1/publications/*/comments", async (route) => {
      await json(
        route,
        {
          id: "cmt_1",
          publication_id: "pub_seed",
          user_id: "grace",
          user_name: "grace",
          body: "Excellent paper.",
          tagged_authors: [],
          created_at: "2026-05-08T12:05:00Z",
        },
        201,
      );
    });
    await page.route("**/api/v1/publications/*/shares", async (route) => {
      currentPublication = publication({ share_count: 1 });
      await json(route, currentPublication, 201);
    });
    await page.route("**/api/v1/publications/*/author-tags", async (route) => {
      currentPublication = publication({
        tagged_authors: [{ name: "Grace Hopper", affiliation: "Compiler Lab" }],
      });
      await json(route, currentPublication);
    });

    await page.goto("/papers");

    await expect(page.getByTestId("publication-feed")).toBeVisible();
    await expect(page.getByText("Ada Lovelace").first()).toBeVisible();
    await expect(page.getByText("Analytical Engine Lab").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Dark matter lensing paper" })).toBeVisible();
    await expect(page.getByTitle("Dark matter lensing paper first page preview")).toBeVisible();

    await page.getByRole("button", { name: "0 Like" }).click();
    await expect(page.getByRole("button", { name: "1 Like" })).toBeVisible();

    await page.getByLabel("Comment on Dark matter lensing paper").fill("Excellent paper.");
    await page.getByRole("button", { name: "Comment", exact: true }).click();
    await expect(page.getByText("Excellent paper.")).toBeVisible();

    await page.getByRole("button", { name: "0 Share" }).click();
    await expect(page.getByRole("button", { name: "1 Share" })).toBeVisible();

    await page.getByLabel("Tag authors on Dark matter lensing paper").fill("Grace Hopper");
    await page.getByRole("button", { name: "Tag" }).click();
    await expect(page.getByText("Grace Hopper")).toBeVisible();

    await page.getByRole("button", { name: "Library" }).first().click();
    await expect(page.getByText("Publication settings")).toBeVisible();

    await page.getByRole("tab", { name: "Feed" }).click();
    await page.getByRole("button", { name: "Publish paper" }).click();
    await expect(page.getByText("Published to the research feed.")).toBeVisible();
  });
});
