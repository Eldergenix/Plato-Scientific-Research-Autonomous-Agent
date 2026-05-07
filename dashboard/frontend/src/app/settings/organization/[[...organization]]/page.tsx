"use client";

import {
  OrganizationProfile,
  OrganizationSwitcher,
  Show,
  SignInButton,
} from "@clerk/nextjs";
import { Building2, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { isClerkAuthEnabled } from "@/lib/auth-mode";

export default function OrganizationSettingsPage() {
  if (!isClerkAuthEnabled()) {
    return <SelfHostedOrganizationFallback />;
  }

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <SettingsHeader
          title="Organization"
          subtitle="Manage Clerk Labs, organization profile, members, invitations, and roles."
        />
        <Show when="signed-out">
          <section className="surface-linear-card p-5">
            <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
              Sign in required
            </h2>
            <p className="mt-1 text-[12px] text-(--color-text-tertiary-spec)">
              Sign in to manage Plato organization settings.
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
          <section className="surface-linear-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
                  Active Lab
                </h2>
                <p className="mt-1 text-[12px] text-(--color-text-tertiary-spec)">
                  Select or create the Clerk organization that should own new Plato work.
                </p>
              </div>
              <OrganizationSwitcher
                createOrganizationMode="modal"
                organizationProfileMode="navigation"
                organizationProfileUrl="/settings/organization"
                skipInvitationScreen={false}
              />
            </div>
          </section>
          <section className="surface-linear-card overflow-hidden p-2">
            <OrganizationProfile path="/settings/organization" routing="path" />
          </section>
        </Show>
      </div>
    </div>
  );
}

function SelfHostedOrganizationFallback() {
  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <SettingsHeader
          title="Organization"
          subtitle="Self-hosted Plato scopes workspaces by the tenant identity forwarded to the backend."
        />
        <section className="surface-linear-card p-5" data-testid="organization-settings-fallback">
          <div className="flex items-start gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-[8px] bg-(--color-brand-indigo)/10 text-(--color-brand-hover)">
              <Building2 size={16} strokeWidth={1.75} />
            </div>
            <div>
              <h2 className="text-[15px] font-[510] text-(--color-text-primary-strong)">
                Hosted organization controls are disabled
              </h2>
              <p className="mt-1 text-[12px] text-(--color-text-tertiary-spec)">
                Clerk Organizations become Plato Labs when{" "}
                <code className="font-mono text-[11px]">
                  NEXT_PUBLIC_PLATO_AUTH_PROVIDER=clerk
                </code>{" "}
                is enabled. In self-hosted mode, organization membership, invitations,
                and verification policy must be managed by the upstream identity provider
                that sets <code className="font-mono text-[11px]">X-Plato-User</code>.
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
