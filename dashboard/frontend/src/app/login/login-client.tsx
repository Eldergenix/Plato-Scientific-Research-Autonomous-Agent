"use client";

import * as React from "react";
import { useAuth } from "@/components/auth/auth-context";
import { LoginForm } from "@/components/auth/login-form";
import { UserMenu } from "@/components/auth/user-menu";

// AuthProvider is mounted once at the root in src/app/layout.tsx. A
// previous version of this file double-wrapped, which caused two
// independent /api/v1/auth/me fetches per render.
export default function LoginClient() {
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
          <LoginForm redirectTo="/" />
        </div>
      </div>
    </main>
  );
}
