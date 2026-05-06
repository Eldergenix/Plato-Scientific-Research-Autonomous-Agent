import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3001";
const shouldStartServer = !process.env.PLAYWRIGHT_BASE_URL;

/**
 * Playwright configuration for the Plato dashboard frontend.
 *
 * - baseURL defaults to the dev server on port 3001, or PLAYWRIGHT_BASE_URL.
 * - testDir lives next to the frontend at ./tests/e2e.
 * - Chromium-only for speed (CI parity is not yet required).
 * - when no override is provided, reuseExistingServer attaches to `npm run dev`.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"]],

  use: {
    baseURL,
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

  webServer: shouldStartServer
    ? {
        command: "npm run dev -- --port 3001",
        url: baseURL,
        reuseExistingServer: true,
        timeout: 60_000,
      }
    : undefined,
});
