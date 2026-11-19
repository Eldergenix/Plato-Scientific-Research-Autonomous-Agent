/**
 * Plato autonomous scientist: Cloudflare edge for https://jarvisos.xyz
 *
 *   /            static UI (Workers Static Assets)
 *   /api/*       JSON API, signed in with a session cookie (or the deploy's bearer token)
 *                  reads    -> Supabase Postgres through Hyperdrive
 *                  research -> the campaign's own Container (Python LangGraph swarm)
 *                  projects -> the project's agent (a Durable Object running Claude)
 *   cron (5 min) wakes the container of every unfinished campaign so a crashed or evicted
 *                run resumes from Postgres, and clears expired sessions and stuck agent turns
 */
import { Container } from "@cloudflare/containers";
import * as auth from "./auth";
import type { Ctx } from "./auth";
import * as campaigns from "./campaigns";
import { db, type Env, HttpError, json, TERMINAL_STATUSES, UUID_RE } from "./lib";
import * as projects from "./projects";

export { ProjectAgent } from "./agent";
export type { Env } from "./lib";

/** One container instance per campaign; it stays up while a campaign is running. */
export class ScientistContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "15m";
  enableInternet = true; // Anthropic API, Supabase, literature APIs, Crossref/doi.org checks, Modal
  pingEndpoint = "localhost/healthz";

  constructor(ctx: ConstructorParameters<typeof Container<Env>>[0], env: Env) {
    super(ctx, env);
    this.envVars = {
      PLATO_DATABASE_URL: env.PLATO_DATABASE_URL,
      PLATO_INTERNAL_TOKEN: env.PLATO_INTERNAL_TOKEN,
      ANTHROPIC_API_KEY: env.ANTHROPIC_API_KEY,
      PLATO_SCIENTIST_MODEL: env.PLATO_SCIENTIST_MODEL,
      PLATO_DB_POOL_SIZE: "8",
      // Experiments run in E2B sandboxes when a key is configured, on the container otherwise.
      PLATO_DEFAULT_EXECUTOR: env.E2B_API_KEY ? env.PLATO_DEFAULT_EXECUTOR || "e2b" : "local",
      ...(env.E2B_API_KEY
        ? { E2B_API_KEY: env.E2B_API_KEY, PLATO_E2B_TEMPLATE: env.PLATO_E2B_TEMPLATE || "plato-lab" }
        : {}),
    };
    // Optional secrets: set only when configured, so the container can tell "absent" apart.
    for (const key of ["ADS_API_KEY", "NCBI_API_KEY", "SEMANTIC_SCHOLAR_KEY", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"] as const) {
      const value = env[key];
      if (value) this.envVars[key] = value;
    }
  }

  /** Inactivity only means no HTTP traffic; keep running while a campaign is in flight. */
  override async onActivityExpired(): Promise<void> {
    if (!this.ctx.container?.running) return;
    try {
      const res = await this.containerFetch("http://localhost/healthz");
      const body = (await res.json()) as { active_runs?: number };
      if ((body.active_runs ?? 0) > 0) {
        this.renewActivityTimeout();
        return;
      }
    } catch (err) {
      console.error("healthz failed during activity check", err);
    }
    await this.stop();
  }
}

/** public: anyone; user: any signed-in caller; account: a person's account; admin: admins. */
type Access = "public" | "user" | "account" | "admin";
type Handler = (c: Ctx, id: string) => Promise<Response>;

const ROUTES: [string, string, Access, Handler][] = [
  ["POST", "auth/signup", "public", auth.signup],
  ["POST", "auth/login", "public", auth.login],
  ["POST", "auth/logout", "public", auth.logout],
  ["GET", "me", "public", auth.me],
  ["PATCH", "me", "account", auth.updateMe],
  ["DELETE", "me", "account", auth.deleteMe],
  ["POST", "me/password", "account", auth.changePassword],
  ["GET", "me/sessions", "account", auth.listSessions],
  ["DELETE", "me/sessions", "account", auth.revokeOtherSessions],
  ["PUT", "me/key", "account", auth.putKey],
  ["DELETE", "me/key", "account", auth.deleteKey],
  ["POST", "me/admin", "account", auth.claimAdmin],
  ["GET", "admin/accounts", "admin", auth.listAccounts],
  ["PATCH", "admin/accounts/:id", "admin", auth.updateAccount],
  ["GET", "health", "user", campaigns.health],
  ["GET", "campaigns", "user", campaigns.listCampaigns],
  ["POST", "campaigns", "user", campaigns.createCampaign],
  ["GET", "campaigns/:id", "user", campaigns.getCampaign],
  ["POST", "campaigns/:id/run", "user", campaigns.runCampaign],
  ["GET", "campaigns/:id/graph", "user", campaigns.campaignGraph],
  ["GET", "campaigns/:id/manuscript", "user", campaigns.campaignManuscript],
  ["GET", "campaigns/:id/usage", "user", campaigns.campaignUsage],
  ["GET", "campaigns/:id/draft", "user", campaigns.campaignDraft],
  ["GET", "nodes/:id/provenance", "user", campaigns.nodeProvenance],
  ["GET", "evidence/:id", "user", campaigns.evidence],
  ["GET", "projects", "account", projects.listProjects],
  ["POST", "projects", "account", projects.createProject],
  ["GET", "projects/:id", "account", projects.getProject],
  ["PATCH", "projects/:id", "account", projects.renameProject],
  ["DELETE", "projects/:id", "account", projects.deleteProject],
  ["POST", "projects/:id/messages", "account", projects.postMessage],
  ["POST", "projects/:id/retry", "account", projects.retryProject],
];

