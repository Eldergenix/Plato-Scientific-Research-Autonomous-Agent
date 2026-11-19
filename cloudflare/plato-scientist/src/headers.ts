// Security headers for /api/* responses. Static responses (the UI) get theirs from
// public/_headers, because run_worker_first sends only /api/* through the Worker.

const COMMON: Record<string, string> = {
  "strict-transport-security": "max-age=31536000",
  "x-content-type-options": "nosniff",
  "referrer-policy": "strict-origin-when-cross-origin",
  "x-frame-options": "SAMEORIGIN",
};

// API JSON is data, never a document: nothing in it may load or run, and no page may frame it.
const JSON_CSP = "default-src 'none'; frame-ancestors 'none'";

/** Add the security headers a handler did not set itself. A handler's own value wins, so file
 * responses keep their stricter sandboxed CSP; JSON gets a CSP that allows nothing. */
export function withSecurityHeaders(res: Response): Response {
  const out = new Response(res.body, res); // copies status and headers into a mutable response
  for (const [k, v] of Object.entries(COMMON)) if (!out.headers.has(k)) out.headers.set(k, v);
  const type = out.headers.get("content-type") ?? "";
  if (!out.headers.has("content-security-policy") && (type === "" || type.startsWith("application/json")))
    out.headers.set("content-security-policy", JSON_CSP);
  return out;
}
