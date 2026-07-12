"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Show,
  SignInButton,
  SignUpButton,
  UserButton,
  useAuth as useClerkAuth,
} from "@clerk/nextjs";
import { AlertTriangle } from "lucide-react";
import { useAuth as useTenantAuth } from "@/components/auth/auth-context";
import { useAuthMode } from "@/components/auth/auth-mode-provider";
import { LoginForm } from "@/components/auth/login-form";
import { UserMenu } from "@/components/auth/user-menu";
import { Button } from "@/components/ui/button";

export function LoginPageClient({ redirectTo }: { redirectTo: string }) {
  const { clerkAuthEnabled, clerkAuthMisconfigured, clerkAuthError } = useAuthMode();

  if (clerkAuthMisconfigured) {
    return <ClerkAuthConfigurationError detail={clerkAuthError} />;
  }

  if (clerkAuthEnabled) {
    return <ClerkLoginPage redirectTo={redirectTo} />;
  }

  return <TenantLoginPage redirectTo={redirectTo} />;
}

function ClerkAuthConfigurationError({ detail }: { detail: string | null }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-(--color-bg-page) p-6">
      <div
        className="surface-linear-card w-full max-w-[420px] overflow-hidden"
        data-testid="login-auth-config-error"
      >
        <header className="flex items-start gap-3 border-b border-[#1D1D1F] px-5 py-4">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-[8px] bg-red-500/10 text-red-600">
            <AlertTriangle size={16} strokeWidth={1.75} />
          </div>
          <div>
            <h1 className="text-[16px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
              Clerk auth is misconfigured
            </h1>
            <p className="mt-1 text-[12px] leading-[1.5] text-(--color-text-tertiary-spec)">
              Hosted sign-in was requested, but Clerk keys are missing or invalid.
            </p>
          </div>
        </header>
        {detail ? (
          <div className="px-5 py-5">
            <p className="font-mono text-[11px] text-(--color-text-tertiary-spec)">
              {detail}
            </p>
          </div>
        ) : null}
      </div>
    </main>
  );
}

function TenantLoginPage({ redirectTo }: { redirectTo: string }) {
  const { user_id } = useTenantAuth();
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
  const router = useRouter();
  const { isLoaded, isSignedIn } = useClerkAuth();
  const signedIn = isLoaded && isSignedIn;

  React.useEffect(() => {
    if (signedIn) {
      router.replace(redirectTo);
    }
  }, [redirectTo, router, signedIn]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-(--color-bg-page) p-6">
      <div
        className="surface-linear-card w-full max-w-[420px] overflow-hidden"
        data-testid="login-card"
      >
        <header className="flex items-start justify-between gap-3 border-b border-[#1D1D1F] px-5 py-4">
          <div>
            <h1 className="text-[16px] font-medium tracking-[-0.01em] text-(--color-text-primary-strong)">
              {signedIn ? "Opening Plato" : "Sign in to Plato"}
            </h1>
            <p className="mt-1 text-[12px] leading-[1.5] text-(--color-text-tertiary-spec)">
              {signedIn
                ? "Your Clerk session is active. Redirecting to your workspace."
                : "Use your Clerk account, then choose a personal workspace or Lab."}
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
              <Link href={redirectTo} prefetch={false}>
                Continue to workspace
              </Link>
            </Button>
          </Show>
        </div>
      </div>
    </main>
  );
}
