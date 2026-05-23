import { expect, test } from "@playwright/test";

test.describe("self-hosted Clerk proxy boundary", () => {
  test.skip(
    process.env.PLAYWRIGHT_EXPECT_CLERK_AUTH === "1" ||
      process.env.PLAYWRIGHT_EXPECT_HOSTED_PROXY_SECRET_ERROR === "1",
    "Hosted mode enables or validates the Clerk frontend proxy.",
  );

  test("Clerk frontend proxy is disabled outside hosted auth mode", async ({ page }) => {
    const response = await page.goto("/__clerk/v1/client");
    const body = await page.locator("body").textContent();

    expect(response?.status()).toBe(404);
    expect(body).toContain("clerk_proxy_disabled");
  });
});

test.describe("self-hosted API tenant boundary", () => {
  test.skip(
    process.env.PLAYWRIGHT_EXPECT_CLERK_AUTH === "1" ||
      process.env.PLAYWRIGHT_EXPECT_HOSTED_PROXY_SECRET_ERROR === "1",
    "Hosted mode derives or validates tenant identity through Clerk.",
  );

  test("API proxy ignores spoofed X-Plato-User when no tenant cookie exists", async ({ page }) => {
    await page.goto("/");

    const result = await page.evaluate(async () => {
      const response = await fetch("/api/v1/auth/me", {
        headers: { "X-Plato-User": "bob" },
      });
      return { status: response.status, body: await response.json() };
    });

    expect(result.status).toBe(200);
    expect(result.body.user_id).toBeNull();
  });

  test("API proxy prefers the tenant cookie over spoofed X-Plato-User", async ({ page }) => {
    await page.goto("/");
    await page.context().addCookies([
      {
        name: "plato_user",
        value: "alice",
        url: page.url(),
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);

    const result = await page.evaluate(async () => {
      const response = await fetch("/api/v1/auth/me", {
        headers: { "X-Plato-User": "bob" },
      });
      return { status: response.status, body: await response.json() };
    });

    expect(result.status).toBe(200);
    expect(result.body.user_id).toBe("alice");
  });
});

test.describe("hosted Clerk auth boundary", () => {
  test.skip(
    process.env.PLAYWRIGHT_EXPECT_CLERK_AUTH !== "1",
    "Run with hosted Clerk env to verify the production auth boundary.",
  );

  test("private API requests fail closed before reaching the backend", async ({ page }) => {
    const response = await page.goto("/api/v1/projects");
    const body = await page.locator("body").textContent();

    if (response?.status() === 400) {
      expect(body).toContain("host_invalid");
      expect(body).toContain("Invalid host");
      return;
    }
    if (response?.status() === 503) {
      expect(body).toContain("clerk_auth_misconfigured");
      expect(body).toContain("Clerk keys are missing or invalid");
      return;
    }

    expect(response?.status()).toBe(401);
    expect(body).toContain("auth_required");
    expect(body).toContain("Sign in with Clerk before accessing Plato.");
  });

  test("hosted auth ignores stale self-hosted tenant cookies", async ({ page }) => {
    await page.goto("/");
    await page.context().addCookies([
      {
        name: "plato_user",
        value: "alice",
        url: page.url(),
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);

    const result = await page.evaluate(async () => {
      const response = await fetch("/api/v1/auth/me");
      return { status: response.status, body: await response.json() };
    });

    expect(result.status).toBe(200);
    expect(result.body.user_id).toBeNull();
  });

  test("only publication feed and detail reads are public in hosted mode", async ({ page }) => {
    const publicFeed = await page.goto("/api/v1/publications");
    expect([200, 404, 503]).toContain(publicFeed?.status());

    const nested = await page.goto("/api/v1/publications/example/comments");
    const body = await page.locator("body").textContent();

    if (nested?.status() === 400) {
      expect(body).toContain("host_invalid");
      expect(body).toContain("Invalid host");
      return;
    }
    if (nested?.status() === 503) {
      expect(body).toContain("clerk_auth_misconfigured");
      expect(body).toContain("Clerk keys are missing or invalid");
      return;
    }

    expect(nested?.status()).toBe(401);
    expect(body).toContain("auth_required");
  });

  test("Clerk frontend proxy reports invalid hosted config", async ({ page }) => {
    const response = await page.goto("/__clerk/v1/client");
    const body = await page.locator("body").textContent();

    if (response?.status() === 503) {
      expect(body).toContain("clerk_auth_misconfigured");
      expect(body).toContain("Clerk keys are missing or invalid");
      return;
    }

    expect(response?.status()).not.toBe(404);
    expect(body).not.toContain("clerk_proxy_disabled");
  });

  test("account and organization settings show hosted config errors", async ({ page }) => {
    await page.goto("/settings/account");
    await expect(page.getByTestId("account-auth-config-error")).toBeVisible();
    await expect(page.getByText("Clerk auth is misconfigured").first()).toBeVisible();
    await expect(
      page.getByText("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is missing or invalid."),
    ).toBeVisible();
    await expect(page.getByTestId("account-settings-fallback")).toHaveCount(0);

    await page.goto("/settings/organization");
    await expect(page.getByTestId("organization-auth-config-error")).toBeVisible();
    await expect(page.getByText("Clerk auth is misconfigured").first()).toBeVisible();
    await expect(
      page.getByText("Hosted Lab settings are unavailable"),
    ).toBeVisible();
    await expect(page.getByTestId("organization-settings-fallback")).toHaveCount(0);
  });

  test("login entry points show hosted config errors instead of local login", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByTestId("login-auth-config-error")).toBeVisible();
    await expect(page.getByText("Clerk auth is misconfigured").first()).toBeVisible();
    await expect(
      page.getByText("Hosted sign-in was requested, but Clerk keys are missing or invalid."),
    ).toBeVisible();
    await expect(
      page.getByText("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is missing or invalid."),
    ).toBeVisible();
    await expect(page.getByTestId("login-form")).toHaveCount(0);

    await page.goto("/sign-in");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByTestId("login-auth-config-error")).toBeVisible();

    await page.goto("/sign-up");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByTestId("login-auth-config-error")).toBeVisible();
  });

  test("local auth mutation endpoints are disabled in hosted mode", async ({ page }) => {
    await page.goto("/");

    const login = await page.evaluate(async () => {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ user_id: "alice" }),
      });
      return { status: response.status, body: await response.text() };
    });
    const logout = await page.evaluate(async () => {
      const response = await fetch("/api/v1/auth/logout", { method: "POST" });
      return { status: response.status, body: await response.text() };
    });
    const cookies = await page.context().cookies();

    for (const result of [login, logout]) {
      if (result.status === 503) {
        expect(result.body).toContain("clerk_auth_misconfigured");
        expect(result.body).toContain("Clerk keys are missing or invalid");
      } else {
        expect(result.status).toBe(404);
        expect(result.body).toContain("local_auth_disabled");
      }
    }
    expect(cookies.some((cookie) => cookie.name === "plato_user")).toBe(false);
  });

  test("billing shows hosted config errors instead of self-hosted billing", async ({ page }) => {
    await page.goto("/settings/billing");
    await expect(page.getByTestId("billing-auth-config-error")).toBeVisible();
    await expect(page.getByText("Hosted billing is misconfigured").first()).toBeVisible();
    await expect(
      page.getByText("Hosted billing, sign-in, and Lab subscription controls are unavailable"),
    ).toBeVisible();
    await expect(
      page.getByText("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is missing or invalid."),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Hosted billing disabled" })).toHaveCount(0);
    await expect(page.getByText("hosted config error")).toBeVisible();
  });

  test("private API requests ignore spoofed tenant headers", async ({ page }) => {
    await page.goto("/");

    const result = await page.evaluate(async () => {
      const response = await fetch("/api/v1/projects", {
        headers: {
          "X-Plato-User": "lab_org_spoofed",
          "X-Plato-Lab-Id": "org_spoofed",
        },
      });
      return { status: response.status, body: await response.text() };
    });

    if (result.status === 400) {
      expect(result.body).toContain("host_invalid");
      expect(result.body).toContain("Invalid host");
      return;
    }
    if (result.status === 503) {
      expect(result.body).toContain("clerk_auth_misconfigured");
      expect(result.body).toContain("Clerk keys are missing or invalid");
      return;
    }

    expect(result.status).toBe(401);
    expect(result.body).toContain("auth_required");
    expect(result.body).toContain("Sign in with Clerk before accessing Plato.");
  });
});

