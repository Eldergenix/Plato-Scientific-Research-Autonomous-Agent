"use client";

import { Show, SignInButton, UserProfile } from "@clerk/nextjs";
import { AlertTriangle, LogIn, ShieldCheck } from "lucide-react";
import { useAuthMode } from "@/components/auth/auth-mode-provider";
import { Button } from "@/components/ui/button";

export default function AccountSettingsPage() {
  const { clerkAuthEnabled, clerkAuthMisconfigured, clerkAuthError } = useAuthMode();

  if (clerkAuthMisconfigured) {
    return (
      <AuthConfigurationError
        title="Account"
        detail={clerkAuthError}
        summary="Hosted account settings are unavailable because Clerk auth was requested but is not configured correctly."
      />
    );
  }

  if (!clerkAuthEnabled) {
    return <SelfHostedAccountFallback />;
  }

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <SettingsHeader
          title="Account"
          subtitle="Profile, email, password, verification, security, and privacy controls are managed by Clerk."
        />
        <Show when="signed-out">
          <section className="surface-linear-card p-5">
            <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
              Sign in required
            </h2>
            <p className="mt-1 text-[12px] text-(--color-text-tertiary-spec)">
              Sign in to manage your Plato account settings.
            </p>
            <SignInButton mode="modal">
              <Button className="mt-4" size="md">
                <LogIn size={13} strokeWidth={1.75} />
                Sign in
              </Button>
            </SignInButton>
          </section>
        </Show>
        <Show when="signed-in">
          <section className="surface-linear-card overflow-hidden p-2">
            <UserProfile path="/settings/account" routing="path" />
          </section>
        </Show>
      </div>
    </div>
  );
}

function AuthConfigurationError({
  title,
  summary,
  detail,
}: {
  title: string;
  summary: string;
  detail: string | null;
}) {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <SettingsHeader
          title={title}
          subtitle="Hosted Clerk authentication needs attention before this page can be used."
        />
        <section className="surface-linear-card p-5" data-testid="account-auth-config-error">
          <div className="flex items-start gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-[8px] bg-red-500/10 text-red-600">
              <AlertTriangle size={16} strokeWidth={1.75} />
            </div>
            <div>
              <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
                Clerk auth is misconfigured
              </h2>
              <p className="mt-1 text-[12px] text-(--color-text-tertiary-spec)">
                {summary}
              </p>
              {detail ? (
                <p className="mt-3 font-mono text-[11px] text-(--color-text-tertiary-spec)">
                  {detail}
                </p>
              ) : null}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function SelfHostedAccountFallback() {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <SettingsHeader
          title="Account"
          subtitle="This deployment uses local Plato sign-in for workspace access."
        />
        <section className="surface-linear-card p-5" data-testid="account-settings-fallback">
          <div className="flex items-start gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-[8px] bg-(--color-brand-indigo)/10 text-(--color-brand-hover)">
              <ShieldCheck size={16} strokeWidth={1.75} />
            </div>
            <div>
              <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
                Local sign-in is active
              </h2>
              <p className="mt-1 text-[12px] text-(--color-text-tertiary-spec)">
                Your User ID scopes projects, settings, and workspace data in this
                dashboard. Passwords, email changes, and privacy controls are managed
                outside Plato by the configured identity provider.
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function SettingsHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="surface-linear-card p-5">
      <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
        {title}
      </h1>
      <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">{subtitle}</p>
    </header>
  );
}
