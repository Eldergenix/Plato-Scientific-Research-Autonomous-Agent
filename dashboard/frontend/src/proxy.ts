import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { toPlatoTenantId } from "@/lib/plato-tenant";
import type { NextRequest } from "next/server";

const clerkAuthEnabled =
  (process.env.PLATO_AUTH_PROVIDER === "clerk" ||
    process.env.NEXT_PUBLIC_PLATO_AUTH_PROVIDER === "clerk") &&
  Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) &&
  Boolean(process.env.CLERK_SECRET_KEY);

const tenantAuthRequired =
  process.env.PLATO_AUTH === "enabled" ||
  process.env.PLATO_DASHBOARD_AUTH_REQUIRED === "1";

const TENANT_COOKIE = "plato_user";

const API_PREFIX = "/api/v1";
const PUBLIC_PATHS = new Set([
  "/login",
  "/login/validation-demo",
  "/sign-in",
  "/sign-up",
]);

function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.has(pathname)) return true;
  if (pathname.startsWith("/sign-in/") || pathname.startsWith("/sign-up/")) {
    return true;
  }
  return pathname.startsWith("/_next/") || pathname.includes(".");
}

function redirectToLogin(request: NextRequest): NextResponse {
  const redirectUrl = request.nextUrl.clone();
  const nextPath = `${request.nextUrl.pathname}${request.nextUrl.search}`;

  redirectUrl.pathname = "/login";
  redirectUrl.search = "";
  if (nextPath !== "/login") {
    redirectUrl.searchParams.set("next", nextPath);
  }

  return NextResponse.redirect(redirectUrl);
}

function publicRequestUrl(request: NextRequest): string {
  const forwardedHost =
    request.headers.get("x-forwarded-host") ??
    request.headers.get("host") ??
    request.nextUrl.host;
  const forwardedProto =
    request.headers.get("x-forwarded-proto") ??
    (forwardedHost.includes("localhost") ? "http" : "https");

  return `${forwardedProto}://${forwardedHost}${request.nextUrl.pathname}${request.nextUrl.search}`;
}

function isPublicApiRequest(request: NextRequest): boolean {
  const { pathname } = request.nextUrl;
  if (
    pathname === "/api/v1/health" ||
    pathname === "/api/v1/capabilities" ||
    pathname === "/api/v1/auth/me" ||
    pathname === "/api/v1/auth/login" ||
    pathname === "/api/v1/auth/logout"
  ) {
    return true;
  }
  if (!["GET", "HEAD"].includes(request.method)) {
    return false;
  }
  return (
    pathname === "/api/v1/publications" ||
    pathname === "/api/v1/publications/rss.xml" ||
    /^\/api\/v1\/publications\/[^/]+$/.test(pathname)
  );
}

function tenantProxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  const isApiRequest = pathname.startsWith(API_PREFIX);

  if (isApiRequest && isPublicApiRequest(request)) {
    return NextResponse.next();
  }

  if (!tenantAuthRequired || request.cookies.has(TENANT_COOKIE)) {
    return NextResponse.next();
  }

  if (isApiRequest) {
    return NextResponse.json(
      {
        code: "auth_required",
        message: "Sign in before accessing Plato.",
      },
      { status: 401 },
    );
  }

  if (!isPublicPath(pathname)) {
    return redirectToLogin(request);
  }

  return NextResponse.next();
}

const clerkProxy = clerkAuthEnabled ? clerkMiddleware(async (auth, request) => {
  const pathname = request.nextUrl.pathname;
  const isApiRequest = pathname.startsWith(API_PREFIX);
  if (isApiRequest && isPublicApiRequest(request)) {
    return NextResponse.next();
  }

  const session = await auth();
  if (!session.userId) {
    if (isApiRequest) {
      return NextResponse.json(
        {
          code: "auth_required",
          message: "Sign in with Clerk before accessing Plato.",
        },
        { status: 401 },
      );
    }
    if (!isPublicPath(pathname)) {
      return session.redirectToSignIn({ returnBackUrl: publicRequestUrl(request) });
    }
    return NextResponse.next();
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(
    "X-Plato-User",
    session.orgId
      ? toPlatoTenantId("lab", session.orgId)
      : toPlatoTenantId("user", session.userId),
  );
  requestHeaders.set("X-Plato-Auth-Provider", "clerk");
  if (session.orgId) {
    requestHeaders.set("X-Plato-Lab-Id", session.orgId);
  }

  return NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
}) : tenantProxy;

export default clerkProxy;

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
    "/__clerk/(.*)",
  ],
};
