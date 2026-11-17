/**
 * The project agent: an orchestrator the person chats with, which starts research threads
 * (scientist campaigns) and reports on them.
 *
 * One Durable Object per project runs the agent's turns in alarm(), so a turn keeps going
 * after the HTTP request that started it returns, and an evicted turn is retried.
 * Postgres is the only state: each step reads the conversation, and the next action follows
 * from its last message. A user message (or tool results) means call the model; an assistant
 * message with tool calls means run them; anything else means the turn is over. So a retried
 * turn resumes where it stopped, and a tool call is never run twice (agent_actions caches
 * each result by tool_use_id, and a thread's id is derived from it).
 *
 * The conversation is replayed exactly as stored, and the model, system prompt and tools are
 * frozen per project, because editing any of them would invalidate the thinking blocks the
 * model gets back on later turns.
 */
import Anthropic from "@anthropic-ai/sdk";
import { DurableObject } from "cloudflare:workers";
import { ownKey } from "./auth";
import { containerError, createPath, manuscriptParts, toContainer } from "./campaigns";
import { db, type Env, monthlyCap, nameUuid, type Sql, TERMINAL_STATUSES, UUID_RE } from "./lib";

/** Model calls per person message; the last one must answer in text. */
const MAX_MODEL_CALLS = 8;
const MAX_TOKENS = 16_000;
const DEFAULT_THREAD_BUDGET = 1_000_000;

const SYSTEM = `You are Plato, the research orchestrator for a project in Plato, an autonomous scientist. You talk with one person about their project and do research for them by starting research threads.

A research thread is an autonomous scientist campaign that works on one research question on its own. It generates hypotheses, reads the literature, runs experiments in a sandbox, checks its results (replication, statistics and a skeptic's review) and writes a peer-reviewed paper. A thread takes minutes to hours and spends tokens from the person's budget, so each one should be worth running.

How to work:
- When the person describes research they want done, turn it into focused, testable research questions and start a thread for each right away. Ask a clarifying question first only if the request is too vague to turn into a testable question.
- Write each question so it stands on its own, because a thread cannot see this conversation: name what is measured, in what setting, and what result would answer it.
- Prefer one well-scoped thread to several overlapping ones. Start more than one only for independent questions, and at most four for one request.
- Use the default budget unless the person asks otherwise.
- After starting threads, say in a sentence or two what each will investigate. The person can follow their progress in the project.
- To answer questions about progress or results, check the threads with list_threads and get_thread, and report only what they return. Never invent results, numbers or citations.
- You cannot stop or change a thread once it is running.
- Keep replies short and concrete. Use Markdown sparingly: short paragraphs, bullet lists, and bold for key results.

A person's message may start with a <context> block saying what they are looking at in the app. Use it to resolve references such as "this thread".`;

const TOOLS: Anthropic.Tool[] = [
  {
    name: "start_research_thread",
    description:
      "Start an autonomous research thread (a scientist campaign) on one research question. It runs on its own for minutes to hours and spends tokens from the person's budget. Returns the new thread's id.",
    input_schema: {
      type: "object",
      properties: {
        question: {
          type: "string",
          description:
            "The research question, self-contained: what is measured, in what setting, and what result would answer it. 10 to 4000 characters.",
        },
        domain: {
          type: "string",
          description: "Research domain, such as statistics, machine-learning or biology. Default: general.",
        },
        token_budget: {
          type: "integer",
          description: `Token budget for the thread, 200000 to 10000000. Default ${DEFAULT_THREAD_BUDGET}.`,
        },
        max_rounds: { type: "integer", description: "Investigation rounds, 1 to 5. Default 2." },
        workers: { type: "integer", description: "Parallel experiment workers, 1 to 8. Default 4." },
      },
      required: ["question"],
      additionalProperties: false,
    },
  },
  {
    name: "list_threads",
    description:
      "List research threads with their status and token use: this project's threads, or all of the person's threads.",
    input_schema: {
      type: "object",
      properties: {
        scope: { type: "string", enum: ["project", "all"], description: "Default: project." },
      },
      additionalProperties: false,
    },
  },
  {
    name: "get_thread",
    description:
      "Get one research thread in detail: status, budget, progress counts, its strongest findings and, once written, the paper's title and abstract.",
    input_schema: {
      type: "object",
      properties: { thread_id: { type: "string", description: "The thread's id." } },
      required: ["thread_id"],
      additionalProperties: false,
    },
  },
];

