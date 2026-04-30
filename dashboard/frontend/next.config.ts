import path from "node:path";
import type { NextConfig } from "next";

// Anchor turbopack to this dashboard/frontend folder so Next stops
// inferring the workspace root from a sibling pnpm-lock.yaml in the
// user's home directory.
const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
