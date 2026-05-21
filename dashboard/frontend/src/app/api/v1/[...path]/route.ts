import { homedir } from "node:os";
import { auth, clerkClient } from "@clerk/nextjs/server";
import {
  clerkAuthConfigError,
  isClerkAuthEnabled,
  isClerkAuthMisconfigured,
  platoTenantHeadersForClerkSession,
  platoTenantIdForClerkSession,
} from "@/lib/auth-mode";
import {
  createPublicationSlotReserver,
  isPublicationProducingRequest,
  parseEnvNumber,
} from "@/lib/hosted-trial-quota";
import { publicHost, publicProto } from "@/lib/public-origin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const API_PROXY_TARGET =
  process.env.PLATO_API_PROXY_TARGET?.trim() || "http://127.0.0.1:7878";
const BACKEND_PROXY_SECRET = process.env.PLATO_BACKEND_PROXY_SECRET?.trim() || "";
const CLERK_AUTH_ENABLED = isClerkAuthEnabled();
const CLERK_AUTH_MISCONFIGURED = isClerkAuthMisconfigured();
const USAGE_LEDGER_PATH =
  process.env.PLATO_HOSTED_USAGE_LEDGER_PATH ||
  `${homedir()}/.plato/hosted-usage/weekly-publications.json`;
const TENANT_COOKIE = "plato_user";
const TENANT_ID_RE = /^[A-Za-z0-9._-]{1,64}$/;

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

type TenantContext = {
  tenant: string | null;
  headers: Headers | null;
};

const FORWARDED_REQUEST_HEADERS = new Set([
  "accept",
  "accept-language",
  "content-type",
  "cookie",
  "x-plato-run-id",
]);

const RESPONSE_HEADER_BLOCKLIST = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "keep-alive",
  "transfer-encoding",
]);

const TRIAL_PUBLICATION_LIMIT = parseEnvNumber(
  "PLATO_HOSTED_TRIAL_PUBLICATIONS_PER_WEEK",
  2,
);

function tenantFromCookie(request: Request): string | null {
  const cookie = request.headers.get("cookie");
  if (!cookie) return null;
  for (const part of cookie.split(";")) {
    const [rawName, ...rawValue] = part.trim().split("=");
    if (rawName !== TENANT_COOKIE || rawValue.length === 0) continue;
    const value = decodeURIComponent(rawValue.join("=")).trim();
    return TENANT_ID_RE.test(value) ? value : null;
  }
  return null;
}

async function tenantContextForRequest(request: Request): Promise<TenantContext> {
  if (CLERK_AUTH_ENABLED) {
    const session = await auth();
    return {
      tenant: platoTenantIdForClerkSession(session),
      headers: platoTenantHeadersForClerkSession(session),
    };
  }
  if (CLERK_AUTH_MISCONFIGURED) {
    return { tenant: null, headers: null };
  }

  const tenant = tenantFromCookie(request);
  const headers = new Headers();
  if (tenant) {
    headers.set("X-Plato-User", tenant);
    headers.set("X-Plato-Auth-Provider", "plato-cookie");
  }
  return { tenant, headers };
}

function targetUrl(path: string[], request: Request): string {
  const incoming = new URL(request.url);
  const target = new URL(`/api/v1/${path.join("/")}`, API_PROXY_TARGET);
  target.search = incoming.search;
  return target.toString();
}

function isPublicApiRequest(path: string[], request: Request): boolean {
  if (path.length === 1 && ["health", "capabilities"].includes(path[0])) {
    return true;
  }
  if (path[0] === "auth" && path.length === 2 && path[1] === "me") {
    return true;
  }
  if (
    !CLERK_AUTH_ENABLED &&
    !CLERK_AUTH_MISCONFIGURED &&
    path[0] === "auth" &&
    path.length === 2 &&
    ["login", "logout"].includes(path[1] ?? "")
  ) {
    return true;
  }
  if (!["GET", "HEAD"].includes(request.method)) {
    return false;
  }
  return (
    (path.length === 1 && path[0] === "publications") ||
    (path.length === 2 && path[0] === "publications" && path[1] === "rss.xml") ||
    (path.length === 2 && path[0] === "publications")
  );
}