export interface AgentConfig {
  model: string;
  system: string;
  tools: Anthropic.Tool[];
}

/** The configuration a new project is frozen with. */
export function agentConfig(env: Env): AgentConfig {
  return { model: env.PLATO_SCIENTIST_MODEL || "claude-haiku-5-5", system: SYSTEM, tools: TOOLS };
}

/** A failure the person can act on; its message is shown in the project. */
class AgentStop extends Error {}
/** A tool failure the model should see (and can recover from) as an error result. */
class ToolError extends Error {}

interface Actor {
  env: Env;
  sql: Sql;
  projectId: string;
  accountId: string;
  isAdmin: boolean;
  key: string | null;
  cap: number | null;
}

type Block = Record<string, unknown> & { type: string };

export class ProjectAgent extends DurableObject<Env> {
  /** Run (or resume) the project's agent turn. Called after a person's message is stored. */
  async kick(projectId: string): Promise<void> {
    if (!UUID_RE.test(projectId)) throw new Error("invalid project id");
    await this.ctx.storage.put("project", projectId);
    await this.ctx.storage.setAlarm(Date.now());
  }

  override async alarm(): Promise<void> {
    const projectId = await this.ctx.storage.get<string>("project");
    if (!projectId) return;
    const sql = db(this.env);
    try {
      await runTurn(this.env, sql, projectId);
    } finally {
      await sql.end({ timeout: 5 }).catch(() => undefined);
    }
  }
}

export async function runTurn(env: Env, sql: Sql, projectId: string): Promise<void> {
  const [p] = await sql`
    SELECT p.account_id, p.agent_status, p.agent_config, a.is_admin, a.monthly_token_cap
      FROM plato.projects p JOIN plato.accounts a ON a.id = p.account_id WHERE p.id = ${projectId}`;
  if (!p || p.agent_status !== "working") return;
  let usingOwnKey = false;
  try {
    let cfg = p.agent_config as AgentConfig;
    if (!cfg?.model) {
      cfg = agentConfig(env);
      await sql`UPDATE plato.projects SET agent_config = ${sql.json(cfg as never)} WHERE id = ${projectId}`;
    }
    const key = await ownKey(env, sql, p.account_id as string);
    usingOwnKey = key !== null;
    const actor: Actor = {
      env,
      sql,
      projectId,
      accountId: p.account_id as string,
      isAdmin: Boolean(p.is_admin),
      key,
      cap: p.is_admin || key ? null : monthlyCap(env, p.monthly_token_cap as number | null),
    };
    const client = new Anthropic({
      apiKey: key ?? env.ANTHROPIC_API_KEY,
      maxRetries: 3,
      timeout: 120_000,
      ...(env.PLATO_DEV_ANTHROPIC_BASE_URL ? { baseURL: env.PLATO_DEV_ANTHROPIC_BASE_URL } : {}),
    });
    await loop(actor, client, cfg);
    await sql`UPDATE plato.projects SET agent_status = 'idle', agent_error = NULL WHERE id = ${projectId}`;
  } catch (err) {
    const message = describe(err, usingOwnKey);
    if (!(err instanceof AgentStop)) console.error("agent turn failed", projectId, err);
    await sql`UPDATE plato.projects SET agent_status = 'error', agent_error = ${message.slice(0, 1000)}
               WHERE id = ${projectId}`;
  }
}

function describe(err: unknown, usingOwnKey: boolean): string {
  if (err instanceof AgentStop) return err.message;
  if (err instanceof Anthropic.AuthenticationError || err instanceof Anthropic.PermissionDeniedError) {
    return usingOwnKey
      ? "Anthropic rejected your API key. Update it in Settings, or remove it to use the shared key."
      : "Anthropic rejected the shared API key. An admin needs to update it.";
  }
  if (err instanceof Anthropic.RateLimitError) return "Anthropic is rate-limiting requests right now. Retry in a minute.";
  if (err instanceof Anthropic.APIConnectionError) return "Couldn't reach Anthropic. Retry in a moment.";
  if (err instanceof Anthropic.InternalServerError) return "Anthropic had a temporary error. Retry in a moment.";
  if (err instanceof Anthropic.APIError) return `The model request failed (${err.status ?? "error"}).`;
  return "Something went wrong while the agent was working. Retry to continue.";
}

