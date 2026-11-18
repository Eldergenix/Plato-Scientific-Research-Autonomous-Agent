/**
 * Campaigns (research threads): creation and runs go to the campaign's own Container;
 * reads come from Postgres through Hyperdrive. Every route checks that the caller may see
 * the campaign: its owner, or an admin. Campaigns from before accounts existed have no
 * owner and are visible to admins only. A hidden campaign answers 404, like a missing one.
 */
import { getContainer } from "@cloudflare/containers";
import { type Ctx, ownKey, type Principal } from "./auth";
import { type Env, HttpError, json, type Sql } from "./lib";

const MAX_CREATE_BYTES = 12 * 1024 * 1024; // 8 datasets of ~1 MiB, base64-encoded, plus slack

/** Who pays for a new campaign: the owner's own key if they saved one, else the default
 * key within their monthly allowance (``cap``; null when uncapped). */
export interface Payer {
  accountId: string | null;
  projectId: string | null;
  key: string | null;
  cap: number | null;
}

export async function payer(env: Env, sql: Sql, who: Principal, projectId: string | null = null): Promise<Payer> {
  const key = await ownKey(env, sql, who.accountId);
  return { accountId: who.accountId, projectId, key, cap: key || !who.accountId ? null : who.cap };
}

export function createPath(campaignId: string, p: Payer): string {
  const q = new URLSearchParams({ id: campaignId });
  if (p.accountId) q.set("account", p.accountId);
  if (p.projectId) q.set("project", p.projectId);
  if (p.key) q.set("own_key", "true");
  if (p.cap !== null && p.accountId) q.set("cap", String(p.cap));
  return `/internal/campaigns?${q}`;
}

/** Forward to the campaign's container. ``key`` is the owner's own Anthropic key, sent per
 * request so it is never stored in the container's environment. */
export async function toContainer(
  env: Env,
  campaignId: string,
  path: string,
  init: RequestInit = {},
  key: string | null = null,
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("x-plato-internal-token", env.PLATO_INTERNAL_TOKEN);
  if (key) headers.set("x-plato-anthropic-key", key);
  const res = env.PLATO_DEV_SERVICE_URL
    ? await fetch(env.PLATO_DEV_SERVICE_URL.replace(/\/$/, "") + path, { ...init, headers })
    : await getContainer(env.PLATO_SCIENTIST, `campaign-${campaignId}`).fetch(
        new Request(`http://container${path}`, { ...init, headers }),
      );
  return new Response(res.body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}

/** Turn a container error (FastAPI ``{"detail": ...}``) into the API's ``{"error": ...}``. */
export async function containerError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    const d = body.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0] && typeof d[0] === "object") {
      const e = d[0] as { loc?: unknown[]; msg?: string };
      return `${(e.loc ?? []).slice(1).join(".")}: ${e.msg ?? "invalid"}`;
    }
  } catch {
    /* not JSON */
  }
  return `request failed (${res.status})`;
}

/** The row of ``ownerQuery`` (which selects the owning ``account_id``) if the caller may see it. */
async function visible(c: Ctx, ownerQuery: PromiseLike<readonly Record<string, unknown>[]>) {
  const [row] = await ownerQuery;
  if (!row || (!c.who!.isAdmin && row.account_id !== c.who!.accountId)) throw new HttpError(404, "not found");
  return row;
}

const campaignOwner = (c: Ctx, id: string) =>
  visible(c, c.sql`SELECT account_id, own_key FROM plato.research_campaigns WHERE id = ${id}`);

export async function createCampaign(c: Ctx): Promise<Response> {
  const length = Number(c.req.headers.get("content-length") ?? NaN);
  if (!Number.isFinite(length)) throw new HttpError(411, "content-length required");
  if (length > MAX_CREATE_BYTES) throw new HttpError(413, "request too large");
  if (!(c.req.headers.get("content-type") ?? "").startsWith("application/json")) {
    throw new HttpError(415, "expected application/json");
  }
  let projectId = c.url.searchParams.get("project");
  if (projectId) {
    const [p] = await c.sql`SELECT 1 FROM plato.projects WHERE id = ${projectId} AND account_id = ${c.who!.accountId}`;
    if (!p) throw new HttpError(404, "project not found");
  } else projectId = null;
  // The Worker picks the id so it can address the container before the campaign exists.
  // The body streams through unparsed; the container validates it (FastAPI/Pydantic) and
  // checks the monthly allowance atomically with the insert.
  const campaignId = crypto.randomUUID();
  const p = await payer(c.env, c.sql, c.who!, projectId);
  const res = await toContainer(
    c.env,
    campaignId,
    createPath(campaignId, p),
    {
      method: "POST",
      headers: { "content-type": "application/json", "content-length": String(length) },
      body: c.req.body,
    },
    p.key,
  );
  if (!res.ok) throw new HttpError(res.status >= 500 ? 502 : res.status, await containerError(res));
  return res;
}

