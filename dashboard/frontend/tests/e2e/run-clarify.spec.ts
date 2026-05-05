import { test, expect, type Route } from "./fixtures";

/**
 * Clarifying-questions full-page flow.
 *
 * The backend is mocked via ``page.route``: a GET returns three
 * questions, then a POST is intercepted, asserted-on, and answered 200.
 */
test.describe("run clarify page", () => {
  const RUN_ID = "run_e2e_clarify";

  const QUESTIONS = [
    "Which detector should we focus on?",
    "What window of strain data are we using?",
    "What's the target signal-to-noise ratio?",
  ];

  test("opens modal, requires all answers, posts on submit", async ({
    page,
  }) => {
    let postPayload: { answers: string[] } | null = null;
    let submitted = false;

    await page.route(
      `**/api/v1/runs/${RUN_ID}/clarifications`,
      async (route: Route) => {
        const req = route.request();
        if (req.method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              questions: QUESTIONS,
              needs_clarification: true,
              answers_submitted: submitted,
            }),
          });
          return;
        }
        if (req.method() === "POST") {
          postPayload = JSON.parse(req.postData() ?? "{}") as {
            answers: string[];
          };
          submitted = true;
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ ok: true, answers_count: 3 }),
          });
          return;
        }
        await route.fallback();
      },
    );

    await page.goto(`/runs/clarify?runId=${RUN_ID}`);

    // Header card surfaces the run id.
    await expect(page.getByTestId("clarify-header")).toContainText(RUN_ID);

    // Modal is open by default on the full-page route.
    const modal = page.getByTestId("clarifying-questions-modal");
    await expect(modal).toBeVisible();

    // Three textareas, one per question.
    const answers = modal.getByTestId(/^clarifying-answer-/);
    await expect(answers).toHaveCount(3);

    // Submit is disabled until every answer is non-empty.
    const submit = modal.getByTestId("clarifying-submit");
    await expect(submit).toBeDisabled();

    // Fill them in.
    await modal.getByTestId("clarifying-answer-0").fill("H1 only");
    await modal.getByTestId("clarifying-answer-1").fill("32 ms post-merger");
    // Whitespace-only doesn't count.
    await modal.getByTestId("clarifying-answer-2").fill("   ");
    await expect(submit).toBeDisabled();

    await modal.getByTestId("clarifying-answer-2").fill("8 sigma");
    await expect(submit).toBeEnabled();

    await submit.click();

    // Once the POST resolves the page refetches and the inline step
    // collapses to the durable "Answers submitted" state.
    await expect(page.getByTestId("clarifier-submitted-badge")).toBeVisible();
    await expect(modal).toBeHidden();

    // Verify the POST body shape.
    expect(postPayload).not.toBeNull();
    expect(postPayload!.answers).toEqual([
      "H1 only",
      "32 ms post-merger",
      "8 sigma",
    ]);
  });
});
