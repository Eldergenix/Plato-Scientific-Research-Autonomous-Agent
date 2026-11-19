/**
 * Accounts: open sign-up with email and password, cookie sessions, settings, the person's
 * own Anthropic key, and workspace administration.
 *
 * Secrets: every key is derived (HKDF) from one Worker secret, PLATO_SECRETS_KEY.
 *   * passwords  PBKDF2-SHA256 over HMAC(pepper, password) with a per-account salt. The
 *                pepper never reaches the database, so a database leak alone cannot be
 *                brute-forced offline. 100,000 iterations is the Workers runtime's maximum.
 *   * API keys   AES-256-GCM with a random IV, the account id as associated data (a row
 *                copied to another account does not decrypt) and a key version for rotation.
 *                Only the last four characters ever leave the Worker.
 *   * throttling subjects (IP, email) are stored as keyed hashes, not in the clear.
 * Sessions: 32 random bytes in an HttpOnly, Secure, SameSite=Lax __Host- cookie; the
 * database stores only its SHA-256.
 */
import Anthropic from "@anthropic-ai/sdk";
import {
  b64,
  b64url,
  enc,
  type Env,
  hex,
  HttpError,
  json,
  monthlyCap,
  readJson,
  sha256,
  type Sql,
  unb64,
  unhex,
  UUID_RE,
} from "./lib";

export interface Principal {
  /** null for the deploy's bearer token (scripts and the smoke test): an admin, no account. */
  accountId: string | null;
  email: string;
  name: string;
  isAdmin: boolean;
  /** Monthly default-key allowance in tokens; null means uncapped (admins). */
  cap: number | null;
  preferences: Record<string, unknown>;
  /** Hex SHA-256 of the session token, for "this session" in the security settings. */
  session: string | null;
}

export interface Ctx {
  req: Request;
  env: Env;
  ctx: ExecutionContext;
  url: URL;
  sql: Sql;
  who: Principal | null;
  /** Set-Cookie headers to add to the response. */
  cookies: string[];
}

const SESSION_COOKIE = "__Host-plato_session";
const SESSION_DAYS = 30;
const PBKDF2_ITERATIONS = 100_000;
const PEPPER_VERSION = "p1";
const KEY_VERSION = 1;

/* ---------- key derivation ---------- */

interface Keys {
  pepper: CryptoKey;
  subject: CryptoKey;
  aes: CryptoKey;
}
let keyCache: { secret: string; keys: Promise<Keys> } | null = null;

function keys(env: Env): Promise<Keys> {
  const secret = env.PLATO_SECRETS_KEY ?? "";
  if (keyCache?.secret === secret) return keyCache.keys;
  const make = async (): Promise<Keys> => {
    let raw: Uint8Array;
    try {
      raw = unb64(secret);
    } catch {
      raw = new Uint8Array();
    }
    if (raw.length < 32) throw new Error("PLATO_SECRETS_KEY must be at least 32 random bytes, base64-encoded");
    const master = await crypto.subtle.importKey("raw", raw, "HKDF", false, ["deriveKey"]);
    const derive = (info: string, alg: SubtleCryptoImportKeyAlgorithm, use: string[]) =>
      crypto.subtle.deriveKey(
        { name: "HKDF", hash: "SHA-256", salt: enc.encode("plato-scientist"), info: enc.encode(info) },
        master,
        alg,
        false,
        use,
      );
    const hmac = { name: "HMAC", hash: "SHA-256", length: 256 };
    const [pepper, subject, aes] = await Promise.all([
      derive(`plato/password-pepper/${PEPPER_VERSION}`, hmac, ["sign"]),
      derive("plato/auth-subject/v1", hmac, ["sign"]),
      derive(`plato/account-keys/v${KEY_VERSION}`, { name: "AES-GCM", length: 256 }, ["encrypt", "decrypt"]),
    ]);
    return { pepper, subject, aes };
  };
  const p = make();
  keyCache = { secret, keys: p };
  p.catch(() => {
    if (keyCache?.keys === p) keyCache = null;
  });
  return p;
}

/* ---------- passwords ---------- */

