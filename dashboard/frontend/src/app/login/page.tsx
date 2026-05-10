"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";
import { useAuth } from "@/components/auth/auth-context";
import { LoginForm } from "@/components/auth/login-form";
import { UserMenu } from "@/components/auth/user-menu";
import { Button } from "@/components/ui/button";
import { isClerkAuthEnabled } from "@/lib/auth-mode";

// AuthProvider is mounted once at the root in src/app/layout.tsx. A
// previous version of this file double-wrapped, which caused two
// independent /api/v1/auth/me fetches per render.
export default function LoginPage() {
  return (
    <React.Suspense fallback={<LoginPageShell />}>
      <LoginPageContent />
    </React.Suspense>
  );
}

function LoginPageContent() {
  const redirectTo = useLoginRedirectPath();

  if (isClerkAuthEnabled()) {
    return <ClerkLoginPage redirectTo={redirectTo} />;
  }

  return <TenantLoginPage redirectTo={redirectTo} />;
}

function LoginPageShell() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-(--color-bg-page) p-6">
      <div
        className="surface-linear-card h-[192px] w-full max-w-[420px]"
        data-testid="login-card"
      />
    </main>
  );
}

function useLoginRedirectPath(): string {
  const searchParams = useSearchParams();
  const next = searchParams.get("next");

  if (!next || !next.startsWith("/") || next.startsWith("//")) {
    return "/";
  }

  if (next === "/login" || next.startsWith("/login?")) {
    return "/";
  }

  return next;
}

function TenantLoginPage({ redirectTo }: { redirectTo: string }) {
  const { user_id } = useAuth();
  return (
    <main className="flex min-h-screen items-center justify-center bg-(--color-bg-page) p-6">
      <div
        className="surface-linear-card w-full max-w-[400px] overflow-hidden"
        data-testid="login-card"
      >
        <header className="flex items-start justify-between gap-3 border-b border-[#1D1D1F] px-5 py-4">
          <div>
            <h1 className="text-[16px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
              Sign in to Plato
            </h1>
            <p className="mt-1 text-[12px] leading-[1.5] text-(--color-text-tertiary-spec)">
              Enter the user id you want to use as your tenant. The dashboard
              sets the X-Plato-User header for all requests.
            </p>
          </div>
          {user_id ? <UserMenu /> : null}
        </header>

        <div className="px-5 py-5">
          <LoginForm redirectTo={redirectTo} />
        </div>
      </div>
    </main>
  );
}

function ClerkLoginPage({ redirectTo }: { redirectTo: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-(--color-bg-page) p-6">
      <div
        className="surface-linear-card w-full max-w-[420px] overflow-hidden"
        data-testid="login-card"
      >
        <header className="flex items-start justify-between gap-3 border-b border-[#1D1D1F] px-5 py-4">
          <div>
            <h1 className="text-[16px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
              Sign in to Plato
            </h1>
            <p className="mt-1 text-[12px] leading-[1.5] text-(--color-text-tertiary-spec)">
              Use your Clerk account, then choose a personal workspace or Lab.
            </p>
          </div>
          <Show when="signed-in">
            <UserButton />
          </Show>
        </header>

        <div className="flex flex-col gap-3 px-5 py-5">
          <Show when="signed-out">
            <SignInButton mode="modal" forceRedirectUrl={redirectTo}>
              <Button type="button" variant="primary" size="md">
                Sign in
              </Button>
            </SignInButton>
            <SignUpButton mode="modal" forceRedirectUrl={redirectTo}>
              <Button type="button" variant="ghost" size="md">
                Create account
              </Button>
            </SignUpButton>
          </Show>
          <Show when="signed-in">
            <Button asChild variant="primary" size="md">
              <Link href={redirectTo}>Continue to workspace</Link>
            </Button>
          </Show>
        </div>
      </div>
    </main>
  );
}
