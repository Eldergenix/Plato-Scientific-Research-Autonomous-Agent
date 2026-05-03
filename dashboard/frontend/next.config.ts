import path from "node:path";
import type { NextConfig } from "next";

// Baseline security headers applied to every response. CSP is
// intentionally permissive on `'unsafe-inline'` for now — the
// inline themeBootstrap script in app/layout.tsx requires it. A
// follow-up can replace the inline script with a nonce-based one
// and tighten the CSP. The other headers are unconditional wins.
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    // Browser API permissions we never need — explicitly deny so a
    // future xss / supply-chain attack can't trigger camera/mic/geo.
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

// Anchor turbopack to this dashboard/frontend folder so Next stops
// inferring the workspace root from a sibling pnpm-lock.yaml in the
// user's home directory.
const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(__dirname),
  },
  async headers() {
    return [
      {
        // Apply to every route. /api/* is served by FastAPI in
        // production (different process), so this only covers the
        // Next.js-served HTML/static assets.
        source: "/(.*)",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

export default nextConfig;