async function pbkdf2(env: Env, password: string, salt: Uint8Array, iterations: number): Promise<Uint8Array> {
  const peppered = await crypto.subtle.sign("HMAC", (await keys(env)).pepper, enc.encode(password));
  const base = await crypto.subtle.importKey("raw", peppered, "PBKDF2", false, ["deriveBits"]);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations }, base, 256));
}

export async function hashPassword(env: Env, password: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const dk = await pbkdf2(env, password, salt, PBKDF2_ITERATIONS);
  return `${PEPPER_VERSION}$pbkdf2_sha256$${PBKDF2_ITERATIONS}$${b64(salt)}$${b64(dk)}`;
}

export async function verifyPassword(env: Env, password: string, stored: string): Promise<boolean> {
  const [pv, alg, iter, salt, hash] = stored.split("$");
  if (pv !== PEPPER_VERSION || alg !== "pbkdf2_sha256" || !salt || !hash) return false;
  const want = unb64(hash);
  const got = await pbkdf2(env, password, unb64(salt), Number(iter));
  return want.length === got.length && crypto.subtle.timingSafeEqual(want, got);
}

// Verified against when the email is unknown, so both paths cost one PBKDF2.
const DUMMY_HASH = `${PEPPER_VERSION}$pbkdf2_sha256$${PBKDF2_ITERATIONS}$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=`;

/* ---------- own API key encryption ---------- */

export async function encryptKey(env: Env, accountId: string, key: string) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: enc.encode(accountId) },
    (await keys(env)).aes,
    enc.encode(key),
  );
  return { ciphertext: hex(ct), iv: hex(iv), version: KEY_VERSION };
}

/** The account's own key, or null if it has none. */
export async function ownKey(env: Env, sql: Sql, accountId: string | null): Promise<string | null> {
  if (!accountId) return null;
  const [row] = await sql`
    SELECT encode(ciphertext, 'hex') AS ct, encode(iv, 'hex') AS iv, key_version
      FROM plato.account_keys WHERE account_id = ${accountId}`;
  return row ? decryptKey(env, accountId, row.ct as string, row.iv as string, Number(row.key_version)) : null;
}

export async function decryptKey(env: Env, accountId: string, ctHex: string, ivHex: string, version: number) {
  if (version !== KEY_VERSION) throw new Error(`no decryption key for version ${version}`);
  const pt = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: unhex(ivHex), additionalData: enc.encode(accountId) },
    (await keys(env)).aes,
    unhex(ctHex),
  );
  return new TextDecoder().decode(pt);
}

/* ---------- sessions ---------- */

