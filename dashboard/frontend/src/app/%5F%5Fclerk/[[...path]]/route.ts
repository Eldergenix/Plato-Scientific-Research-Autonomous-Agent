import { createFrontendApiProxyHandlers } from "@clerk/nextjs/server";

export const runtime = "nodejs";

export const { GET, POST, PUT, DELETE, PATCH } = createFrontendApiProxyHandlers({
  proxyPath: "/__clerk",
});
