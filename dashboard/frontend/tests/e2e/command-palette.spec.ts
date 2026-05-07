import { test, expect } from "./fixtures";

/**
 * The topbar trigger opens the command palette. Typing filters the list,
 * Escape closes it.
 *
 * The placeholder is "Search projects, run a stage, switch model…"
 * (cmdk's <Command.Input> renders a real <input>). We locate it by a
 * substring match so the test stays resilient to copy tweaks.
 */
test.describe("command palette", () => {
  test("opens from the topbar trigger, filters on input, closes on Escape", async ({ page }) => {
    await page.goto("/");

    const trigger = page.getByRole("button", { name: "Open command palette" });
    await expect(trigger).toBeVisible();
    await trigger.click();

    // Input — placeholder mentions "Search projects".
    const input = page.getByPlaceholder(/Search projects/i);
    await expect(input).toBeVisible();

    // Type "model" — the "Models" navigate item should remain visible
    // while at least one unrelated item gets filtered out.
    await input.fill("model");
    const modelItem = page.getByRole("option", { name: /^Models$/ });
    await expect(modelItem).toBeVisible();
    await expect(page.getByRole("option", { name: "Settings" })).toHaveCount(0);

    // Escape closes.
    await page.keyboard.press("Escape");
    await expect(input).not.toBeVisible();
  });
});
