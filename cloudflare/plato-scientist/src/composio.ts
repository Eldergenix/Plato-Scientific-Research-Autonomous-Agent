/**
 * Composio v3 REST client: connected accounts (OAuth handled by Composio), tool execution,
 * file staging, trigger instances and webhook verification.
 *
 * Every person is one Composio user, `plato-<account id>`, so their connections and
 * triggers are theirs alone. The deploy's COMPOSIO_API_KEY never reaches the browser.
 * Shapes used here were checked against the live API (2026-11-18).
 */
import { b64, type Env, enc, HttpError, type Sql, unb64 } from "./lib";

const HOST = "https://backend.composio.dev";
const BASE = `${HOST}/api/v3`;

export const userId = (accountId: string) => `plato-${accountId}`;

/** Toolkits people can connect, with the tools Plato uses on each. */
export const TOOLKITS = {
  googledrive: { name: "Google Drive", files: true, email: false },
  dropbox: { name: "Dropbox", files: true, email: false },
  one_drive: { name: "OneDrive", files: true, email: false },
  gmail: { name: "Gmail", files: false, email: true },
  outlook: { name: "Outlook", files: false, email: true },
} as const;
export type Toolkit = keyof typeof TOOLKITS;

export function toolkit(v: string): Toolkit {
  if (!(v in TOOLKITS)) throw new HttpError(404, "unknown service");
  return v as Toolkit;
}

export class ComposioError extends HttpError {}

function key(env: Env): string {
  if (!env.COMPOSIO_API_KEY) throw new HttpError(503, "Connected services are not configured on this deployment.");
  return env.COMPOSIO_API_KEY;
}

