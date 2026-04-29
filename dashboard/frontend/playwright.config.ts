import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for the Plato dashboard frontend.
 *
 * - baseURL points at the dev server on port 3001.
 * - testDir lives next to the frontend at ./tests/e2e.
 * - Chromium-only for speed (CI parity is not yet required).
 * - reuseExistingServer: true so we attach to a running `npm run dev`.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"]],

  use: {
    baseURL: "http://localhost:3001",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    command: "npm run dev -- --port 3001",
    url: "http://localhost:3001",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
