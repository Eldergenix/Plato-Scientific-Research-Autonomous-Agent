/**
 * Projects: a conversation with the project agent, plus the research threads it started.
 * Posting a message stores it and wakes the project's agent (a Durable Object); the UI
 * polls the project while the agent works. One turn at a time: a message posted while the
 * agent is working is refused with 409, unless the turn has been silent for 15 minutes.
 */
import { agentConfig } from "./agent";
import type { Ctx } from "./auth";
import { HttpError, json, readJson, TERMINAL_STATUSES, UUID_RE } from "./lib";

const MESSAGE_MAX = 8000;
const STALE = "15 minutes";

type Block = Record<string, unknown> & { type: string };

/** The person's message as content blocks: an optional <context> block naming the thread
 * they are looking at (only one they may see), then their text. */
async function personMessage(c: Ctx, body: Record<string, unknown>): Promise<Block[]> {
  const text = typeof body.text === "string" ? body.text.trim() : "";
  if (!text) throw new HttpError(400, "Write a message first.");
  if (text.length > MESSAGE_MAX) throw new HttpError(400, `Messages are limited to ${MESSAGE_MAX.toLocaleString()} characters.`);
  const blocks: Block[] = [];
  const ctx = body.context as { campaign_id?: unknown } | undefined;
  const cid = ctx && typeof ctx === "object" ? ctx.campaign_id : undefined;
  if (typeof cid === "string" && UUID_RE.test(cid)) {
    const [r] = await c.sql`
      SELECT id, account_id, research_question, status FROM plato.research_campaigns WHERE id = ${cid}`;
    if (r && (c.who!.isAdmin || r.account_id === c.who!.accountId)) {
      const q = String(r.research_question).replace(/\s+/g, " ").slice(0, 300);
      blocks.push({
        type: "text",
        text: `<context>The person is looking at research thread ${r.id} ("${q}"), status: ${r.status}.</context>`,
      });
    }
  }
  blocks.push({ type: "text", text });
  return blocks;
}

function titleFrom(text: string): string {
  const line = text.split("\n").find((l) => l.trim())?.trim() ?? "New project";
  if (line.length <= 80) return line;
  const cut = line.slice(0, 80);
  return cut.slice(0, Math.max(cut.lastIndexOf(" "), 40)).replace(/[\s,.;:–-]+$/, "") + "…";
}

/** Wake the project's agent. If that fails, the project shows an error with a retry. */
async function kick(c: Ctx, projectId: string): Promise<void> {
  try {
    await c.env.PROJECT_AGENT.get(c.env.PROJECT_AGENT.idFromName(projectId)).kick(projectId);
  } catch (err) {
    console.error("could not wake the project agent", projectId, err);
    await c.sql`UPDATE plato.projects SET agent_status = 'error',
                       agent_error = 'Could not start the agent. Retry to continue.'
                 WHERE id = ${projectId}`;
  }
}

export async function listProjects(c: Ctx): Promise<Response> {
  const rows = await c.sql`
    SELECT p.id, p.title, p.agent_status, p.created_at, p.updated_at,
           count(r.id)::int AS threads,
           count(r.id) FILTER (WHERE NOT r.status = ANY(${TERMINAL_STATUSES}::text[]))::int AS active
      FROM plato.projects p LEFT JOIN plato.research_campaigns r ON r.project_id = p.id
     WHERE p.account_id = ${c.who!.accountId}
     GROUP BY p.id ORDER BY p.updated_at DESC LIMIT 100`;
  return json({ projects: rows });
}

export async function createProject(c: Ctx): Promise<Response> {
  const body = await readJson(c.req, 32 * 1024);
  const blocks = await personMessage(c, body);
  const text = String(blocks.at(-1)!.text);
  const id = await c.sql.begin(async (tx) => {
    const [p] = await tx`
      INSERT INTO plato.projects (account_id, title, agent_status, agent_config)
      VALUES (${c.who!.accountId}, ${titleFrom(text)}, 'working', ${tx.json(agentConfig(c.env) as never)})
      RETURNING id`;
    await tx`INSERT INTO plato.project_messages (project_id, role, content)
             VALUES (${p.id}, 'user', ${tx.json(blocks as never)})`;
    return p.id as string;
  });
  await kick(c, id);
  return json({ id }, 201);
}

