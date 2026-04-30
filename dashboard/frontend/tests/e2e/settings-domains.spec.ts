import { test, expect, type Route } from "@playwright/test";

/**
 * Settings → Domains: pick a profile, inspect its full schema, set it as
 * the user's default. The backend is mocked end-to-end so the spec is
 * deterministic and runs without the FastAPI service.
 */
test.describe("settings/domains", () => {
  const ASTRO = {
    name: "astro",
    retrieval_sources: ["semantic_scholar", "arxiv", "openalex", "ads"],
    keyword_extractor: "cmbagent",
    journal_presets: ["NONE", "AAS", "APS", "JHEP", "PASJ", "ICML", "NeurIPS"],
    executor: "cmbagent",
    novelty_corpus: "arxiv:astro-ph",
  };
  const BIOLOGY = {
    name: "biology",
    retrieval_sources: ["pubmed", "openalex", "semantic_scholar"],
    keyword_extractor: "mesh",
    journal_presets: ["NATURE", "CELL", "SCIENCE", "PLOS_BIO", "ELIFE", "NONE"],
    executor: "cmbagent",
    novelty_corpus: "pubmed",
  };

  test.beforeEach(async ({ page }) => {
    let storedDefault: string | null = null;

    await page.route("**/api/v1/domains", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ domains: [ASTRO, BIOLOGY], default: "astro" }),
      });
    });

    await page.route("**/api/v1/user/preferences", async (route: Route) => {
      const req = route.request();
      if (req.method() === "PUT") {
        const body = req.postDataJSON() as { default_domain: string };
        storedDefault = body.default_domain;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            default_domain: storedDefault,
            default_executor: null,
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          default_domain: storedDefault,
          default_executor: null,
        }),
      });
    });
  });

  test("renders biology card after switching the dropdown", async ({ page }) => {
    await page.goto("/settings/domains");

    // Header.
    await expect(
      page.getByRole("heading", { level: 1, name: "Domains" }),
    ).toBeVisible();

    // Astro is the default and renders first.
    await expect(page.getByTestId("domain-card-astro")).toBeVisible();

    // Open the selector and pick biology.
    await page.getByTestId("domain-selector-trigger").click();
    await page.getByTestId("domain-option-biology").click();

    // Biology card appears with the right sections.
    const card = page.getByTestId("domain-card-biology");
    await expect(card).toBeVisible();
    await expect(card.getByTestId("keyword-extractor")).toHaveText("mesh");
    await expect(card.getByTestId("executor")).toHaveText("cmbagent");
    await expect(card.getByTestId("novelty-corpus")).toHaveText("pubmed");

    // All retrieval-source chips render.
    const sourceList = card.getByTestId("retrieval-sources");
    await expect(sourceList).toContainText("pubmed");
    await expect(sourceList).toContainText("openalex");
    await expect(sourceList).toContainText("semantic_scholar");
  });

  test("Set as default surfaces the Default pill and a toast", async ({
    page,
  }) => {
    await page.goto("/settings/domains");

    // Switch to biology.
    await page.getByTestId("domain-selector-trigger").click();
    await page.getByTestId("domain-option-biology").click();

    const card = page.getByTestId("domain-card-biology");
    await expect(card).toBeVisible();

    // No default pill yet for biology.
    await expect(card.getByTestId("domain-default-pill")).toHaveCount(0);

    // Click "Set as default".
    await card.getByTestId("domain-set-default-button").click();

    // Toast confirms persistence.
    await expect(page.getByTestId("domains-toast")).toContainText(
      /biology set as default/i,
    );

    // Pill now reads "Default".
    await expect(card.getByTestId("domain-default-pill")).toBeVisible();
    await expect(card.getByTestId("domain-default-pill")).toContainText(
      "Default",
    );
  });
});