function isLocalAuthMutation(path: string[], request: Request): boolean {
  return (
    request.method === "POST" &&
    path[0] === "auth" &&
    path.length === 2 &&
    ["login", "logout"].includes(path[1] ?? "")
  );
}

async function shouldApplyTrialLimit(): Promise<boolean> {
  if (!CLERK_AUTH_ENABLED) return false;

  const session = await auth();
  if (!session.userId) return true;

  try {
    const client = await clerkClient();
    const subscription = session.orgId
      ? await client.billing.getOrganizationBillingSubscription(session.orgId)
      : await client.billing.getUserBillingSubscription(session.userId);

    if (subscription.status !== "active") return true;
    if (subscription.subscriptionItems.length === 0) return true;

    return subscription.subscriptionItems.some((item) => {
      const slug = item.plan?.slug ?? "";
      return item.isFreeTrial || slug.includes("free");
    });
  } catch {
    return true;
  }
}

const reservePublicationSlot = createPublicationSlotReserver({
  ledgerPath: USAGE_LEDGER_PATH,
  limit: TRIAL_PUBLICATION_LIMIT,
  shouldApplyLimit: shouldApplyTrialLimit,
});

function forwardedHeaders(request: Request, tenantHeaders: Headers | null): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (
      FORWARDED_REQUEST_HEADERS.has(lowerKey) &&
      (lowerKey !== "cookie" || (!CLERK_AUTH_ENABLED && !CLERK_AUTH_MISCONFIGURED))
    ) {
      headers.set(key, value);
    }
  });
  tenantHeaders?.forEach((value, key) => headers.set(key, value));
  headers.set(
    "x-forwarded-host",
    publicHost({ headers: request.headers, url: request.url }),
  );
  headers.set(
    "x-forwarded-proto",
    publicProto({ headers: request.headers, url: request.url }),
  );
  if (BACKEND_PROXY_SECRET) {
    headers.set("X-Plato-Proxy-Secret", BACKEND_PROXY_SECRET);
  }
  return headers;
}

function responseHeaders(response: Response): Headers {
  const headers = new Headers();
  response.headers.forEach((value, key) => {
    if (!RESPONSE_HEADER_BLOCKLIST.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  return headers;
}

async function proxyRequest(request: Request, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params;
  const localAuthMutation = isLocalAuthMutation(path, request);
  if (CLERK_AUTH_ENABLED && localAuthMutation) {
    return Response.json(
      {
        code: "local_auth_disabled",
        message: "Local Plato login is disabled when hosted Clerk auth is enabled.",
      },
      { status: 404 },
    );
  }

  const tenantContext = await tenantContextForRequest(request);
  const tenant = tenantContext.tenant;
  const publicationProducingRequest = isPublicationProducingRequest(path, request);
  const publicApiRequest = isPublicApiRequest(path, request);

  if (CLERK_AUTH_MISCONFIGURED && !publicApiRequest) {
    return Response.json(
      {
        code: "clerk_auth_misconfigured",
        message: "Hosted Clerk auth is requested but Clerk keys are missing or invalid.",
        detail: clerkAuthConfigError(),
      },
      { status: 503 },
    );
  }

  if (CLERK_AUTH_ENABLED && !tenant && !publicApiRequest) {
    return Response.json(
      { code: "auth_required", message: "Sign in with Clerk before accessing Plato." },
      { status: 401 },
    );
  }

  const publicationReservation = publicationProducingRequest && tenant
    ? await reservePublicationSlot(tenant)
    : null;
  if (publicationReservation?.limited) return publicationReservation.limited;

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(targetUrl(path, request), {
      method: request.method,
      headers: forwardedHeaders(request, tenantContext.headers),
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
    });
  } catch (error) {
    await publicationReservation?.rollback();
    return Response.json(
      {
        code: "backend_unavailable",
        message: "Plato backend is offline. Start it with `plato dashboard`.",
        detail: error instanceof Error ? error.message : "Failed to reach backend",
      },
      { status: 503 },
    );
  }
  if (publicationReservation && !upstream.ok) {
    await publicationReservation.rollback();
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders(upstream),
  });
}

export function GET(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}

export function HEAD(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}

export function POST(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}

export function PUT(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}

export function PATCH(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}

export function DELETE(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}
