/**
 * Plato autonomous scientist: Cloudflare edge for https://jarvisos.xyz
 *
 *   /            static UI (Workers Static Assets)
 *   /api/*       bearer-authenticated JSON API
 *                  reads  -> Supabase Postgres through Hyperdrive (pooled, low latency)
 *                  writes -> the campaign's own Container (Python LangGraph swarm)
 *   cron (5 min) wakes the container of every unfinished campaign so a crashed or
 *                evicted run resumes from the state persisted in Postgres
 */
import { Container, getContainer } from "@cloudflare/containers";
import postgres from "postgres";

export interface Env {
  ASSETS: Fetcher;
  HYPERDRIVE: Hyperdrive;
  PLATO_SCIENTIST: DurableObjectNamespace<ScientistContainer>;
  PLATO_SCIENTIST_MODEL: string;
  PLATO_API_TOKEN: string;
  PLATO_INTERNAL_TOKEN: string;
  ANTHROPIC_API_KEY: string;
  PLATO_DATABASE_URL: string;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const MAX_CREATE_BYTES = 12 * 1024 * 1024; // 8 datasets of ~1 MiB, base64-encoded, plus slack
// Postgres array literal: postgres.js cannot infer array parameter types with fetch_types off.
const TERMINAL_STATUSES = "{completed,halted}";

/** One container instance per campaign; it stays up while a campaign is running. */
export class ScientistContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "15m";
  enableInternet = true; // Anthropic API, Supabase, arXiv/OpenAlex
  pingEndpoint = "localhost/healthz";

