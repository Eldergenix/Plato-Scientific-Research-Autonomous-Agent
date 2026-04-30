"use client";

import * as React from "react";
import { AuthProvider, useAuth } from "@/components/auth/auth-context";
import { LoginForm } from "@/components/auth/login-form";
import { UserMenu } from "@/components/auth/user-menu";

function LoginPageBody() {
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
          {/* Show the user menu when already signed in — useful for sign-out
              while we wait for the topbar wiring to land in the integration
              commit. */}
          {user_id ? <UserMenu /> : null}
        </header>

        <div className="px-5 py-5">
          <LoginForm redirectTo="/" />
        </div>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    // The layout's AuthProvider lands in the integration commit; wrap
    // here too so this page works standalone today. Nesting providers
    // is a no-op once the outer one is in place — useAuth() will pick
    // up whichever is closest.
    <AuthProvider>
      <LoginPageBody />
    </AuthProvider>
  );
}
