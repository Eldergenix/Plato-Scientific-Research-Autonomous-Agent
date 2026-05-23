import "server-only";

import { createHmac } from "node:crypto";
import { secretKeyLooksValid } from "@/lib/auth-mode";

const DERIVED_PROXY_SECRET_CONTEXT = "plato-backend-proxy-secret-v1";

export function backendProxySecretForRequest(): string {
  const explicit = process.env.PLATO_BACKEND_PROXY_SECRET?.trim();
  if (explicit) return explicit;

  const clerkSecret = process.env.CLERK_SECRET_KEY?.trim();
  if (!secretKeyLooksValid(clerkSecret)) return "";

  return createHmac("sha256", clerkSecret as string)
    .update(DERIVED_PROXY_SECRET_CONTEXT)
    .digest("hex");
}
