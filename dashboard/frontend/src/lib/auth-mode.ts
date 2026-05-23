import { toPlatoTenantId } from "@/lib/plato-tenant";

export const PLATO_CLERK_AUTH_PROVIDER = "clerk";

export type ClerkTenantSession = {
  userId?: string | null;
  orgId?: string | null;
};

type ClerkAuthConfiguration = {
  requested: boolean;
  enabled: boolean;
  error: string | null;
};

function secretKeyLooksValid(value: string | undefined): boolean {
  return /^sk_(test|live)_[A-Za-z0-9_-]+$/.test(value ?? "");
}

function publishableKeyLooksValid(value: string | undefined): boolean {
  if (!value || !/^pk_(test|live)_[A-Za-z0-9_-]+$/.test(value)) {
    return false;
  }

  const encoded = value.split("_")[2];
  if (!encoded) return false;

  try {
    const padded = encoded
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(encoded.length / 4) * 4, "=");
    const decoded = globalThis.atob(padded);
    return (
      decoded.endsWith("$") &&
      !decoded.slice(0, -1).includes("$") &&
      decoded.slice(0, -1).includes(".")
    );
  } catch {
    return false;
  }
}

function backendProxySecretLooksConfigured(value: string | undefined): boolean {
  return (value ?? "").trim().length >= 32;
}

export function clerkAuthConfiguration(): ClerkAuthConfiguration {
  const requested =
    process.env.PLATO_AUTH_PROVIDER === PLATO_CLERK_AUTH_PROVIDER ||
    process.env.NEXT_PUBLIC_PLATO_AUTH_PROVIDER === PLATO_CLERK_AUTH_PROVIDER;
  if (!requested) {
    return { requested: false, enabled: false, error: null };
  }

  if (!publishableKeyLooksValid(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)) {
    return {
      requested: true,
      enabled: false,
      error: "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is missing or invalid.",
    };
  }

  if (!secretKeyLooksValid(process.env.CLERK_SECRET_KEY)) {
    return {
      requested: true,
      enabled: false,
      error: "CLERK_SECRET_KEY is missing or invalid.",
    };
  }

  if (!backendProxySecretLooksConfigured(process.env.PLATO_BACKEND_PROXY_SECRET)) {
    return {
      requested: true,
      enabled: false,
      error:
        "PLATO_BACKEND_PROXY_SECRET is missing or too short. Hosted Clerk deployments must use a private backend proxy secret with at least 32 characters.",
    };
  }

  return { requested: true, enabled: true, error: null };
}

export function isClerkAuthEnabled(): boolean {
  return clerkAuthConfiguration().enabled;
}

export function isClerkProviderAvailable(): boolean {
  const requested =
    process.env.PLATO_AUTH_PROVIDER === PLATO_CLERK_AUTH_PROVIDER ||
    process.env.NEXT_PUBLIC_PLATO_AUTH_PROVIDER === PLATO_CLERK_AUTH_PROVIDER;
  return requested && publishableKeyLooksValid(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
}

export function isClerkAuthMisconfigured(): boolean {
  const config = clerkAuthConfiguration();
  return config.requested && !config.enabled;
}

export function clerkAuthConfigError(): string | null {
  return clerkAuthConfiguration().error;
}

export function isHostedBillingEnabled(): boolean {
  return (
    isClerkAuthEnabled() &&
    process.env.NEXT_PUBLIC_PLATO_HOSTED_BILLING === "enabled"
  );
}

export function isHostedBillingRequested(): boolean {
  return process.env.NEXT_PUBLIC_PLATO_HOSTED_BILLING === "enabled";
}

export function hostedBillingConfigError(): string | null {
  if (!isHostedBillingRequested() || isHostedBillingEnabled()) {
    return null;
  }
  return (
    clerkAuthConfigError() ??
    "NEXT_PUBLIC_PLATO_HOSTED_BILLING=enabled requires Clerk auth. Set PLATO_AUTH_PROVIDER=clerk and NEXT_PUBLIC_PLATO_AUTH_PROVIDER=clerk."
  );
}

export function platoTenantIdForClerkSession(
  session: ClerkTenantSession,
): string | null {
  if (!session.userId) return null;
  return session.orgId
    ? toPlatoTenantId("lab", session.orgId)
    : toPlatoTenantId("user", session.userId);
}

export function platoTenantHeadersForClerkSession(
  session: ClerkTenantSession,
): Headers | null {
  const tenantId = platoTenantIdForClerkSession(session);
  if (!tenantId) return null;

  const headers = new Headers();
  headers.set("X-Plato-User", tenantId);
  headers.set("X-Plato-Auth-Provider", "clerk");
  if (session.orgId) {
    headers.set("X-Plato-Lab-Id", session.orgId);
  }
  return headers;
}
