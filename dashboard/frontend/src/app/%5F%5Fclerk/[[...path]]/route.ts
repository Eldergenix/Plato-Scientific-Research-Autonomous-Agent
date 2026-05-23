import { NextResponse } from "next/server";
import {
  clerkAuthConfigError,
  isClerkAuthEnabled,
  isClerkAuthMisconfigured,
} from "@/lib/auth-mode";
import { publicOrigin } from "@/lib/public-origin";
import type { NextRequest } from "next/server";

const CLERK_PROXY_PREFIX = "/__clerk";
const CLERK_FRONTEND_API = "https://frontend-api.clerk.dev";
const CLERK_AUTH_ENABLED = isClerkAuthEnabled();
const CLERK_AUTH_MISCONFIGURED = isClerkAuthMisconfigured();

const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "accept-language",
  "content-type",
  "cookie",
  "origin",
  "referer",
  "user-agent",
];

const HOP_BY_HOP_RESPONSE_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

const STRIPPED_RESPONSE_HEADERS = new Set([
  "content-encoding",
  "content-length",
  "transfer-encoding",
]);

function forwardedHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  for (const key of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(key);
    if (value) {
      headers.set(key, value);
    }
  }

  headers.set("accept-encoding", "identity");
  headers.set("clerk-proxy-url", `${publicOrigin(request)}${CLERK_PROXY_PREFIX}`);
  headers.set("clerk-secret-key", process.env.CLERK_SECRET_KEY ?? "");

  const clientIp =
    request.headers.get("cf-connecting-ip") ??
    request.headers.get("x-real-ip") ??
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  if (clientIp) {
    headers.set("x-forwarded-for", clientIp);
  }

  return headers;
}

function responseHeaders(response: Response, proxyOrigin: string): Headers {
  const headers = new Headers();
  response.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (!STRIPPED_RESPONSE_HEADERS.has(lower) && !HOP_BY_HOP_RESPONSE_HEADERS.has(lower)) {
      headers.append(key, value);
    }
  });

  const location = response.headers.get("location");
  if (location) {
    const locationUrl = new URL(location, CLERK_FRONTEND_API);
    if (locationUrl.origin === CLERK_FRONTEND_API) {
      headers.set(
        "location",
        `${proxyOrigin}${CLERK_PROXY_PREFIX}${locationUrl.pathname}${locationUrl.search}${locationUrl.hash}`,
      );
    }
  }

  return headers;
}

async function proxyClerk(request: NextRequest): Promise<Response> {
  if (CLERK_AUTH_MISCONFIGURED) {
    return NextResponse.json(
      {
        code: "clerk_auth_misconfigured",
        message: "Hosted Clerk auth is requested but Clerk keys are missing or invalid.",
        detail: clerkAuthConfigError(),
      },
      { status: 503 },
    );
  }

  if (!CLERK_AUTH_ENABLED) {
    return NextResponse.json(
      {
        code: "clerk_proxy_disabled",
        message: "Hosted Clerk authentication is not enabled for this deployment.",
      },
      { status: 404 },
    );
  }

  const targetPath = request.nextUrl.pathname.slice(CLERK_PROXY_PREFIX.length) || "/";
  const targetUrl = new URL(`${CLERK_FRONTEND_API}${targetPath}`);
  targetUrl.search = request.nextUrl.search;

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const response = await fetch(targetUrl, {
    method: request.method,
    headers: forwardedHeaders(request),
    redirect: "manual",
    ...(hasBody ? { body: request.body, duplex: "half" as const } : {}),
  });

  return new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders(response, publicOrigin(request)),
  });
}

export function GET(request: NextRequest) {
  return proxyClerk(request);
}

export function POST(request: NextRequest) {
  return proxyClerk(request);
}

export function PUT(request: NextRequest) {
  return proxyClerk(request);
}

export function DELETE(request: NextRequest) {
  return proxyClerk(request);
}

export function PATCH(request: NextRequest) {
  return proxyClerk(request);
}
