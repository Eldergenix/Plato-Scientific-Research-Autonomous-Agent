import "server-only";

import { auth, clerkClient } from "@clerk/nextjs/server";
import { platoTenantIdForClerkSession } from "@/lib/auth-mode";

type KeyState = "unset" | "from_env" | "in_app";

type KeysStatus = {
  OPENAI: KeyState;
  GEMINI: KeyState;
  ANTHROPIC: KeyState;
  PERPLEXITY: KeyState;
  SEMANTIC_SCHOLAR: KeyState;
  LANGFUSE_PUBLIC: KeyState;
  LANGFUSE_SECRET: KeyState;
  LANGFUSE_HOST: KeyState;
};

type BackendProject = {
  total_tokens?: number;
  total_cost_cents?: number;
};

type BillingDiagnostic = {
  source: "keys" | "projects";
  status: number | null;
  message: string;
};

type BillingSummary = {
  scope: "user" | "lab";
  scopeLabel: string;
  tenantId: string;
  providerMode: "hosted" | "byok" | "unknown";
  projectsCount: number;
  totalCostCents: number;
  totalTokens: number;
  trialPublicationLimit: number;
  diagnostics: BillingDiagnostic[];
  subscription: null | {
    status: string;
    planName: string | null;
    planSlug: string | null;
    planPeriod: string | null;
    isFreeTrial: boolean;
    eligibleForFreeTrial: boolean;
    nextPaymentCents: number | null;
    nextPaymentDate: string | null;
  };
  organization: null | {
    id: string;
    name: string;
    membersCount: number | null;
    maxAllowedMemberships: number | null;
  };
  implementation: {
    clerkManagesPlans: true;
    clerkSupportsSeatLimits: true;
    clerkSupportsPerSeatUnitPricing: false;
    clerkSupportsNativeUsageMetering: false;
  };
  contract: {
    userProFeeCents: number;
    userResearcherFeeCents: number;
    labBaseFeeCents: number;
    labSeatFeeCents: number;
    estimatedSeatChargeCents: number;
  };
};

const API_PROXY_TARGET =
  process.env.PLATO_API_PROXY_TARGET?.trim() || "http://127.0.0.1:7878";
const BACKEND_PROXY_SECRET = process.env.PLATO_BACKEND_PROXY_SECRET?.trim() || "";
const BYOK_PROVIDERS: Array<keyof KeysStatus> = ["OPENAI", "GEMINI", "ANTHROPIC"];

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
const USER_PRO_FEE_CENTS = parseEnvNumber("PLATO_HOSTED_USER_PRO_FEE_CENTS", 1499);
const USER_RESEARCHER_FEE_CENTS = parseEnvNumber(
  "PLATO_HOSTED_USER_RESEARCHER_FEE_CENTS",
  9999,
);
const LAB_BASE_FEE_CENTS = parseEnvNumber("PLATO_HOSTED_LAB_BASE_FEE_CENTS", 9900);
const LAB_SEAT_FEE_CENTS = parseEnvNumber("PLATO_HOSTED_LAB_SEAT_FEE_CENTS", 0);
const DIAGNOSTIC_MESSAGE_MAX = 180;

function sanitizedDiagnosticMessage(body: string): string {
  const trimmed = body.trim();
  if (!trimmed) return "Upstream request failed";

  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (typeof parsed === "object" && parsed != null) {
      const detail = (parsed as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) {
        return detail.trim().slice(0, DIAGNOSTIC_MESSAGE_MAX);
      }
      if (typeof detail === "object" && detail != null) {
        const code = (detail as { code?: unknown }).code;
        const message = (detail as { message?: unknown }).message;
        const parts = [code, message].filter((item): item is string =>
          typeof item === "string" && item.trim().length > 0,
        );
        if (parts.length > 0) {
          return parts.join(": ").slice(0, DIAGNOSTIC_MESSAGE_MAX);
        }
      }
    }
  } catch {
    // Fall through to the generic response below.
  }

  return "Upstream request failed";
}

async function fetchTenantJson<T>(
  tenantId: string,
  path: string,
  source: BillingDiagnostic["source"],
): Promise<{ data: T | null; diagnostic: BillingDiagnostic | null }> {
  let response: Response;
  try {
    const headers: Record<string, string> = {
      "X-Plato-User": tenantId,
      "X-Plato-Auth-Provider": "clerk",
    };
    if (BACKEND_PROXY_SECRET) {
      headers["X-Plato-Proxy-Secret"] = BACKEND_PROXY_SECRET;
    }

    response = await fetch(new URL(path, API_PROXY_TARGET), {
      headers,
      cache: "no-store",
    });
  } catch (error) {
    return {
      data: null,
      diagnostic: {
        source,
        status: null,
        message: error instanceof Error ? error.message : "Backend request failed",
      },
    };
  }

  if (!response.ok) {
    return {
      data: null,
      diagnostic: {
        source,
        status: response.status,
        message: sanitizedDiagnosticMessage(await response.text()),
      },
    };
  }

  return { data: (await response.json()) as T, diagnostic: null };
}