function readCookie(req: Request, name: string): string | null {
  for (const part of (req.headers.get("cookie") ?? "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return null;
}

const sessionCookie = (token: string, maxAge: number) =>
  `${SESSION_COOKIE}=${token}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;

async function startSession(c: Ctx, accountId: string): Promise<void> {
  const token = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const ua = (c.req.headers.get("user-agent") ?? "").slice(0, 300);
  await c.sql`
    INSERT INTO plato.sessions (token_hash, account_id, expires_at, user_agent)
    VALUES (decode(${hex(await sha256(token))}, 'hex'), ${accountId},
            now() + make_interval(days => ${SESSION_DAYS}), ${ua})`;
  c.cookies.push(sessionCookie(token, SESSION_DAYS * 86400));
}

async function constantEq(a: string, b: string): Promise<boolean> {
  const [x, y] = await Promise.all([sha256(a), sha256(b)]);
  return crypto.subtle.timingSafeEqual(x, y);
}

/** Who is calling: the deploy's bearer token, or a session cookie. */
export async function authenticate(c: Ctx): Promise<Principal | null> {
  const auth = c.req.headers.get("authorization");
  if (auth !== null) {
    const presented = auth.startsWith("Bearer ") ? auth.slice(7) : "";
    if (!c.env.PLATO_API_TOKEN || !(await constantEq(presented, c.env.PLATO_API_TOKEN))) return null;
    return { accountId: null, email: "", name: "Admin token", isAdmin: true, cap: null, preferences: {}, session: null };
  }
  const token = readCookie(c.req, SESSION_COOKIE);
  if (!token || token.length > 64) return null;
  const hash = hex(await sha256(token));
  const [row] = await c.sql`
    SELECT a.id, a.email, a.name, a.is_admin, a.monthly_token_cap, a.preferences,
           s.expires_at < now() + make_interval(days => ${SESSION_DAYS / 2}) AS renew
      FROM plato.sessions s JOIN plato.accounts a ON a.id = s.account_id
     WHERE s.token_hash = decode(${hash}, 'hex') AND s.expires_at > now()`;
  if (!row) return null;
  if (row.renew) {
    // Sliding expiry: an active session is extended once it is past half its life.
    await c.sql`UPDATE plato.sessions SET expires_at = now() + make_interval(days => ${SESSION_DAYS})
                 WHERE token_hash = decode(${hash}, 'hex')`;
    c.cookies.push(sessionCookie(token, SESSION_DAYS * 86400));
  }
  return {
    accountId: row.id as string,
    email: row.email as string,
    name: row.name as string,
    isAdmin: Boolean(row.is_admin),
    cap: row.is_admin ? null : monthlyCap(c.env, row.monthly_token_cap as number | null),
    preferences: (row.preferences ?? {}) as Record<string, unknown>,
    session: hash,
  };
}

/* ---------- throttling ---------- */

type AttemptKind = "signup" | "login_ip" | "login_email";

async function subject(env: Env, kind: AttemptKind, value: string): Promise<string> {
  return hex(await crypto.subtle.sign("HMAC", (await keys(env)).subject, enc.encode(`${kind}:${value}`)));
}

async function recentAttempts(sql: Sql, kind: AttemptKind, subj: string, minutes: number, failuresOnly: boolean) {
  const [row] = await sql`
    SELECT count(*)::int AS n FROM plato.auth_attempts
     WHERE kind = ${kind} AND subject = decode(${subj}, 'hex')
       AND created_at > now() - make_interval(mins => ${minutes})
       AND (NOT ${failuresOnly} OR NOT ok)`;
  return row.n as number;
}

async function recordAttempt(sql: Sql, kind: AttemptKind, subj: string, ok: boolean) {
  await sql`INSERT INTO plato.auth_attempts (kind, subject, ok) VALUES (${kind}, decode(${subj}, 'hex'), ${ok})`;
}

const clientIp = (req: Request) => req.headers.get("cf-connecting-ip") ?? "unknown";

/* ---------- validation ---------- */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function str(body: Record<string, unknown>, key: string, { min = 0, max = 1000, trim = true } = {}): string {
  const v = body[key];
  if (typeof v !== "string") throw new HttpError(400, `${key} is required`);
  const s = trim ? v.trim() : v;
  if (s.length < min || s.length > max) throw new HttpError(400, `${key} must be ${min}–${max} characters`);
  return s;
}

function email(body: Record<string, unknown>): string {
  const e = str(body, "email", { min: 3, max: 254 }).toLowerCase();
  if (!EMAIL_RE.test(e)) throw new HttpError(400, "Enter a valid email address.");
  return e;
}

function password(body: Record<string, unknown>, key = "password"): string {
  const v = body[key];
  if (typeof v !== "string" || v.length < 10) throw new HttpError(400, "Use a password of at least 10 characters.");
  if (v.length > 200) throw new HttpError(400, "Use a password of at most 200 characters.");
  return v;
}

/** Account preferences: a closed set of keys, each with its allowed values. */
const PREFERENCES: Record<string, (v: unknown) => boolean> = {
  home: (v) => v === "agent" || v === "campaigns",
  theme: (v) => v === "system" || v === "light" || v === "dark",
  reduce_motion: (v) => typeof v === "boolean",
  open_paper_while_writing: (v) => typeof v === "boolean",
  follow_live_writing: (v) => typeof v === "boolean",
  compact_grid: (v) => typeof v === "boolean",
  send_with_mod_enter: (v) => typeof v === "boolean",
};

/* ---------- handlers ---------- */

export async function signup(c: Ctx): Promise<Response> {
  const body = await readJson(c.req);
  const addr = email(body);
  const pw = password(body);
  const name = typeof body.name === "string" ? body.name.trim().slice(0, 80) : "";
  const ipSubject = await subject(c.env, "signup", clientIp(c.req));
  if ((await recentAttempts(c.sql, "signup", ipSubject, 60, false)) >= 5) {
    throw new HttpError(429, "Too many sign-ups from this network. Try again in an hour.");
  }
  await recordAttempt(c.sql, "signup", ipSubject, true);
  const hash = await hashPassword(c.env, pw);
  const [row] = await c.sql`
    INSERT INTO plato.accounts (email, name, password_hash) VALUES (${addr}, ${name}, ${hash})
    ON CONFLICT (email) DO NOTHING RETURNING id`;
  if (!row) throw new HttpError(409, "An account with this email already exists. Sign in instead.");
  await startSession(c, row.id as string);
  return json({ ok: true }, 201);
}

export async function login(c: Ctx): Promise<Response> {
  const body = await readJson(c.req);
  const addr = email(body);
  const pw = typeof body.password === "string" ? body.password.slice(0, 200) : "";
  const [ipSubject, emailSubject] = await Promise.all([
    subject(c.env, "login_ip", clientIp(c.req)),
    subject(c.env, "login_email", addr),
  ]);
  const [byIp, byEmail] = await Promise.all([
    recentAttempts(c.sql, "login_ip", ipSubject, 15, true),
    recentAttempts(c.sql, "login_email", emailSubject, 15, true),
  ]);
  if (byIp >= 30 || byEmail >= 10) throw new HttpError(429, "Too many attempts. Wait 15 minutes and try again.");
  const [acct] = await c.sql`SELECT id, password_hash FROM plato.accounts WHERE email = ${addr}`;
  const ok = await verifyPassword(c.env, pw, (acct?.password_hash as string) ?? DUMMY_HASH);
  await Promise.all([
    recordAttempt(c.sql, "login_ip", ipSubject, ok && !!acct),
    recordAttempt(c.sql, "login_email", emailSubject, ok && !!acct),
  ]);
  if (!acct || !ok) throw new HttpError(401, "Incorrect email or password.");
  await startSession(c, acct.id as string);
  return json({ ok: true });
}

export async function logout(c: Ctx): Promise<Response> {
  const token = readCookie(c.req, SESSION_COOKIE);
  if (token && token.length <= 64) {
    await c.sql`DELETE FROM plato.sessions WHERE token_hash = decode(${hex(await sha256(token))}, 'hex')`;
  }
  c.cookies.push(sessionCookie("", 0));
  return json({ ok: true });
}

/** Public, so a signed-out visitor gets {account: null} rather than a 401 the browser logs as an error. */
export async function me(c: Ctx): Promise<Response> {
  const who = (c.who = await authenticate(c));
  if (!who) return json({ account: null });
  if (!who.accountId) {
    return json({ account: null, admin_token: true, model: c.env.PLATO_SCIENTIST_MODEL });
  }
  const [[acct], [key], [usage]] = await Promise.all([
    c.sql`SELECT id, email, name, is_admin, preferences, created_at FROM plato.accounts WHERE id = ${who.accountId}`,
    c.sql`SELECT last4, created_at FROM plato.account_keys WHERE account_id = ${who.accountId}`,
    c.sql`SELECT plato.account_committed_tokens(${who.accountId}::uuid) AS committed`,
  ]);
  return json({
    account: acct,
    key: key ?? null,
    allowance: { cap: who.cap, committed: Number(usage.committed), own_key: Boolean(key) },
    model: c.env.PLATO_SCIENTIST_MODEL,
  });
}

export async function updateMe(c: Ctx): Promise<Response> {
  const who = c.who!;
  const body = await readJson(c.req);
  let name: string | null = null;
  if (body.name !== undefined) name = str(body, "name", { max: 80 });
  let prefs: Record<string, unknown> = {};
  if (body.preferences !== undefined) {
    const p = body.preferences;
    if (!p || typeof p !== "object" || Array.isArray(p)) throw new HttpError(400, "preferences must be an object");
    for (const [k, v] of Object.entries(p)) {
      if (!PREFERENCES[k]?.(v)) throw new HttpError(400, `invalid preference: ${k}`);
    }
    prefs = p as Record<string, unknown>;
  }
  const [row] = await c.sql`
    UPDATE plato.accounts SET name = COALESCE(${name}, name), preferences = preferences || ${c.sql.json(prefs as never)}
     WHERE id = ${who.accountId!} RETURNING name, preferences`;
  return json(row);
}

export async function changePassword(c: Ctx): Promise<Response> {
  const who = c.who!;
  const body = await readJson(c.req);
  const current = typeof body.current === "string" ? body.current.slice(0, 200) : "";
  const next = password(body);
  const [acct] = await c.sql`SELECT password_hash FROM plato.accounts WHERE id = ${who.accountId!}`;
  if (!(await verifyPassword(c.env, current, acct.password_hash as string))) {
    throw new HttpError(403, "Your current password is incorrect.");
  }
  const hash = await hashPassword(c.env, next);
  await c.sql.begin(async (tx) => {
    await tx`UPDATE plato.accounts SET password_hash = ${hash} WHERE id = ${who.accountId!}`;
    // A changed password signs out every other session.
    await tx`DELETE FROM plato.sessions WHERE account_id = ${who.accountId!}
              AND token_hash <> decode(${who.session!}, 'hex')`;
  });
  return json({ ok: true });
}

export async function deleteMe(c: Ctx): Promise<Response> {
  const who = c.who!;
  const body = await readJson(c.req);
  const pw = typeof body.password === "string" ? body.password.slice(0, 200) : "";
  const [acct] = await c.sql`SELECT password_hash FROM plato.accounts WHERE id = ${who.accountId!}`;
  if (!(await verifyPassword(c.env, pw, acct.password_hash as string))) {
    throw new HttpError(403, "Your password is incorrect.");
  }
  // Sessions, keys, projects and agent history cascade; campaigns keep running unowned.
  await c.sql`DELETE FROM plato.accounts WHERE id = ${who.accountId!}`;
  c.cookies.push(sessionCookie("", 0));
  return json({ ok: true });
}

export async function listSessions(c: Ctx): Promise<Response> {
  const who = c.who!;
  const rows = await c.sql`
    SELECT created_at, expires_at, user_agent, token_hash = decode(${who.session!}, 'hex') AS current
      FROM plato.sessions WHERE account_id = ${who.accountId!} AND expires_at > now()
     ORDER BY created_at DESC LIMIT 50`;
  return json({ sessions: rows });
}

export async function revokeOtherSessions(c: Ctx): Promise<Response> {
  const who = c.who!;
  const rows = await c.sql`
    DELETE FROM plato.sessions WHERE account_id = ${who.accountId!}
       AND token_hash <> decode(${who.session!}, 'hex') RETURNING 1`;
  return json({ revoked: rows.length });
}

const KEY_RE = /^sk-ant-[A-Za-z0-9_-]{20,300}$/;

export async function putKey(c: Ctx): Promise<Response> {
  const who = c.who!;
  const body = await readJson(c.req);
  const key = typeof body.key === "string" ? body.key.trim() : "";
  if (!KEY_RE.test(key)) throw new HttpError(400, "That doesn't look like an Anthropic API key (sk-ant-…).");
  // Prove the key works before storing it: a models listing costs nothing.
  try {
    const client = new Anthropic({
      apiKey: key,
      maxRetries: 1,
      timeout: 15_000,
      ...(c.env.PLATO_DEV_ANTHROPIC_BASE_URL ? { baseURL: c.env.PLATO_DEV_ANTHROPIC_BASE_URL } : {}),
    });
    await client.models.list({ limit: 1 });
  } catch (err) {
    if (err instanceof Anthropic.AuthenticationError || err instanceof Anthropic.PermissionDeniedError) {
      throw new HttpError(422, "Anthropic didn't accept this key. Check it and try again.");
    }
    console.error("key check failed", err instanceof Error ? err.name : "error");
    throw new HttpError(502, "Couldn't reach Anthropic to check the key. Try again in a moment.");
  }
  const sealed = await encryptKey(c.env, who.accountId!, key);
  const [row] = await c.sql`
    INSERT INTO plato.account_keys (account_id, ciphertext, iv, key_version, last4)
    VALUES (${who.accountId!}, decode(${sealed.ciphertext}, 'hex'), decode(${sealed.iv}, 'hex'),
            ${sealed.version}, ${key.slice(-4)})
    ON CONFLICT (account_id) DO UPDATE SET ciphertext = EXCLUDED.ciphertext, iv = EXCLUDED.iv,
        key_version = EXCLUDED.key_version, last4 = EXCLUDED.last4, created_at = now()
    RETURNING last4, created_at`;
  return json({ key: row });
}

export async function deleteKey(c: Ctx): Promise<Response> {
  await c.sql`DELETE FROM plato.account_keys WHERE account_id = ${c.who!.accountId!}`;
  return json({ key: null });
}

/** Link the deploy's admin token to this account, making it a workspace admin. */
export async function claimAdmin(c: Ctx): Promise<Response> {
  const body = await readJson(c.req);
  const token = typeof body.token === "string" ? body.token.trim() : "";
  const ipSubject = await subject(c.env, "login_ip", clientIp(c.req));
  if ((await recentAttempts(c.sql, "login_ip", ipSubject, 15, true)) >= 30) {
    throw new HttpError(429, "Too many attempts. Wait 15 minutes and try again.");
  }
  const ok = Boolean(c.env.PLATO_API_TOKEN) && (await constantEq(token, c.env.PLATO_API_TOKEN));
  await recordAttempt(c.sql, "login_ip", ipSubject, ok);
  if (!ok) throw new HttpError(403, "That isn't the admin token for this deployment.");
  await c.sql`UPDATE plato.accounts SET is_admin = true WHERE id = ${c.who!.accountId!}`;
  return json({ ok: true });
}

export async function listAccounts(c: Ctx): Promise<Response> {
  const rows = await c.sql`
    SELECT a.id, a.email, a.name, a.is_admin, a.monthly_token_cap, a.created_at,
           plato.account_committed_tokens(a.id) AS committed,
           (k.account_id IS NOT NULL) AS own_key,
           (SELECT max(s.created_at) FROM plato.sessions s WHERE s.account_id = a.id) AS last_sign_in,
           (SELECT count(*)::int FROM plato.research_campaigns r WHERE r.account_id = a.id) AS campaigns
      FROM plato.accounts a LEFT JOIN plato.account_keys k ON k.account_id = a.id
     ORDER BY a.created_at LIMIT 500`;
  return json({ accounts: rows, default_cap: monthlyCap(c.env, null) });
}

export async function updateAccount(c: Ctx, id: string): Promise<Response> {
  if (!UUID_RE.test(id)) throw new HttpError(400, "invalid id");
  const body = await readJson(c.req);
  let isAdmin: boolean | null = null;
  if (body.is_admin !== undefined) {
    if (typeof body.is_admin !== "boolean") throw new HttpError(400, "is_admin must be a boolean");
    if (id === c.who!.accountId) throw new HttpError(400, "You can't change your own role.");
    isAdmin = body.is_admin;
  }
  let setCap = false;
  let cap: number | null = null;
  if (body.monthly_token_cap !== undefined) {
    const v = body.monthly_token_cap;
    if (v !== null && (typeof v !== "number" || !Number.isInteger(v) || v < 0 || v > 10_000_000_000)) {
      throw new HttpError(400, "monthly_token_cap must be a whole number of tokens or null");
    }
    setCap = true;
    cap = v as number | null;
  }
  const [row] = await c.sql`
    UPDATE plato.accounts
       SET is_admin = COALESCE(${isAdmin}, is_admin),
           monthly_token_cap = CASE WHEN ${setCap} THEN ${cap}::bigint ELSE monthly_token_cap END
     WHERE id = ${id} RETURNING id, is_admin, monthly_token_cap`;
  if (!row) throw new HttpError(404, "account not found");
  return json(row);
}