export async function runCampaign(c: Ctx, id: string): Promise<Response> {
  const row = await campaignOwner(c, id);
  // An own-key campaign runs only on its owner's key, never the default one.
  const key = row.own_key ? await ownKey(c.env, c.sql, row.account_id as string | null) : null;
  return toContainer(c.env, id, `/internal/campaigns/${id}/run`, { method: "POST" }, key);
}

export async function health(c: Ctx): Promise<Response> {
  const [row] = await c.sql`SELECT count(*)::int AS campaigns FROM plato.research_campaigns`;
  return json({ ok: true, model: c.env.PLATO_SCIENTIST_MODEL, campaigns: row.campaigns });
}

export async function listCampaigns(c: Ctx): Promise<Response> {
  const w = c.who!;
  const rows = await c.sql`
    SELECT c.id, c.research_question, c.status, c.halted_reason, c.tokens_used, c.token_budget_max,
           c.gpu_seconds_used, c.gpu_seconds_max, c.created_at, c.updated_at, c.project_id, c.own_key,
           p.slug AS program_slug
      FROM plato.research_campaigns c JOIN plato.research_programs p ON p.id = c.program_id
     WHERE ${w.isAdmin} OR c.account_id = ${w.accountId}
     ORDER BY c.created_at DESC LIMIT 100`;
  return json({ campaigns: rows });
}

export async function getCampaign(c: Ctx, id: string): Promise<Response> {
  await campaignOwner(c, id);
  const [[campaign], counts, guard] = await Promise.all([
    c.sql`SELECT c.*, p.slug AS program_slug, p.domain AS program_domain
            FROM plato.research_campaigns c JOIN plato.research_programs p ON p.id = c.program_id
           WHERE c.id = ${id}`,
    c.sql`SELECT node_type::text AS node_type, status::text AS status, count(*)::int AS n
            FROM plato.exploration_nodes WHERE campaign_id = ${id} GROUP BY 1, 2 ORDER BY 1, 2`,
    c.sql`SELECT kind, decision, detail, created_at FROM plato.guard_events
           WHERE campaign_id = ${id} ORDER BY created_at DESC LIMIT 50`,
  ]);
  return json({ campaign, node_counts: counts, guard_events: guard });
}

export async function campaignGraph(c: Ctx, id: string): Promise<Response> {
  await campaignOwner(c, id);
  const [nodes, edges] = await Promise.all([
    c.sql`SELECT id, node_type::text AS node_type, status::text AS status, title, hypothesis_or_spec,
                 metrics, priority, confidence_score, created_at, updated_at
            FROM plato.exploration_nodes WHERE campaign_id = ${id} ORDER BY created_at LIMIT 2000`,
    c.sql`SELECT source_node_id, target_node_id, edge_type::text AS edge_type, rationale
            FROM plato.exploration_edges WHERE campaign_id = ${id} LIMIT 5000`,
  ]);
  return json({ nodes, edges });
}

export async function manuscriptParts(sql: Sql, id: string) {
  return sql`
    SELECT DISTINCT ON (e.artifact_type) e.artifact_type, convert_from(e.content, 'UTF8') AS text, e.created_at
      FROM plato.evidence_artifacts e
      JOIN plato.exploration_nodes n ON n.id = e.node_id
     WHERE n.campaign_id = ${id} AND n.node_type = 'goal' AND n.dedup_key = 'root-goal'
       AND e.artifact_type IN ('latex_section', 'bibtex', 'peer_review', 'citation_report', 'evidence_matrix', 'review_panel')
       AND e.content IS NOT NULL
     ORDER BY e.artifact_type, e.created_at DESC`;
}

export async function campaignManuscript(c: Ctx, id: string): Promise<Response> {
  await campaignOwner(c, id);
  const rows = await manuscriptParts(c.sql, id);
  if (rows.length === 0) throw new HttpError(404, "manuscript not written yet");
  return json(Object.fromEntries(rows.map((r) => [r.artifact_type, r.text])));
}

