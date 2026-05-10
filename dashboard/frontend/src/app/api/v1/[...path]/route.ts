import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { homedir } from "node:os";
import { auth, clerkClient } from "@clerk/nextjs/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const API_PROXY_TARGET =
  process.env.PLATO_API_PROXY_TARGET?.trim() || "http://127.0.0.1:7878";
const CLERK_AUTH_ENABLED =
  (process.env.PLATO_AUTH_PROVIDER === "clerk" ||
    process.env.NEXT_PUBLIC_PLATO_AUTH_PROVIDER === "clerk") &&
  Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
const TRIAL_PUBLICATION_LIMIT = Number(
  process.env.PLATO_HOSTED_TRIAL_PUBLICATIONS_PER_WEEK ?? "2",
);
const USAGE_LEDGER_PATH =
  process.env.PLATO_HOSTED_USAGE_LEDGER_PATH ||
  `${homedir()}/.plato/hosted-usage/weekly-publications.json`;

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

type PublicationLedger = Record<
  string,
  Record<string, { publications: number; updatedAt: string }>
>;
let ledgerWriteQueue = Promise.resolve();

const FORWARDED_REQUEST_HEADERS = new Set([
  "accept",
  "accept-language",
  "content-type",
  "cookie",
  "x-plato-run-id",
  "x-plato-user",
  "x-plato-auth-provider",
  "x-plato-lab-id",
]);

const RESPONSE_HEADER_BLOCKLIST = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "keep-alive",
  "transfer-encoding",
]);

function tenantFromHeaders(request: Request): string | null {
  const value = request.headers.get("X-Plato-User")?.trim();
  return value && /^[A-Za-z0-9._-]{1,64}$/.test(value) ? value : null;
}

function targetUrl(path: string[], request: Request): string {
  const incoming = new URL(request.url);
  const target = new URL(`/api/v1/${path.join("/")}`, API_PROXY_TARGET);
  target.search = incoming.search;
  return target.toString();
}

function isPublicationRun(path: string[], request: Request): boolean {
  return (
    request.method === "POST" &&
    path.length === 5 &&
    path[0] === "projects" &&
    path[2] === "stages" &&
    path[3] === "paper" &&
    path[4] === "run"
  );
}

function isPublicApiRequest(path: string[], request: Request): boolean {
  if (path.length === 1 && ["health", "capabilities"].includes(path[0])) {
    return true;
  }
  if (
    path[0] === "auth" &&
    path.length === 2 &&
    ["me", "login", "logout"].includes(path[1] ?? "")
  ) {
    return true;
  }
  if (!["GET", "HEAD"].includes(request.method)) {
    return false;
  }
  return path[0] === "publications";
}

function weekKey(date = new Date()): string {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

async function readLedger(): Promise<PublicationLedger> {
  try {
    return JSON.parse(await readFile(USAGE_LEDGER_PATH, "utf8")) as PublicationLedger;
  } catch {
    return {};
  }
}

async function writeLedger(ledger: PublicationLedger): Promise<void> {
  await mkdir(dirname(USAGE_LEDGER_PATH), { recursive: true });
  await writeFile(USAGE_LEDGER_PATH, JSON.stringify(ledger, null, 2), "utf8");
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

async function reservePublicationSlot(tenant: string): Promise<Response | null> {
  if (!Number.isFinite(TRIAL_PUBLICATION_LIMIT) || TRIAL_PUBLICATION_LIMIT <= 0) {
    return null;
  }
  if (!(await shouldApplyTrialLimit())) return null;
  const key = weekKey();
  const writeTask = ledgerWriteQueue.then(async () => {
    const ledger = await readLedger();
    ledger[tenant] ??= {};
    const current = ledger[tenant][key]?.publications ?? 0;
    if (current >= TRIAL_PUBLICATION_LIMIT) {
      return Response.json(
        {
          code: "trial_publication_limit_exceeded",
          message: `This trial/free billing scope is limited to ${TRIAL_PUBLICATION_LIMIT} scientific publications per week.`,
          week: key,
          used: current,
          limit: TRIAL_PUBLICATION_LIMIT,
        },
        { status: 402 },
      );
    }
    ledger[tenant][key] = {
      publications: current + 1,
      updatedAt: new Date().toISOString(),
    };
    await writeLedger(ledger);
    return null;
  });
  ledgerWriteQueue = writeTask.then(
    () => undefined,
    () => undefined,
  );
  return await writeTask;
}

function forwardedHeaders(request: Request): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (FORWARDED_REQUEST_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  const incoming = new URL(request.url);
  headers.set(
    "x-forwarded-host",
    request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? incoming.host,
  );
  headers.set(
    "x-forwarded-proto",
    request.headers.get("x-forwarded-proto") ?? incoming.protocol.replace(":", ""),
  );
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
  const tenant = tenantFromHeaders(request);
  const publicationRun = isPublicationRun(path, request);
  const publicApiRequest = isPublicApiRequest(path, request);

  if (CLERK_AUTH_ENABLED && !tenant && !publicApiRequest) {
    return Response.json(
      { code: "auth_required", message: "Sign in with Clerk before accessing Plato." },
      { status: 401 },
    );
  }

  if (publicationRun && tenant) {
    const limited = await reservePublicationSlot(tenant);
    if (limited) return limited;
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(targetUrl(path, request), {
      method: request.method,
      headers: forwardedHeaders(request),
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
    });
  } catch (error) {
    return Response.json(
      {
        code: "backend_unavailable",
        message: "Plato backend is offline. Start it with `plato dashboard`.",
        detail: error instanceof Error ? error.message : "Failed to reach backend",
      },
      { status: 503 },
    );
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
