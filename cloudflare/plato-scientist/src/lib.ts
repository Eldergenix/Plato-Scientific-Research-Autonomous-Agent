/** Shared plumbing for the Worker and its Durable Objects: env, JSON, Postgres, encoding. */
import postgres from "postgres";
import type { ProjectAgent } from "./agent";
import type { ScientistContainer } from "./worker";

export interface Env {
  ASSETS: Fetcher;
  HYPERDRIVE: Hyperdrive;
  PLATO_SCIENTIST: DurableObjectNamespace<ScientistContainer>;
  PROJECT_AGENT: DurableObjectNamespace<ProjectAgent>;
  PLATO_SCIENTIST_MODEL: string;
  /** Monthly default-key allowance per account, in tokens (accounts may override it). */
  PLATO_DEFAULT_MONTHLY_TOKENS: string;
  PLATO_API_TOKEN: string;
  PLATO_INTERNAL_TOKEN: string;
  /** 32+ random bytes, base64. Root of the password pepper and the API-key encryption key. */
  PLATO_SECRETS_KEY: string;
  ANTHROPIC_API_KEY: string;
  PLATO_DATABASE_URL: string;
  /** Optional literature-source keys: ADS needs a token; NCBI and Semantic Scholar raise rate limits. */
  ADS_API_KEY?: string;
  NCBI_API_KEY?: string;
  SEMANTIC_SCHOLAR_KEY?: string;
  /** Optional Modal Labs credentials: enable remote (and GPU) experiment runs. */
  MODAL_TOKEN_ID?: string;
  MODAL_TOKEN_SECRET?: string;
  /** Local development only: send container traffic to this URL (the Python service). */
  PLATO_DEV_SERVICE_URL?: string;
  /** Local development only: Anthropic API base URL (a stub server in tests). */
  PLATO_DEV_ANTHROPIC_BASE_URL?: string;
}

export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
// Postgres array literal: postgres.js cannot infer array parameter types with fetch_types off.
export const TERMINAL_STATUSES = "{completed,halted}";

/** An error with an HTTP status whose message is safe to show to the caller. */
export class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** JSON text of query results: int8 columns arrive as BigInt, which JSON.stringify rejects. */
export function toJson(data: unknown): string {
  return JSON.stringify(data, (_k, v) => (typeof v === "bigint" ? Number(v) : v));
}

export function json(data: unknown, status = 200, headers: HeadersInit = {}): Response {
  const h = new Headers(headers);
  h.set("content-type", "application/json; charset=utf-8");
  h.set("cache-control", "no-store");
  return new Response(toJson(data), { status, headers: h });
}

/** Parse a JSON object body (at most ``maxBytes``). JSON-only bodies also stop HTML forms
 * from posting here cross-site, on top of the SameSite cookie and the Origin check. */
export async function readJson(req: Request, maxBytes = 64 * 1024): Promise<Record<string, unknown>> {
  if (!(req.headers.get("content-type") ?? "").toLowerCase().startsWith("application/json")) {
    throw new HttpError(415, "expected application/json");
  }
  const text = await req.text();
  if (text.length > maxBytes) throw new HttpError(413, "request too large");
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw new HttpError(400, "invalid JSON");
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new HttpError(400, "expected a JSON object");
  return body as Record<string, unknown>;
}

export type Sql = ReturnType<typeof db>;

export function db(env: Env) {
  return postgres(env.HYPERDRIVE.connectionString, {
    max: 5,
    fetch_types: false, // no extra round trip for type metadata
    prepare: true, // Hyperdrive supports prepared statements and caches them
    idle_timeout: 5,
    types: { bigint: postgres.BigInt }, // int8 -> BigInt -> JSON number (not a string)
  });
}

export const enc = new TextEncoder();

export function b64(bytes: ArrayBuffer | Uint8Array): string {
  const u = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000));
  return btoa(s);
}

export function unb64(text: string): Uint8Array {
  const s = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

export const b64url = (bytes: ArrayBuffer | Uint8Array) =>
  b64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

export function hex(bytes: ArrayBuffer | Uint8Array): string {
  return [...(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes))]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function unhex(text: string): Uint8Array {
  const out = new Uint8Array(text.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(text.slice(2 * i, 2 * i + 2), 16);
  return out;
}

export async function sha256(data: string | Uint8Array): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", typeof data === "string" ? enc.encode(data) : data));
}

/** A UUID derived from a name (SHA-256, version 8 layout): the same name gives the same id,
 * which makes creates keyed by it idempotent across retries. */
export async function nameUuid(name: string): Promise<string> {
  const h = (await sha256(name)).slice(0, 16);
  h[6] = (h[6] & 0x0f) | 0x80;
  h[8] = (h[8] & 0x3f) | 0x80;
  const x = hex(h);
  return `${x.slice(0, 8)}-${x.slice(8, 12)}-${x.slice(12, 16)}-${x.slice(16, 20)}-${x.slice(20)}`;
}

export function monthlyCap(env: Env, accountCap: number | bigint | null | undefined): number {
  if (accountCap !== null && accountCap !== undefined) return Number(accountCap);
  const n = Number(env.PLATO_DEFAULT_MONTHLY_TOKENS);
  return Number.isFinite(n) && n >= 0 ? n : 5_000_000;
}
