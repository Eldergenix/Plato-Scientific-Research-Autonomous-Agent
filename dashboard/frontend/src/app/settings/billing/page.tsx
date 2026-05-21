import {
  OrganizationSwitcher,
  PricingTable,
  Show,
  SignInButton,
  SignUpButton,
  UserButton,
} from "@clerk/nextjs";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import {
  clerkAuthConfigError,
  hostedBillingConfigError,
  isClerkAuthMisconfigured,
  isHostedBillingEnabled,
  isHostedBillingRequested,
} from "@/lib/auth-mode";
import { getHostedBillingSummary } from "@/lib/hosted-billing.server";

export const dynamic = "force-dynamic";

function parseEnvNumber(name: string, fallback: number): number {
  const raw = process.env[name]?.trim();
  if (!raw) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

const TRIAL_PUBLICATION_LIMIT = parseEnvNumber(
  "PLATO_HOSTED_TRIAL_PUBLICATIONS_PER_WEEK",
  2,
);
const TRIAL_PUBLICATION_LABEL = `${TRIAL_PUBLICATION_LIMIT} ${
  TRIAL_PUBLICATION_LIMIT === 1 ? "paper" : "papers"
} / week`;

const USER_PLANS = [
  {
    name: "Free BYOK",
    price: "$0",
    description: "Personal scientific workspace with your own provider keys.",
    details: ["Bring your own keys", TRIAL_PUBLICATION_LABEL, "No usage billing"],
  },
  {
    name: "Pro",
    price: "$14.99/mo",
    description: "Individual researcher plan with included hosted usage.",
    details: ["1 month free", "Usage limits + overages", "Strict trial cap"],
  },
  {
    name: "Researcher",
    price: "$99.99/mo",
    description: "Higher-limit individual plan for active publication work.",
    details: ["1 month free", "Higher hosted usage", "Usage overages"],
  },
];

const LAB_PLANS = [
  {
    name: "Lab Standard",
    price: "$99/mo",
    description: "Shared Lab workspace for members, colleagues, and outside collaborators.",
    details: ["Organization billing", "20 scientist limit", "Hosted usage policy"],
  },
  {
    name: "Lab BYOK",
    price: "$99/mo",
    description: "Shared Lab membership and collaboration without hosted usage billing.",
    details: ["Bring lab-owned keys", "No usage billing", "Flat Lab fee"],
  },
];

export default async function BillingSettingsPage() {
  const hostedBilling = isHostedBillingEnabled();
  const hostedBillingRequested = isHostedBillingRequested();
  const clerkAuthMisconfigured = isClerkAuthMisconfigured();
  const billingConfigError = clerkAuthMisconfigured
    ? clerkAuthConfigError()
    : hostedBillingConfigError();
  let billingSummary = null;
  let billingError: string | null = null;
  if (hostedBilling) {
    try {
      billingSummary = await getHostedBillingSummary();
    } catch (error) {
      billingError =
        error instanceof Error ? error.message : "Hosted billing summary failed to load";
    }
  }
  const billingWarnings = [
    ...(billingSummary?.diagnostics ?? []).map((item) =>
      item.status == null
        ? `${item.source}: ${item.message}`
        : `${item.source}: API ${item.status} ${item.message}`,
    ),
    ...(billingError ? [billingError] : []),
  ];
  const trialPublicationLabel = billingSummary
    ? `${billingSummary.trialPublicationLimit} ${
        billingSummary.trialPublicationLimit === 1 ? "paper" : "papers"
      } / week`
    : TRIAL_PUBLICATION_LABEL;

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="surface-linear-card p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="mb-2 flex items-center gap-2">
                <Pill tone={hostedBilling ? "green" : billingConfigError ? "amber" : "neutral"}>
                  {hostedBilling
                    ? "hosted"
                    : billingConfigError
                      ? "hosted config error"
                      : "self-hosted"}
                </Pill>
                <Pill tone="neutral">Labs</Pill>
                {billingSummary ? (
                  <Pill tone={billingSummary.scope === "lab" ? "indigo" : "amber"}>
                    {billingSummary.scope === "lab" ? "active lab" : "personal"}
                  </Pill>
                ) : null}
                {billingSummary ? (
                  <Pill tone={billingSummary.providerMode === "byok" ? "indigo" : "green"}>
                    {billingSummary.providerMode === "unknown"
                      ? "usage unknown"
                      : billingSummary.providerMode === "byok"
                        ? "byok"
                        : "hosted usage"}
                  </Pill>
                ) : null}
                {billingWarnings.length > 0 ? (
                  <Pill tone="amber">billing warning</Pill>
                ) : null}
              </div>
              <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
                Labs & billing
              </h1>
              <p className="mt-1 max-w-2xl text-[13px] leading-[1.55] text-(--color-text-tertiary-spec)">
                Clerk Organizations are presented as Labs in Plato. Scientists can
                work individually, switch into a Lab, or invite collaborators from
                other laboratories.
              </p>
            </div>
            {hostedBilling ? (
              <div className="flex items-center gap-2">
                <Show when="signed-out">
                  <SignInButton mode="modal">
                    <Button type="button" variant="ghost" size="md">
                      Sign in
                    </Button>
                  </SignInButton>
                  <SignUpButton mode="modal">
                    <Button type="button" variant="primary" size="md">
                      Start trial
                    </Button>
                  </SignUpButton>
                </Show>
                <Show when="signed-in">
                  <OrganizationSwitcher
                    createOrganizationMode="modal"
                    organizationProfileMode="modal"
                    skipInvitationScreen={false}
                  />
                  <UserButton />
                </Show>
              </div>
            ) : null}
          </div>
        </header>

        <section className="surface-linear-card p-5">
          <SectionTitle
            title="Billing contract"
            subtitle="The trial publication cap is enforced in the hosted API proxy before the Paper stage can start."
          />
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
            <Metric label="Trial" value="1 month free" />
            <Metric label="Strict cap" value={trialPublicationLabel} />
            <Metric label="Tenant scope" value="User or active Lab" />
          </div>
        </section>

        {billingConfigError ? (
          <section
            className="surface-linear-card border-(--color-status-amber)/40 bg-(--color-status-amber)/10 p-5"
            data-testid="billing-auth-config-error"
          >
            <SectionTitle
              title="Hosted billing is misconfigured"
              subtitle="Hosted billing, sign-in, and Lab subscription controls are unavailable until Clerk auth and billing are configured together."
            />
            <p className="mt-3 font-mono text-[11px] text-(--color-text-tertiary-spec)">
              {billingConfigError}
            </p>
          </section>
        ) : null}

        {billingWarnings.length > 0 ? (
          <section
            className="surface-linear-card border-(--color-status-amber)/40 bg-(--color-status-amber)/10 p-5"
            data-testid="hosted-billing-warning"
          >
            <SectionTitle
              title="Billing data needs attention"
              subtitle="The page is still usable, but production billing totals may be incomplete until these upstream reads recover."
            />
            <ul className="mt-3 space-y-1 text-[12px] text-(--color-text-primary)">
              {billingWarnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {billingSummary ? (
          <section className="surface-linear-card p-5" data-testid="hosted-billing-summary">
            <SectionTitle
              title="Current scope"
              subtitle="Clerk manages the active subscription and Lab context. Plato computes the contract details that Clerk Billing does not expose natively."
            />
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <Metric label="Workspace" value={billingSummary.scopeLabel} />
              <Metric
                label="Current plan"
                value={billingSummary.subscription?.planName ?? "Free / unsubscribed"}
              />
              <Metric
                label="Tracked spend"
                value={formatUsd(billingSummary.totalCostCents)}
              />
              <Metric
                label="Projects"
                value={String(billingSummary.projectsCount)}
              />
              <Metric
                label="Plan status"
                value={billingSummary.subscription?.status ?? "inactive"}
              />
              <Metric
                label="Next payment"
                value={
                  billingSummary.subscription?.nextPaymentCents != null
                    ? formatUsd(billingSummary.subscription.nextPaymentCents)
                    : "n/a"
                }
              />
              <Metric
                label="Token usage"
                value={formatTokens(billingSummary.totalTokens)}
              />
              <Metric
                label="Trial guard"
                value={trialPublicationLabel}
              />
            </div>
            {billingSummary.organization ? (
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
                <Metric
                  label="Lab members"
                  value={String(billingSummary.organization.membersCount ?? 0)}
                />
                <Metric
                  label="Seat estimate"
                  value={formatUsd(billingSummary.contract.estimatedSeatChargeCents)}
                />
                <Metric
                  label="Lab base fee"
                  value={formatUsd(billingSummary.contract.labBaseFeeCents)}
                />
              </div>
            ) : null}
          </section>
        ) : null}

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <PlanGroup title="Scientists" plans={USER_PLANS} />
          <PlanGroup title="Labs" plans={LAB_PLANS} />
        </section>

        {hostedBilling ? (
          <>
            <section className="surface-linear-card p-5" data-testid="billing-implementation-notes">
              <SectionTitle
                title="Implementation notes"
                subtitle="The hosted branch is wired so the product stays honest about what Clerk Billing currently provides and what Plato computes itself."
              />
              <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                <article className="rounded-[10px] border border-(--color-border-card) bg-(--color-bg-card) p-4">
                  <h3 className="text-[14px] font-[510] text-(--color-text-primary-strong)">
                    Clerk-managed
                  </h3>
                  <ul className="mt-3 flex flex-wrap gap-1.5">
                    <li><Pill tone="green">Sign-in and sign-up</Pill></li>
                    <li><Pill tone="green">Labs / Organizations</Pill></li>
                    <li><Pill tone="green">Subscription status</Pill></li>
                    <li><Pill tone="green">PricingTable UI</Pill></li>
                    <li><Pill tone="green">Seat limits</Pill></li>
                  </ul>
                </article>
                <article className="rounded-[10px] border border-(--color-border-card) bg-(--color-bg-card) p-4">
                  <h3 className="text-[14px] font-[510] text-(--color-text-primary-strong)">
                    Plato-managed
                  </h3>
                  <ul className="mt-3 flex flex-wrap gap-1.5">
                    <li><Pill tone="amber">Seat usage estimate</Pill></li>
                    <li><Pill tone="amber">BYOK detection</Pill></li>
                    <li><Pill tone="amber">Trial publication cap</Pill></li>
                    <li><Pill tone="amber">Hosted usage accounting</Pill></li>
                    <li><Pill tone="amber">Usage overage policy</Pill></li>
                  </ul>
                </article>
              </div>
              <p className="mt-3 text-[13px] leading-[1.55] text-(--color-text-tertiary-spec)">
                Current Clerk docs and dashboard flows expose recurring plan fees,
                free trials, feature gates, and seat limits. They do not document
                native per-seat unit pricing or usage-meter overage charging, so
                this branch keeps those parts in Plato&apos;s own contract layer.
              </p>
            </section>

            <section className="surface-linear-card p-5" data-testid="user-pricing-table">
              <SectionTitle
                title="User plans"
                subtitle="Rendered from Clerk Billing for the signed-in scientist."
              />
              <div className="mt-4">
                <PricingTable
                  for="user"
                  collapseFeatures
                  newSubscriptionRedirectUrl="/settings/billing"
                />
              </div>
            </section>

            <section className="surface-linear-card p-5" data-testid="lab-pricing-table">
              <SectionTitle
                title="Lab plans"
                subtitle="Rendered from Clerk Billing for the active Lab."
              />
              <div className="mt-4">
                <PricingTable
                  for="organization"
                  collapseFeatures
                  newSubscriptionRedirectUrl="/settings/billing"
                />
              </div>
            </section>
          </>
        ) : hostedBillingRequested || clerkAuthMisconfigured ? null : (
          <section className="surface-linear-card p-5">
            <SectionTitle
              title="Hosted billing disabled"
              subtitle="Self-hosted deployments keep local/auth-proxy mode by default."
            />
            <p className="mt-3 text-[13px] leading-[1.55] text-(--color-text-tertiary-spec)">
              Set <code className="font-mono">NEXT_PUBLIC_PLATO_AUTH_PROVIDER=clerk</code>{" "}
              and Clerk keys to enable hosted authentication, Labs, and Clerk Billing.
            </p>
          </section>
        )}

        <footer className="flex items-center justify-between gap-3 text-[12px] text-(--color-text-tertiary)">
          <Link href="/settings" className="hover:text-(--color-text-primary)">
            Back to settings
          </Link>
          <a
            href="https://dashboard.clerk.com/"
            className="hover:text-(--color-text-primary)"
            target="_blank"
            rel="noreferrer"
          >
            Clerk Dashboard
          </a>
        </footer>
      </div>
    </div>
  );
}

function PlanGroup({
  title,
  plans,
}: {
  title: string;
  plans: Array<{ name: string; price: string; description: string; details: string[] }>;
}) {
  return (
    <section className="surface-linear-card p-5">
      <SectionTitle title={title} />
      <div className="mt-3 grid grid-cols-1 gap-3">
        {plans.map((plan) => (
          <article
            key={plan.name}
            className="rounded-[10px] border border-(--color-border-card) bg-(--color-bg-card) p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-[14px] font-[510] text-(--color-text-primary-strong)">
                  {plan.name}
                </h3>
                <p className="mt-1 text-[12px] leading-[1.5] text-(--color-text-tertiary-spec)">
                  {plan.description}
                </p>
              </div>
              <div className="shrink-0 text-right text-[13px] font-[510] text-(--color-text-primary)">
                {plan.price}
              </div>
            </div>
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {plan.details.map((detail) => (
                <li key={detail}>
                  <Pill tone="neutral">{detail}</Pill>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[10px] border border-(--color-border-card) bg-(--color-bg-card) px-3 py-2.5">
      <div className="text-[11px] text-(--color-text-tertiary-spec)">{label}</div>
      <div className="mt-1 text-[13px] font-[510] text-(--color-text-primary)">
        {value}
      </div>
    </div>
  );
}

function formatUsd(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div>
      <h2 className="text-[15px] font-[510] tracking-[-0.2px] text-(--color-text-primary-strong)">
        {title}
      </h2>
      {subtitle ? (
        <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
          {subtitle}
        </p>
      ) : null}
    </div>
  );
}