function sumProjects(projects: BackendProject[]) {
  return projects.reduce(
    (totals, project) => ({
      totalCostCents: totals.totalCostCents + (project.total_cost_cents ?? 0),
      totalTokens: totals.totalTokens + (project.total_tokens ?? 0),
    }),
    { totalCostCents: 0, totalTokens: 0 },
  );
}

function hasByokKeys(status: KeysStatus | null): boolean {
  if (!status) return false;
  return BYOK_PROVIDERS.some((provider) => status[provider] === "in_app");
}

export async function getHostedBillingSummary(): Promise<BillingSummary | null> {
  const session = await auth();
  if (!session.userId) return null;

  const client = await clerkClient();
  const scope = session.orgId ? "lab" : "user";
  const tenantId = platoTenantIdForClerkSession(session);
  if (!tenantId) return null;

  const [keysResult, projectsResult] = await Promise.all([
    fetchTenantJson<KeysStatus>(tenantId, "/api/v1/keys/status", "keys"),
    fetchTenantJson<BackendProject[]>(tenantId, "/api/v1/projects", "projects"),
  ]);
  const keysStatus = keysResult.data;
  const projects = projectsResult.data;
  const diagnostics = [keysResult.diagnostic, projectsResult.diagnostic].filter(
    (item): item is BillingDiagnostic => item != null,
  );

  const providerMode = keysStatus == null
    ? "unknown"
    : hasByokKeys(keysStatus)
      ? "byok"
      : "hosted";
  const totals = sumProjects(projects ?? []);

  let organization: BillingSummary["organization"] = null;
  let membersCount = 0;
  if (session.orgId) {
    const [org, memberships] = await Promise.all([
      client.organizations
        .getOrganization({ organizationId: session.orgId })
        .catch(() => null),
      client.organizations
        .getOrganizationMembershipList({ organizationId: session.orgId })
        .catch(() => null),
    ]);
    if (org && memberships) {
      membersCount = memberships.totalCount;
      organization = {
        id: org.id,
        name: org.name,
        membersCount: memberships.totalCount,
        maxAllowedMemberships: org.maxAllowedMemberships ?? null,
      };
    }
  }

  const subscription = session.orgId
    ? await client.billing.getOrganizationBillingSubscription(session.orgId).catch(() => null)
    : await client.billing.getUserBillingSubscription(session.userId).catch(() => null);

  const primaryItem = subscription?.subscriptionItems[0] ?? null;

  return {
    scope,
    scopeLabel: organization?.name ?? (scope === "lab" ? "Active Lab" : "Personal workspace"),
    tenantId,
    providerMode,
    projectsCount: projects?.length ?? 0,
    totalCostCents: totals.totalCostCents,
    totalTokens: totals.totalTokens,
    trialPublicationLimit: TRIAL_PUBLICATION_LIMIT,
    diagnostics,
    subscription: subscription
      ? {
          status: subscription.status,
          planName: primaryItem?.plan?.name ?? null,
          planSlug: primaryItem?.plan?.slug ?? null,
          planPeriod: primaryItem?.planPeriod ?? null,
          isFreeTrial: primaryItem?.isFreeTrial ?? false,
          eligibleForFreeTrial: subscription.eligibleForFreeTrial ?? false,
          nextPaymentCents: subscription.nextPayment?.amount?.amount ?? null,
          nextPaymentDate:
            subscription.nextPayment?.date != null
              ? new Date(subscription.nextPayment.date).toISOString()
              : null,
        }
      : null,
    organization,
    implementation: {
      clerkManagesPlans: true,
      clerkSupportsSeatLimits: true,
      clerkSupportsPerSeatUnitPricing: false,
      clerkSupportsNativeUsageMetering: false,
    },
    contract: {
      userProFeeCents: USER_PRO_FEE_CENTS,
      userResearcherFeeCents: USER_RESEARCHER_FEE_CENTS,
      labBaseFeeCents: LAB_BASE_FEE_CENTS,
      labSeatFeeCents: LAB_SEAT_FEE_CENTS,
      estimatedSeatChargeCents: scope === "lab" ? membersCount * LAB_SEAT_FEE_CENTS : 0,
    },
  };
}
