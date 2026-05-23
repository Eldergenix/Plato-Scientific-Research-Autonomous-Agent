import { defineConfig, devices } from "@playwright/test";

if (process.env.NO_COLOR && process.env.FORCE_COLOR) {
  delete process.env.NO_COLOR;
  delete process.env.FORCE_COLOR;
}

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3201";
const shouldStartServer = !process.env.PLAYWRIGHT_BASE_URL;

/**
 * Playwright configuration for the Plato dashboard frontend.
 *
 * - baseURL defaults to a dedicated dev server on port 3201, or PLAYWRIGHT_BASE_URL.
 * - testDir lives next to the frontend at ./tests/e2e.
 * - Chromium-only for speed (CI parity is not yet required).
 * - when no override is provided, the webServer harness builds and starts the
 *   production Next server plus a tiny mock backend for API proxy boundary tests.
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
        command:
          "env -u FORCE_COLOR -u NO_COLOR npm run build && env -u FORCE_COLOR -u NO_COLOR PLAYWRIGHT_NEXT_SCRIPT=start node scripts/playwright-web-server.mjs",
        url: baseURL,
        reuseExistingServer: false,
        timeout: 60_000,
      }
    : undefined,
});