test.describe("hosted backend proxy secret boundary", () => {
  test.skip(
    process.env.PLAYWRIGHT_EXPECT_HOSTED_PROXY_SECRET_ERROR !== "1",
    "Run with hosted auth requested but no explicit or derived backend proxy secret.",
  );

  test("hosted Clerk mode fails loud without backend proxy protection", async ({ page }) => {
    const response = await page.goto("/api/v1/projects");
    const body = await page.locator("body").textContent();

    expect(response?.status()).toBe(503);
    expect(body).toContain("clerk_auth_misconfigured");
    expect(body).toContain("CLERK_SECRET_KEY is unavailable for derived backend proxy protection");

    await page.goto("/settings/billing");
    await expect(page.getByTestId("billing-auth-config-error")).toBeVisible();
    await expect(
      page.getByText("CLERK_SECRET_KEY is unavailable for derived backend proxy protection"),
    ).toBeVisible();
    await expect(page.getByText("hosted config error")).toBeVisible();

    await page.goto("/settings/account");
    await expect(page.getByTestId("account-auth-config-error")).toBeVisible();
    await expect(
      page.getByText("CLERK_SECRET_KEY is unavailable for derived backend proxy protection"),
    ).toBeVisible();
    await expect(page.getByTestId("account-settings-fallback")).toHaveCount(0);

    await page.goto("/settings/organization");
    await expect(page.getByTestId("organization-auth-config-error")).toBeVisible();
    await expect(
      page.getByText("CLERK_SECRET_KEY is unavailable for derived backend proxy protection"),
    ).toBeVisible();
    await expect(page.getByTestId("organization-settings-fallback")).toHaveCount(0);
  });
});