async function loop(a: Actor, client: Anthropic, cfg: AgentConfig): Promise<void> {
  for (;;) {
    const rows = await a.sql`
      SELECT id, role, content, stop_reason FROM plato.project_messages
       WHERE project_id = ${a.projectId} ORDER BY id`;
    const last = rows.at(-1);
    if (!last) return;
    // Heartbeat: a turn that stops updating is treated as dead after 15 minutes.
    await a.sql`UPDATE plato.projects SET updated_at = now() WHERE id = ${a.projectId}`;

    if (last.role === "assistant") {
      const uses = (last.content as Block[]).filter((b) => b.type === "tool_use");
      if (uses.length === 0) return; // the turn ended with an answer
      const cutOff = last.stop_reason === "max_tokens" || last.stop_reason === "refusal";
      const results: Block[] = [];
      for (const use of uses) results.push(await runTool(a, use, cutOff));
      await a.sql`INSERT INTO plato.project_messages (project_id, role, content)
                  VALUES (${a.projectId}, 'user', ${a.sql.json(results as never)})`;
      continue;
    }

    // The model's turn. Count its calls since the person's last message, so the limit holds
    // across retries; the final call may not use tools, so the turn ends with an answer.
    let calls = 0;
    for (let i = rows.length - 1; i >= 0; i--) {
      const r = rows[i];
      if (r.role === "assistant") calls++;
      else if ((r.content as Block[]).some((b) => b.type === "text")) break;
    }
    if (calls > MAX_MODEL_CALLS) return;
    if (a.cap !== null) {
      const [u] = await a.sql`SELECT plato.account_committed_tokens(${a.accountId}::uuid, false) AS spent`;
      if (Number(u.spent) >= a.cap) {
        throw new AgentStop(
          "You've used this month's allowance on the shared key. Add your own Anthropic API key in Settings to keep going.",
        );
      }
    }
    const res = await client.messages.create({
      model: cfg.model,
      max_tokens: MAX_TOKENS,
      system: [{ type: "text", text: cfg.system, cache_control: { type: "ephemeral" } }],
      tools: cfg.tools,
      tool_choice: calls >= MAX_MODEL_CALLS ? { type: "none" } : { type: "auto" },
      messages: rows.map((r) => ({ role: r.role, content: r.content }) as Anthropic.MessageParam),
      output_config: { effort: "medium" },
      cache_control: { type: "ephemeral" },
    });
    const u = res.usage;
    const tokens =
      u.input_tokens + u.output_tokens + (u.cache_creation_input_tokens ?? 0) + (u.cache_read_input_tokens ?? 0);
    await a.sql.begin(async (tx) => {
      await tx`INSERT INTO plato.project_messages (project_id, role, content, stop_reason)
               VALUES (${a.projectId}, 'assistant', ${tx.json(res.content as never)}, ${res.stop_reason ?? null})`;
      if (tokens > 0) {
        await tx`INSERT INTO plato.agent_usage (account_id, project_id, tokens, own_key)
                 VALUES (${a.accountId}, ${a.projectId}, ${tokens}, ${a.key !== null})`;
      }
    });
  }
}

async function runTool(a: Actor, use: Block, cutOff: boolean): Promise<Block> {
  const id = String(use.id);
  const result = (content: string, isError = false): Block => ({
    type: "tool_result",
    tool_use_id: id,
    content,
    ...(isError ? { is_error: true } : {}),
  });
  if (cutOff) return result("Not run: the response was cut off before this call was complete. Try again.", true);
  const [cached] = await a.sql`SELECT result FROM plato.agent_actions WHERE tool_use_id = ${id}`;
  if (cached) return cached.result as Block;
  let out: Block;
  try {
    const input = (use.input ?? {}) as Record<string, unknown>;
    const fn = { start_research_thread: startThread, list_threads: listThreads, get_thread: getThread }[
      String(use.name)
    ];
    if (!fn) throw new ToolError(`Unknown tool: ${String(use.name)}`);
    out = result(JSON.stringify(await fn(a, input, id)).slice(0, 12_000));
  } catch (err) {
    if (!(err instanceof ToolError)) throw err; // transient: fail the turn, retry runs it again
    out = result(err.message, true);
  }
  await a.sql`INSERT INTO plato.agent_actions (tool_use_id, project_id, result)
              VALUES (${id}, ${a.projectId}, ${a.sql.json(out as never)}) ON CONFLICT DO NOTHING`;
  return out;
}