export async function campaignUsage(c: Ctx, id: string): Promise<Response> {
  await campaignOwner(c, id);
  // Cumulative token and sandbox burn from the usage ledger, at most ~240 points: the
  // ledger is cut into equal-count buckets and each bucket's last running total is kept,
  // so the series stays monotone and ends exactly on the ledger's total.
  const points = await c.sql`
    WITH run AS (
      SELECT id, created_at,
             sum(tokens)      OVER w AS tokens,
             sum(gpu_seconds) OVER w AS gpu_seconds,
             ntile(240)       OVER (ORDER BY created_at, id) AS bucket
        FROM plato.usage_events WHERE campaign_id = ${id}
      WINDOW w AS (ORDER BY created_at, id ROWS UNBOUNDED PRECEDING)
    )
    SELECT DISTINCT ON (bucket) extract(epoch FROM created_at)::float8 AS t,
           tokens::float8 AS tokens, gpu_seconds::float8 AS gpu_seconds
      FROM run ORDER BY bucket, created_at DESC, id DESC`;
  return json({ points });
}

export async function campaignDraft(c: Ctx, id: string): Promise<Response> {
  await campaignOwner(c, id);
  // The paper while it is being written (streamed by the writer, throttled to ~1.5s).
  // Polled every 2s while writing, so "nothing yet" is a normal answer, not a 404.
  const [row] = await c.sql`
    SELECT stage, body, updated_at FROM plato.manuscript_drafts WHERE campaign_id = ${id}`;
  return json(row ?? { stage: null, body: "", updated_at: null });
}

export async function nodeProvenance(c: Ctx, id: string): Promise<Response> {
  await visible(
    c,
    c.sql`SELECT r.account_id FROM plato.exploration_nodes n
            JOIN plato.research_campaigns r ON r.id = n.campaign_id WHERE n.id = ${id}`,
  );
  // plato.lineage() is the same SQL function the Python store uses.
  const nodes = await c.sql`
    SELECT n.id, n.node_type::text AS node_type, n.status::text AS status, n.title, n.metrics,
           n.confidence_score, l.depth
      FROM plato.lineage(${id}::uuid, 32) l JOIN plato.exploration_nodes n ON n.id = l.node_id
     ORDER BY l.depth, n.created_at`;
  if (nodes.length === 0) throw new HttpError(404, "node not found");
  // Postgres array literal (fetch_types is off, so postgres.js cannot infer array types).
  const ids = `{${nodes.map((n) => n.id as string).join(",")}}`;
  const [edges, anchors, evidence] = await Promise.all([
    c.sql`SELECT source_node_id, target_node_id, edge_type::text AS edge_type FROM plato.exploration_edges
           WHERE source_node_id = ANY(${ids}::uuid[]) AND target_node_id = ANY(${ids}::uuid[])`,
    c.sql`SELECT x.node_id, x.anchor_role, a.id AS asset_id, a.asset_type::text AS asset_type,
                 a.canonical_name, a.uri_or_commit
            FROM plato.exploration_anchors x JOIN plato.knowledge_assets a ON a.id = x.asset_id
           WHERE x.node_id = ANY(${ids}::uuid[])`,
    c.sql`SELECT id, node_id, artifact_type, sha256_checksum, vlm_quality_score, approval_actor, created_at
            FROM plato.evidence_artifacts WHERE node_id = ANY(${ids}::uuid[]) ORDER BY created_at`,
  ]);
  return json({ root: id, nodes, edges, anchors, evidence });
}

const EVIDENCE_TYPES: Record<string, string> = {
  plot_png: "image/png",
  sealed_eval_json: "application/json",
  vlm_critique: "text/plain; charset=utf-8",
  peer_review: "text/plain; charset=utf-8",
  citation_report: "application/json",
  evidence_matrix: "application/json",
  review_panel: "application/json",
};

export async function evidence(c: Ctx, id: string): Promise<Response> {
  const row = await visible(
    c,
    c.sql`SELECT r.account_id, e.artifact_type, e.content, e.sha256_checksum
            FROM plato.evidence_artifacts e
            JOIN plato.exploration_nodes n ON n.id = e.node_id
            JOIN plato.research_campaigns r ON r.id = n.campaign_id
           WHERE e.id = ${id}`,
  );
  if (row.content === null) throw new HttpError(404, "evidence not found or stored externally");
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