/** What the UI shows of a stored block: no thinking, and tool results trimmed. */
function view(b: Block): Block | null {
  if (b.type === "text") return { type: "text", text: b.text };
  if (b.type === "tool_use") return { type: "tool_use", id: b.id, name: b.name, input: b.input };
  if (b.type === "tool_result") {
    const content = typeof b.content === "string" ? b.content : JSON.stringify(b.content ?? "");
    return { type: "tool_result", tool_use_id: b.tool_use_id, content: content.slice(0, 2000), is_error: !!b.is_error };
  }
  return null;
}

export async function getProject(c: Ctx, id: string): Promise<Response> {
  const after = Number(c.url.searchParams.get("after") ?? 0);
  if (!Number.isSafeInteger(after) || after < 0) throw new HttpError(400, "after must be a message id");
  const [p] = await c.sql`
    SELECT id, title, agent_status, agent_error, created_at, updated_at,
           agent_status = 'working' AND updated_at < now() - ${STALE}::interval AS stale
      FROM plato.projects WHERE id = ${id} AND account_id = ${c.who!.accountId}`;
  if (!p) throw new HttpError(404, "project not found");
  const [messages, threads] = await Promise.all([
    c.sql`SELECT id, role, content, stop_reason, created_at FROM plato.project_messages
           WHERE project_id = ${id} AND id > ${after} ORDER BY id LIMIT 500`,
    c.sql`SELECT id, research_question, status, halted_reason, tokens_used, token_budget_max, created_at, updated_at
            FROM plato.research_campaigns WHERE project_id = ${id} ORDER BY created_at`,
  ]);
  const { stale, ...project } = p;
  if (stale) Object.assign(project, { agent_status: "error", agent_error: "The agent stopped responding. Retry to continue." });
  return json({
    project,
    messages: messages.map((m) => ({ ...m, content: (m.content as Block[]).map(view).filter(Boolean) })),
    threads,
  });
}

export async function postMessage(c: Ctx, id: string): Promise<Response> {
  const body = await readJson(c.req, 32 * 1024);
  const blocks = await personMessage(c, body);
  // Claim the turn and store the message in one statement.
  const rows = await c.sql`
    WITH p AS (
      UPDATE plato.projects SET agent_status = 'working', agent_error = NULL
       WHERE id = ${id} AND account_id = ${c.who!.accountId}
         AND (agent_status <> 'working' OR updated_at < now() - ${STALE}::interval)
      RETURNING id)
    INSERT INTO plato.project_messages (project_id, role, content)
    SELECT id, 'user', ${c.sql.json(blocks as never)} FROM p RETURNING id`;
  if (rows.length === 0) {
    const [p] = await c.sql`SELECT 1 FROM plato.projects WHERE id = ${id} AND account_id = ${c.who!.accountId}`;
    throw p ? new HttpError(409, "Plato is still working on your last message.") : new HttpError(404, "project not found");
  }
  await kick(c, id);
  return json({ id: rows[0].id }, 201);
}

export async function retryProject(c: Ctx, id: string): Promise<Response> {
  const rows = await c.sql`
    UPDATE plato.projects SET agent_status = 'working', agent_error = NULL
     WHERE id = ${id} AND account_id = ${c.who!.accountId}
       AND (agent_status = 'error' OR (agent_status = 'working' AND updated_at < now() - ${STALE}::interval))
    RETURNING id`;
  if (rows.length === 0) throw new HttpError(409, "There is nothing to retry.");
  await kick(c, id);
  return json({ ok: true });
}

export async function renameProject(c: Ctx, id: string): Promise<Response> {
  const body = await readJson(c.req);
  const title = typeof body.title === "string" ? body.title.trim() : "";
  if (!title || title.length > 200) throw new HttpError(400, "Titles are 1 to 200 characters.");
  const [row] = await c.sql`
    UPDATE plato.projects SET title = ${title} WHERE id = ${id} AND account_id = ${c.who!.accountId}
    RETURNING id, title`;
  if (!row) throw new HttpError(404, "project not found");
  return json(row);
}

export async function deleteProject(c: Ctx, id: string): Promise<Response> {
  // The conversation goes; its research threads keep running and stay in the campaign list.
  const rows = await c.sql`DELETE FROM plato.projects WHERE id = ${id} AND account_id = ${c.who!.accountId} RETURNING 1`;
  if (rows.length === 0) throw new HttpError(404, "project not found");
  return json({ ok: true });
}