export async function call<T = Record<string, unknown>>(
  env: Env,
  method: string,
  path: string,
  body?: unknown,
  base = BASE,
): Promise<T> {
  // Local development only: PLATO_DEV_COMPOSIO_BASE_URL points every call at a stub.
  const url = (env.PLATO_DEV_COMPOSIO_BASE_URL ? base.replace(HOST, env.PLATO_DEV_COMPOSIO_BASE_URL.replace(/\/$/, "")) : base) + path;
  const res = await fetch(url, {
    method,
    headers: { "x-api-key": key(env), ...(body !== undefined ? { "content-type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* not JSON */
  }
  if (!res.ok) {
    const err = (data as { error?: { message?: string } } | null)?.error;
    console.warn(JSON.stringify({ event: "composio_error", method, path: path.split("?")[0], status: res.status }));
    throw new ComposioError(res.status === 404 ? 404 : 502, err?.message ?? `connected service error (${res.status})`);
  }
  return data as T;
}

/* ---------- auth configs and connections ---------- */

/** The Composio-managed OAuth auth config for a toolkit, created once and cached. */
export async function authConfig(env: Env, sql: Sql, tk: Toolkit): Promise<string> {
  const [row] = await sql`SELECT auth_config_id FROM plato.composio_auth_configs WHERE toolkit = ${tk}`;
  if (row) return row.auth_config_id as string;
  const existing = await call<{ items: { id: string; status?: string; is_composio_managed?: boolean }[] }>(
    env,
    "GET",
    `/auth_configs?toolkit_slug=${tk}&limit=50`,
  );
  let id = existing.items?.find((a) => a.is_composio_managed !== false && (a.status ?? "ENABLED") === "ENABLED")?.id;
  if (!id) {
    const created = await call<{ auth_config: { id: string } }>(env, "POST", "/auth_configs", {
      toolkit: { slug: tk },
      auth_config: { type: "use_composio_managed_auth" },
    });
    id = created.auth_config.id;
  }
  await sql`INSERT INTO plato.composio_auth_configs (toolkit, auth_config_id) VALUES (${tk}, ${id})
            ON CONFLICT (toolkit) DO NOTHING`;
  const [stored] = await sql`SELECT auth_config_id FROM plato.composio_auth_configs WHERE toolkit = ${tk}`;
  return stored.auth_config_id as string;
}

export interface Connection {
  id: string;
  toolkit: string;
  status: string;
  created_at?: string;
}

export async function connections(env: Env, accountId: string): Promise<Connection[]> {
  const out = await call<{ items: { id: string; status: string; toolkit?: { slug?: string }; created_at?: string }[] }>(
    env,
    "GET",
    `/connected_accounts?user_ids=${encodeURIComponent(userId(accountId))}&limit=100`,
  );
  return (out.items ?? []).map((c) => ({ id: c.id, toolkit: c.toolkit?.slug ?? "", status: c.status, created_at: c.created_at }));
}

export async function connectLink(env: Env, sql: Sql, accountId: string, tk: Toolkit, callbackUrl: string) {
  const out = await call<{ redirect_url: string; connected_account_id: string }>(env, "POST", "/connected_accounts/link", {
    auth_config_id: await authConfig(env, sql, tk),
    user_id: userId(accountId),
    callback_url: callbackUrl,
  });
  return out;
}

export async function disconnect(env: Env, connectionId: string): Promise<void> {
  await call(env, "DELETE", `/connected_accounts/${encodeURIComponent(connectionId)}`);
}

/* ---------- tools ---------- */

interface ExecResult {
  data: Record<string, unknown>;
  error: string | null;
  successful: boolean;
}

export async function execute(env: Env, accountId: string, tool: string, args: Record<string, unknown>) {
  const out = await call<ExecResult>(env, "POST", `/tools/execute/${tool}`, {
    user_id: userId(accountId),
    arguments: args,
  });
  if (!out.successful) throw new ComposioError(502, `${tool}: ${(out.error ?? "failed").slice(0, 300)}`);
  return out.data ?? {};
}

/** A file a tool returned (Composio stages it and gives a short-lived URL). */
export interface FileRef {
  name: string;
  mimetype: string;
  s3url: string;
}

export async function fetchFile(ref: FileRef, maxBytes: number): Promise<Uint8Array> {
  const res = await fetch(ref.s3url);
  if (!res.ok) throw new ComposioError(502, `could not download ${ref.name} (${res.status})`);
  const len = Number(res.headers.get("content-length") ?? 0);
  if (len > maxBytes) throw new HttpError(413, `${ref.name} is larger than ${Math.round(maxBytes / 2 ** 20)} MiB`);
  const buf = new Uint8Array(await res.arrayBuffer());
  if (buf.byteLength > maxBytes) throw new HttpError(413, `${ref.name} is larger than ${Math.round(maxBytes / 2 ** 20)} MiB`);
  return buf;
}

async function md5Hex(data: Uint8Array): Promise<string> {
  // node:crypto via nodejs_compat (Web Crypto has no MD5).
  const { createHash } = await import("node:crypto");
  return createHash("md5").update(data).digest("hex");
}

/** Stage bytes in Composio's file store for a tool argument: ``{name, mimetype, s3key}``. */
export async function stageFile(env: Env, tk: Toolkit, tool: string, name: string, mimetype: string, data: Uint8Array) {
  const req = await call<{ key: string; new_presigned_url: string; metadata?: { storage_backend?: string } }>(
    env,
    "POST",
    "/files/upload/request",
    { toolkit_slug: tk, tool_slug: tool, filename: name, mimetype, md5: await md5Hex(data) },
  );
  const headers: Record<string, string> = { "content-type": mimetype };
  if (req.metadata?.storage_backend === "azure_blob_storage") headers["x-ms-blob-type"] = "BlockBlob";
  const put = await fetch(req.new_presigned_url, { method: "PUT", headers, body: data });
  if (!put.ok) throw new ComposioError(502, `could not stage ${name} (${put.status})`);
  return { name, mimetype, s3key: req.key };
}

/** Dropbox's read tool returns the bytes inline as a string: base64 for binary files, or the
 * text itself. The file's size (from the tool's metadata) decides which reading is right;
 * without it, a string that decodes as base64 is taken as base64. */
export function inlineBytes(v: unknown, size = NaN): Uint8Array | null {
  if (typeof v !== "string") return null;
  const text = enc.encode(v);
  if (Number.isFinite(size) && text.byteLength === size) return text;
  try {
    const compact = v.replace(/\s+/g, "");
    if (/^[A-Za-z0-9+/]*={0,2}$/.test(compact) && compact.length % 4 === 0) {
      const raw = unb64(compact);
      if (!Number.isFinite(size) || raw.byteLength === size) return raw;
    }
  } catch {
    /* not base64 */
  }
  return text;
}

/* ---------- triggers ---------- */

export async function upsertTrigger(env: Env, accountId: string, slug: string, config: Record<string, unknown>) {
  const out = await call<{ trigger_id: string }>(
    env,
    "POST",
    `/trigger_instances/${slug}/upsert`,
    { user_id: userId(accountId), trigger_config: config },
    `${HOST}/api/v3.1`,
  );
  return out.trigger_id;
}

export async function deleteTrigger(env: Env, triggerId: string): Promise<void> {
  try {
    await call(env, "DELETE", `/trigger_instances/manage/${encodeURIComponent(triggerId)}`);
  } catch (err) {
    // 410: already gone at Composio (for example the connection was removed).
    if (!(err instanceof ComposioError)) throw err;
  }
}

/* ---------- webhooks ---------- */

/** Composio webhook verification: HMAC-SHA256 over ``id.timestamp.body`` keyed with the
 * subscription secret, base64; the header carries ``v1,<sig>`` (several space-separated
 * values are accepted). Deliveries older than 5 minutes are refused (replay). */
export async function verifyWebhook(secret: string, headers: Headers, body: string, now = Date.now()): Promise<boolean> {
  const id = headers.get("webhook-id");
  const ts = headers.get("webhook-timestamp");
  const sigs = headers.get("webhook-signature");
  if (!id || !ts || !sigs || !/^\d+$/.test(ts)) return false;
  if (Math.abs(now / 1000 - Number(ts)) > 300) return false;
  // Composio keys the HMAC with the secret string itself (docs: subscribing-to-events).
  const k = await crypto.subtle.importKey("raw", enc.encode(secret),{ name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const expected = b64(await crypto.subtle.sign("HMAC", k, enc.encode(`${id}.${ts}.${body}`)));
  for (const part of sigs.split(" ")) {
    const sig = part.includes(",") ? part.slice(part.indexOf(",") + 1) : part;
    if (sig.length === expected.length && crypto.subtle.timingSafeEqual(enc.encode(sig), enc.encode(expected))) return true;
  }
  return false;
}