  constructor(ctx: ConstructorParameters<typeof Container<Env>>[0], env: Env) {
    super(ctx, env);
    this.envVars = {
      PLATO_DATABASE_URL: env.PLATO_DATABASE_URL,
      PLATO_INTERNAL_TOKEN: env.PLATO_INTERNAL_TOKEN,
      ANTHROPIC_API_KEY: env.ANTHROPIC_API_KEY,
      PLATO_SCIENTIST_MODEL: env.PLATO_SCIENTIST_MODEL,
      PLATO_DB_POOL_SIZE: "8",
    };
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

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data, (_k, v) => (typeof v === "bigint" ? Number(v) : v)), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

async function sha256(text: string): Promise<ArrayBuffer> {
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
}

/** Constant-time bearer check (digests first, so length is not leaked either). */
async function authorized(req: Request, env: Env): Promise<boolean> {
  if (!env.PLATO_API_TOKEN) return false;
  const header = req.headers.get("authorization") ?? "";
  const presented = header.startsWith("Bearer ") ? header.slice(7) : "";
  const [a, b] = await Promise.all([sha256(presented), sha256(env.PLATO_API_TOKEN)]);
  return crypto.subtle.timingSafeEqual(a, b);
}

function db(env: Env) {
  return postgres(env.HYPERDRIVE.connectionString, {
    max: 5,
    fetch_types: false, // no extra round trip for type metadata
    prepare: true, // Hyperdrive supports prepared statements and caches them
    idle_timeout: 5,
    types: { bigint: postgres.BigInt }, // int8 -> BigInt -> JSON number (not a string)
  });
}

function campaignStub(env: Env, campaignId: string) {
  return getContainer(env.PLATO_SCIENTIST, `campaign-${campaignId}`);
}

async function toContainer(env: Env, campaignId: string, path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("x-plato-internal-token", env.PLATO_INTERNAL_TOKEN);
  const res = await campaignStub(env, campaignId).fetch(new Request(`http://container${path}`, { ...init, headers }));
  return new Response(res.body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}

const EVIDENCE_TYPES: Record<string, string> = {
  plot_png: "image/png",
  sealed_eval_json: "application/json",
  vlm_critique: "text/plain; charset=utf-8",
  peer_review: "text/plain; charset=utf-8",
};

async function api(req: Request, env: Env, ctx: ExecutionContext, url: URL): Promise<Response> {
  const parts = url.pathname.replace(/\/+$/, "").split("/").slice(2); // drop "", "api"
  const method = req.method;
  const id = parts[1];
  if (id !== undefined && !UUID_RE.test(id)) return json({ error: "invalid id" }, 400);

  // Writes go to the campaign's container.
  if (method === "POST" && parts[0] === "campaigns" && parts.length === 1) {
    const length = Number(req.headers.get("content-length") ?? NaN);
    if (!Number.isFinite(length)) return json({ error: "content-length required" }, 411);
    if (length > MAX_CREATE_BYTES) return json({ error: "request too large" }, 413);
    // The Worker picks the id so it can address the container before the campaign exists.
    // The body streams through unparsed; the container validates it (FastAPI/Pydantic).
    const campaignId = crypto.randomUUID();
    return toContainer(env, campaignId, `/internal/campaigns?id=${campaignId}`, {
      method: "POST",
      headers: { "content-type": "application/json", "content-length": String(length) },
      body: req.body,
    });
  }
  if (method === "POST" && parts[0] === "campaigns" && parts[2] === "run" && parts.length === 3) {
    return toContainer(env, id!, `/internal/campaigns/${id}/run`, { method: "POST" });
  }
  if (method !== "GET") return json({ error: "method not allowed" }, 405);

  const sql = db(env);
  try {
    return await read(sql, env, parts, id);
  } finally {
    // Close only after the queries ran; Hyperdrive keeps the pooled origin connection warm.
    ctx.waitUntil(sql.end({ timeout: 5 }).catch(() => undefined));
  }
}

async function read(sql: ReturnType<typeof db>, env: Env, parts: string[], id: string | undefined): Promise<Response> {
  if (parts[0] === "health" && parts.length === 1) {
    const [row] = await sql`SELECT count(*)::int AS campaigns FROM plato.research_campaigns`;
    return json({ ok: true, model: env.PLATO_SCIENTIST_MODEL, campaigns: row.campaigns });
  }

  if (parts[0] === "campaigns" && parts.length === 1) {
    const rows = await sql`
      SELECT c.id, c.research_question, c.status, c.halted_reason, c.tokens_used, c.token_budget_max,
             c.gpu_seconds_used, c.gpu_seconds_max, c.created_at, c.updated_at, p.slug AS program_slug
        FROM plato.research_campaigns c JOIN plato.research_programs p ON p.id = c.program_id
       ORDER BY c.created_at DESC LIMIT 100`;
    return json({ campaigns: rows });
  }

  if (parts[0] === "campaigns" && parts.length === 2) {
    const [[campaign], counts, guard] = await Promise.all([
      sql`SELECT c.*, p.slug AS program_slug, p.domain AS program_domain
            FROM plato.research_campaigns c JOIN plato.research_programs p ON p.id = c.program_id
           WHERE c.id = ${id!}`,
      sql`SELECT node_type::text AS node_type, status::text AS status, count(*)::int AS n
            FROM plato.exploration_nodes WHERE campaign_id = ${id!} GROUP BY 1, 2 ORDER BY 1, 2`,
      sql`SELECT kind, decision, detail, created_at FROM plato.guard_events
           WHERE campaign_id = ${id!} ORDER BY created_at DESC LIMIT 50`,
    ]);
    if (!campaign) return json({ error: "campaign not found" }, 404);
    return json({ campaign, node_counts: counts, guard_events: guard });
  }

  if (parts[0] === "campaigns" && parts[2] === "graph" && parts.length === 3) {
    const [nodes, edges] = await Promise.all([
      sql`SELECT id, node_type::text AS node_type, status::text AS status, title, hypothesis_or_spec,
                 metrics, priority, confidence_score, created_at
            FROM plato.exploration_nodes WHERE campaign_id = ${id!} ORDER BY created_at LIMIT 2000`,
      sql`SELECT source_node_id, target_node_id, edge_type::text AS edge_type, rationale
            FROM plato.exploration_edges WHERE campaign_id = ${id!} LIMIT 5000`,
    ]);
    return json({ nodes, edges });
  }

  if (parts[0] === "campaigns" && parts[2] === "manuscript" && parts.length === 3) {
    const rows = await sql`
      SELECT DISTINCT ON (e.artifact_type) e.artifact_type, convert_from(e.content, 'UTF8') AS text, e.created_at
        FROM plato.evidence_artifacts e
        JOIN plato.exploration_nodes n ON n.id = e.node_id
       WHERE n.campaign_id = ${id!} AND n.node_type = 'goal' AND n.dedup_key = 'root-goal'
         AND e.artifact_type IN ('latex_section', 'bibtex', 'peer_review') AND e.content IS NOT NULL
       ORDER BY e.artifact_type, e.created_at DESC`;
    if (rows.length === 0) return json({ error: "manuscript not written yet" }, 404);
    return json(Object.fromEntries(rows.map((r) => [r.artifact_type, r.text])));
  }

  if (parts[0] === "nodes" && parts[2] === "provenance" && parts.length === 3) {
    // plato.lineage() is the same SQL function the Python store uses.
    const nodes = await sql`
      SELECT n.id, n.node_type::text AS node_type, n.status::text AS status, n.title, n.metrics,
             n.confidence_score, l.depth
        FROM plato.lineage(${id!}::uuid, 32) l JOIN plato.exploration_nodes n ON n.id = l.node_id
       ORDER BY l.depth, n.created_at`;
    if (nodes.length === 0) return json({ error: "node not found" }, 404);
    // Postgres array literal (fetch_types is off, so postgres.js cannot infer array types).
    const ids = `{${nodes.map((n) => n.id as string).join(",")}}`;
    const [edges, anchors, evidence] = await Promise.all([
      sql`SELECT source_node_id, target_node_id, edge_type::text AS edge_type FROM plato.exploration_edges
           WHERE source_node_id = ANY(${ids}::uuid[]) AND target_node_id = ANY(${ids}::uuid[])`,
      sql`SELECT x.node_id, x.anchor_role, a.id AS asset_id, a.asset_type::text AS asset_type,
                 a.canonical_name, a.uri_or_commit
            FROM plato.exploration_anchors x JOIN plato.knowledge_assets a ON a.id = x.asset_id
           WHERE x.node_id = ANY(${ids}::uuid[])`,
      sql`SELECT id, node_id, artifact_type, sha256_checksum, vlm_quality_score, approval_actor, created_at
            FROM plato.evidence_artifacts WHERE node_id = ANY(${ids}::uuid[]) ORDER BY created_at`,
    ]);
    return json({ root: id, nodes, edges, anchors, evidence });
  }

  if (parts[0] === "evidence" && parts.length === 2) {
    const [row] = await sql`
      SELECT artifact_type, content, sha256_checksum FROM plato.evidence_artifacts WHERE id = ${id!}`;
    if (!row || row.content === null) return json({ error: "evidence not found or stored externally" }, 404);
    return new Response(row.content as Uint8Array, {
      headers: {
        "content-type": EVIDENCE_TYPES[row.artifact_type as string] ?? "text/plain; charset=utf-8",
        // Evidence is model- or experiment-generated: never let it run as active content.
        "content-security-policy": "default-src 'none'; img-src 'self'; sandbox",
        "x-content-type-options": "nosniff",
        etag: `"${row.sha256_checksum}"`,
        "cache-control": "private, max-age=31536000, immutable", // content is immutable by trigger
      },
    });
  }

  return json({ error: "not found" }, 404);
}

export default {
  async fetch(req, env, ctx): Promise<Response> {
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);
    if (!(await authorized(req, env))) {
      return json({ error: "unauthorized" }, 401);
    }
    try {
      return await api(req, env, ctx, url);
    } catch (err) {
      console.error("api error", url.pathname, err);
      return json({ error: "internal error" }, 500);
    }
  },

  async scheduled(_controller, env, ctx): Promise<void> {
    const sql = db(env);
    try {
      const active = await sql`
        SELECT id FROM plato.research_campaigns
         WHERE NOT status = ANY(${TERMINAL_STATUSES}::text[]) ORDER BY created_at LIMIT 100`;
      const results = await Promise.allSettled(
        active.map((r) => toContainer(env, r.id as string, `/internal/campaigns/${r.id}/run`, { method: "POST" })),
      );
      const failed = results.filter((r) => r.status === "rejected" || !r.value.ok).length;
      console.log(JSON.stringify({ event: "resume", active: active.length, failed }));
    } finally {
      ctx.waitUntil(sql.end({ timeout: 5 }));
    }
  },
} satisfies ExportedHandler<Env>;