function int(v: unknown, name: string, min: number, max: number, dflt: number): number {
  if (v === undefined || v === null) return dflt;
  if (typeof v !== "number" || !Number.isInteger(v) || v < min || v > max) {
    throw new ToolError(`${name} must be a whole number from ${min} to ${max}.`);
  }
  return v;
}

async function startThread(a: Actor, input: Record<string, unknown>, toolUseId: string) {
  const question = typeof input.question === "string" ? input.question.trim() : "";
  if (question.length < 10 || question.length > 4000) throw new ToolError("question must be 10 to 4000 characters.");
  const domain = typeof input.domain === "string" && input.domain.trim() ? input.domain.trim().slice(0, 64) : "general";
  const body = {
    question,
    domain,
    token_budget: int(input.token_budget, "token_budget", 200_000, 10_000_000, DEFAULT_THREAD_BUDGET),
    max_rounds: int(input.max_rounds, "max_rounds", 1, 5, 2),
    workers: int(input.workers, "workers", 1, 8, 4),
  };
  // Derived from the tool call, so a retried call addresses the same campaign (the
  // container's create is idempotent for a given id).
  const threadId = await nameUuid(`plato.agent:${a.projectId}:${toolUseId}`);
  const res = await toContainer(
    a.env,
    threadId,
    createPath(threadId, { accountId: a.accountId, projectId: a.projectId, key: a.key, cap: a.cap }),
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) },
    a.key,
  );
  if (res.status >= 400 && res.status < 500) throw new ToolError(await containerError(res));
  if (!res.ok) throw new Error(`container create failed: ${res.status} ${await containerError(res)}`);
  return { thread_id: threadId, status: "started", question, token_budget: body.token_budget };
}

async function listThreads(a: Actor, input: Record<string, unknown>) {
  const all = input.scope === "all";
  const rows = await a.sql`
    SELECT id AS thread_id, research_question AS question, status, halted_reason,
           tokens_used, token_budget_max AS token_budget, created_at, updated_at
      FROM plato.research_campaigns
     WHERE CASE WHEN ${all} THEN account_id = ${a.accountId} ELSE project_id = ${a.projectId} END
     ORDER BY created_at DESC LIMIT 40`;
  return { threads: rows };
}

async function getThread(a: Actor, input: Record<string, unknown>) {
  const id = typeof input.thread_id === "string" ? input.thread_id.trim().toLowerCase() : "";
  if (!UUID_RE.test(id)) throw new ToolError("thread_id must be a thread's id (a UUID).");
  const [c] = await a.sql`
    SELECT id, account_id, research_question, status, halted_reason, tokens_used, token_budget_max,
           created_at, updated_at, NOT (status = ANY(${TERMINAL_STATUSES}::text[])) AS active
      FROM plato.research_campaigns WHERE id = ${id}`;
  if (!c || (c.account_id !== a.accountId && !a.isAdmin)) throw new ToolError("No thread with that id.");
  const [counts, top, paper] = await Promise.all([
    a.sql`SELECT node_type::text AS type, status::text AS status, count(*)::int AS n
            FROM plato.exploration_nodes WHERE campaign_id = ${id} GROUP BY 1, 2 ORDER BY 1, 2`,
    a.sql`SELECT node_type::text AS type, status::text AS status, title, confidence_score
            FROM plato.exploration_nodes
           WHERE campaign_id = ${id} AND node_type IN ('finding', 'fact')
           ORDER BY (status = 'verified') DESC, confidence_score DESC NULLS LAST, created_at DESC LIMIT 12`,
    c.status === "completed" ? manuscriptParts(a.sql, id) : Promise.resolve([]),
  ]);
  const tex = (paper.find((r) => r.artifact_type === "latex_section")?.text as string | undefined) ?? "";
  const title = /\\title\{([^}]*)\}/.exec(tex)?.[1];
  const abstract = /\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}/.exec(tex)?.[1]?.trim().slice(0, 3000);
  return {
    thread_id: c.id,
    question: c.research_question,
    status: c.status,
    halted_reason: c.halted_reason,
    tokens_used: c.tokens_used,
    token_budget: c.token_budget_max,
    started: c.created_at,
    last_update: c.updated_at,
    progress: counts,
    strongest_results: top,
    ...(title || abstract ? { paper: { title, abstract } } : {}),
  };
}
