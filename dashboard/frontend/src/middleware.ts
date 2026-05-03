import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Per-request CSP nonce. Generated fresh for every navigation so the
// inline themeBootstrap script in app/layout.tsx can be authorized
// without `'unsafe-inline'`. Keep style-src on `'unsafe-inline'` for
// now — Tailwind/Next inject inline styles (font CSS variables, JIT
// utilities) and a full nonce migration there is non-trivial.
export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");

  const csp = [
    `default-src 'self'`,
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    `style-src 'self' 'unsafe-inline'`,
    `img-src 'self' blob: data:`,
    `font-src 'self' data:`,
    `connect-src 'self'`,
    `frame-ancestors 'none'`,
    `base-uri 'self'`,
    `form-action 'self'`,
  ].join("; ");

  // Forward the nonce to RSC so layout.tsx can read it via headers().
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

// Skip CSP on static assets and the Next image optimizer — they don't
// execute scripts and the per-request work would just add latency.
export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
