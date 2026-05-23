import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import {
  clerkAuthConfigError,
  isClerkAuthEnabled,
  isClerkAuthMisconfigured,
  platoTenantHeadersForClerkSession,
} from "@/lib/auth-mode";
import { publicRequestUrl } from "@/lib/public-origin";
import type { NextFetchEvent, NextRequest } from "next/server";

const clerkAuthEnabled = isClerkAuthEnabled();
const clerkAuthMisconfigured = isClerkAuthMisconfigured();

const tenantAuthRequired =
  process.env.PLATO_AUTH === "enabled" ||
  process.env.PLATO_DASHBOARD_AUTH_REQUIRED === "1";

const TENANT_COOKIE = "plato_user";

const API_PREFIX = "/api/v1";
const CLERK_PROXY_PREFIX = "/__clerk";
const PUBLIC_PATHS = new Set([
  "/landing",
  "/login",
  "/login/validation-demo",
  "/sign-in",
  "/sign-up",
]);

function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.has(pathname)) return true;
  if (pathname.startsWith(CLERK_PROXY_PREFIX)) return true;
  if (pathname.startsWith("/sign-in/") || pathname.startsWith("/sign-up/")) {
    return true;
  }
  return pathname.startsWith("/_next/") || pathname.includes(".");
}

function isClerkConfigDiagnosticPath(pathname: string): boolean {
  return (
    pathname === "/settings/account" ||
    pathname.startsWith("/settings/account/") ||
    pathname === "/settings/organization" ||
    pathname.startsWith("/settings/organization/") ||
    pathname === "/settings/billing" ||
    pathname.startsWith("/settings/billing/")
  );
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

function isPublicApiRequest(request: NextRequest): boolean {
  const { pathname } = request.nextUrl;
  if (
    pathname === "/api/v1/health" ||
    pathname === "/api/v1/capabilities" ||
    pathname === "/api/v1/auth/me"
  ) {
    return true;
  }
  if (
    !clerkAuthEnabled &&
    !clerkAuthMisconfigured &&
    (pathname === "/api/v1/auth/login" || pathname === "/api/v1/auth/logout")
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

function skipClerkProxyPath(request: NextRequest): NextResponse | undefined {
  if (request.nextUrl.pathname.startsWith(CLERK_PROXY_PREFIX)) {
    return NextResponse.next();
  }
}

const clerkProxy = clerkAuthEnabled
  ? clerkMiddleware(
      async (auth, request) => {
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
        const tenantHeaders = platoTenantHeadersForClerkSession(session);
        tenantHeaders?.forEach((value, key) => requestHeaders.set(key, value));

        return NextResponse.next({
          request: {
            headers: requestHeaders,
          },
        });
      },
      { proxyUrl: process.env.NEXT_PUBLIC_CLERK_PROXY_URL ?? CLERK_PROXY_PREFIX },
    )
  : tenantProxy;

export default function proxy(request: NextRequest, event: NextFetchEvent) {
  if (clerkAuthMisconfigured) {
    if (request.nextUrl.pathname.startsWith(API_PREFIX)) {
      if (isPublicApiRequest(request)) return NextResponse.next();
      return NextResponse.json(
        {
          code: "clerk_auth_misconfigured",
          message: "Hosted Clerk auth is requested but Clerk keys are missing or invalid.",
          detail: clerkAuthConfigError(),
        },
        { status: 503 },
      );
    }
    if (!isPublicPath(request.nextUrl.pathname)) {
      if (isClerkConfigDiagnosticPath(request.nextUrl.pathname)) {
        return NextResponse.next();
      }
      return redirectToLogin(request);
    }
  }
  return skipClerkProxyPath(request) ?? clerkProxy(request, event);
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
    "/__clerk/(.*)",
  ],
};
