"use client";

import { Show, SignInButton, UserProfile } from "@clerk/nextjs";
import { LogIn, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { isClerkAuthEnabled } from "@/lib/auth-mode";

export default function AccountSettingsPage() {
  if (!isClerkAuthEnabled()) {
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

function SelfHostedAccountFallback() {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <SettingsHeader
          title="Account"
          subtitle="Self-hosted Plato is using tenant-id auth, not hosted Clerk account management."
        />
        <section className="surface-linear-card p-5" data-testid="account-settings-fallback">
          <div className="flex items-start gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-[8px] bg-(--color-brand-indigo)/10 text-(--color-brand-hover)">
              <ShieldCheck size={16} strokeWidth={1.75} />
            </div>
            <div>
              <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
                Hosted account controls are disabled
              </h2>
              <p className="mt-1 text-[12px] text-(--color-text-tertiary-spec)">
                Password changes, email changes, identity verification, and account privacy
                controls are provided by Clerk when{" "}
                <code className="font-mono text-[11px]">
                  NEXT_PUBLIC_PLATO_AUTH_PROVIDER=clerk
                </code>{" "}
                is enabled. In self-hosted mode, Plato only receives a tenant identity
                from the configured auth proxy or local login cookie.
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
