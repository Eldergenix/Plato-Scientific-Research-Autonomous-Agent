import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { toPlatoTenantId } from "@/lib/plato-tenant";
import type { NextRequest } from "next/server";

const clerkAuthEnabled =
  process.env.PLATO_AUTH_PROVIDER === "clerk" ||
  process.env.NEXT_PUBLIC_PLATO_AUTH_PROVIDER === "clerk";

const API_PREFIX = "/api/v1";
const PUBLIC_PATHS = new Set(["/login", "/login/validation-demo"]);

function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.has(pathname)) return true;
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

function isPublicApiRequest(request: NextRequest): boolean {
  const { pathname } = request.nextUrl;
  if (pathname === "/api/v1/health" || pathname === "/api/v1/capabilities") {
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

function passthroughProxy(_request: NextRequest) {
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
      return redirectToLogin(request);
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
}) : passthroughProxy;

export default clerkProxy;

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