function match(path: string[], pattern: string): string | null | false {
  const pat = pattern.split("/");
  if (pat.length !== path.length) return false;
  let id: string | null = null;
  for (let i = 0; i < pat.length; i++) {
    if (pat[i] === ":id") {
      if (!UUID_RE.test(path[i])) return false;
      id = path[i];
    } else if (pat[i] !== path[i]) return false;
  }
  return id;
}

async function dispatch(c: Ctx): Promise<Response> {
  const path = c.url.pathname.replace(/\/+$/, "").split("/").slice(2); // drop "", "api"
  const allowed: string[] = [];
  for (const [method, pattern, access, handler] of ROUTES) {
    const id = match(path, pattern);
    if (id === false) continue;
    if (method !== c.req.method) {
      allowed.push(method);
      continue;
    }
    if (access !== "public") {
      c.who = await auth.authenticate(c);
      if (!c.who) throw new HttpError(401, "Sign in to continue.");
      if (access === "account" && !c.who.accountId) throw new HttpError(403, "This needs an account. Sign in with email.");
      if (access === "admin" && !c.who.isAdmin) throw new HttpError(403, "Only workspace admins can do this.");
    }
    return handler(c, id ?? "");
  }
  if (allowed.length) return json({ error: "method not allowed" }, 405, { allow: allowed.join(", ") });
  return json({ error: "not found" }, 404);
}

export default {
  async fetch(req, env, ctx): Promise<Response> {
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);
    // Browsers send Origin on cross-origin writes: refuse them (with the SameSite=Lax cookie
    // and JSON-only bodies, this closes cross-site request forgery).
    if (req.method !== "GET" && req.method !== "HEAD") {
      const origin = req.headers.get("origin");
      if (origin && origin !== url.origin) return json({ error: "cross-origin request refused" }, 403);
    }
    const sql = db(env);
    const c: Ctx = { req, env, ctx, url, sql, who: null, cookies: [] };
    let res: Response;
    try {
      res = await dispatch(c);
    } catch (err) {
      if (err instanceof HttpError) res = json({ error: err.message }, err.status);
      else {
        console.error("api error", url.pathname, err);
        res = json({ error: "internal error" }, 500);
      }
    } finally {
      // Close only after the queries ran; Hyperdrive keeps the pooled origin connection warm.
      ctx.waitUntil(sql.end({ timeout: 5 }).catch(() => undefined));
    }
    if (c.cookies.length) {
      res = new Response(res.body, res);
      for (const cookie of c.cookies) res.headers.append("set-cookie", cookie);
    }
    return res;
  },

  async scheduled(_controller, env, ctx): Promise<void> {
    const sql = db(env);
    try {
      const active = await sql`
        SELECT c.id, c.own_key, c.account_id, encode(k.ciphertext, 'hex') AS ct, encode(k.iv, 'hex') AS iv,
               k.key_version
          FROM plato.research_campaigns c
          LEFT JOIN plato.account_keys k ON c.own_key AND k.account_id = c.account_id
         WHERE NOT c.status = ANY(${TERMINAL_STATUSES}::text[]) ORDER BY c.created_at LIMIT 100`;
      // An own-key campaign resumes only with its owner's key; without it, it waits.
      const runnable = active.filter((r) => !r.own_key || r.ct);
      const results = await Promise.allSettled(
        runnable.map(async (r) => {
          const key = r.own_key
            ? await auth.decryptKey(env, r.account_id as string, r.ct as string, r.iv as string, Number(r.key_version))
            : null;
          const res = await campaigns.toContainer(env, r.id as string, `/internal/campaigns/${r.id}/run`, { method: "POST" }, key);
          if (!res.ok) throw new Error(`run ${r.id}: ${res.status}`);
        }),
      );
      const failed = results.filter((r) => r.status === "rejected").length;
      const [sessions, attempts, stuck] = await Promise.all([
        sql`DELETE FROM plato.sessions WHERE expires_at < now() RETURNING 1`,
        sql`DELETE FROM plato.auth_attempts WHERE created_at < now() - interval '1 day' RETURNING 1`,
        sql`UPDATE plato.projects SET agent_status = 'error',
                   agent_error = 'The agent stopped responding. Retry to continue.'
             WHERE agent_status = 'working' AND updated_at < now() - interval '20 minutes' RETURNING 1`,
      ]);
      console.log(
        JSON.stringify({
          event: "resume",
          active: active.length,
          waiting_for_key: active.length - runnable.length,
          failed,
          expired_sessions: sessions.length,
          old_attempts: attempts.length,
          stuck_agents: stuck.length,
        }),
      );
    } finally {
      ctx.waitUntil(sql.end({ timeout: 5 }));
    }
  },
} satisfies ExportedHandler<Env>;
