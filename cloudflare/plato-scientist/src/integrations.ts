/**
 * Connected services through Composio: Google Drive, Dropbox, OneDrive (browse, import
 * into the library, receive packages) and Gmail, Outlook (send packages; Gmail attachments
 * and new Drive files arrive by trigger).
 *
 * Triggers deliver to /api/integrations/webhook. Each delivery is verified (HMAC with the
 * subscription secret, 5-minute window), stored once by its webhook-id, and imported right
 * away; anything that fails is retried by the cron, at most 5 times.
 */
import type { Ctx } from "./auth";
import * as composio from "./composio";
import { db, type Env, HttpError, json, readJson, type Sql, UUID_RE } from "./lib";
import * as library from "./library";

const MAX_IMPORT = 20;
const MAX_ATTEMPTS = 5;

const TRIGGERS: Partial<Record<composio.Toolkit, { slug: string; label: string }>> = {
  googledrive: { slug: "GOOGLEDRIVE_FILE_CREATED_TRIGGER", label: "New files in a Drive folder" },
  gmail: { slug: "GMAIL_NEW_GMAIL_MESSAGE", label: "Attachments of new emails" },
};

/* ---------- connections ---------- */

export async function listIntegrations(c: Ctx): Promise<Response> {
  const configured = Boolean(c.env.COMPOSIO_API_KEY);
  const conns = configured ? await composio.connections(c.env, c.who!.accountId!) : [];
  const triggers = await c.sql`
    SELECT id, toolkit, trigger_slug, label, config, created_at FROM plato.integration_triggers
     WHERE account_id = ${c.who!.accountId} ORDER BY created_at`;
  const services = Object.entries(composio.TOOLKITS).map(([slug, t]) => {
    const mine = conns.filter((x) => x.toolkit === slug);
    const active = mine.find((x) => x.status === "ACTIVE");
    return {
      slug,
      name: t.name,
      files: t.files,
      email: t.email,
      status: active ? "connected" : mine.find((x) => x.status === "EXPIRED") ? "expired" : mine.length ? "pending" : "disconnected",
      trigger: TRIGGERS[slug as composio.Toolkit] ?? null,
    };
  });
  return json({ configured, services, triggers });
}

export async function connect(c: Ctx, _id: string): Promise<Response> {
  const body = await readJson(c.req);
  const tk = composio.toolkit(String(body.service ?? ""));
  // The app routes by hash; the settings page re-reads the connection status when it opens.
  const callback = `${c.url.origin}/#/settings/integrations`;
  const link = await composio.connectLink(c.env, c.sql, c.who!.accountId!, tk, callback);
  return json({ redirect_url: link.redirect_url });
}

export async function disconnect(c: Ctx): Promise<Response> {
  const body = await readJson(c.req);
  const tk = composio.toolkit(String(body.service ?? ""));
  const account = c.who!.accountId!;
  const triggers = await c.sql`
    SELECT id, trigger_id FROM plato.integration_triggers WHERE account_id = ${account} AND toolkit = ${tk}`;
  for (const t of triggers) await composio.deleteTrigger(c.env, t.trigger_id as string);
  await c.sql`DELETE FROM plato.integration_triggers WHERE account_id = ${account} AND toolkit = ${tk}`;
  for (const conn of (await composio.connections(c.env, account)).filter((x) => x.toolkit === tk)) {
    await composio.disconnect(c.env, conn.id);
  }
  return json({ disconnected: tk });
}

/* ---------- browse and import ---------- */

interface Item {
  id: string;
  name: string;
  folder: boolean;
  size: number | null;
  mime: string | null;
  path?: string;
  modified?: string | null;
}

const GOOGLE_EXPORTS: Record<string, [string, string]> = {
  "application/vnd.google-apps.document": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"],
  "application/vnd.google-apps.spreadsheet": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"],
  "application/vnd.google-apps.presentation": ["application/pdf", ".pdf"],
};

export async function browse(c: Ctx): Promise<Response> {
  const tk = composio.toolkit(c.url.searchParams.get("service") ?? "");
  const folder = c.url.searchParams.get("folder") ?? "";
  const cursor = c.url.searchParams.get("cursor") ?? "";
  const q = (c.url.searchParams.get("q") ?? "").slice(0, 100);
  const account = c.who!.accountId!;
  let items: Item[] = [];
  let next: string | null = null;
  if (tk === "googledrive") {
    const parts = ["trashed = false"];
    if (q) parts.push(`name contains '${q.replace(/['\\]/g, "")}'`);
    else parts.push(`'${(folder || "root").replace(/['\\]/g, "")}' in parents`);
    const d = await composio.execute(c.env, account, "GOOGLEDRIVE_LIST_FILES", {
      q: parts.join(" and "),
      pageSize: 100,
      orderBy: "folder,name",
      fields: "nextPageToken,files(id,name,mimeType,size,modifiedTime)",
      ...(cursor ? { pageToken: cursor } : {}),
    });
    items = ((d.files as Record<string, unknown>[]) ?? []).map((f) => ({
      id: String(f.id),
      name: String(f.name),
      folder: f.mimeType === "application/vnd.google-apps.folder",
      size: f.size ? Number(f.size) : null,
      mime: (f.mimeType as string) ?? null,
      modified: (f.modifiedTime as string) ?? null,
    }));
    next = (d.nextPageToken as string) || null;
  } else if (tk === "dropbox") {
    const d = await composio.execute(c.env, account, "DROPBOX_LIST_FILES_IN_FOLDER", { path: folder, limit: 200 });
    items = ((d.entries as Record<string, unknown>[]) ?? []).map((e) => ({
      id: String(e.id ?? e.path_lower),
      name: String(e.name),
      folder: e[".tag"] === "folder",
      size: typeof e.size === "number" ? e.size : null,
      mime: null,
      path: String(e.path_display ?? e.path_lower ?? ""),
      modified: (e.server_modified as string) ?? null,
    }));
  } else if (tk === "one_drive") {
    const d = await composio.execute(
      c.env,
      account,
      q ? "ONE_DRIVE_SEARCH_ITEMS" : "ONE_DRIVE_ONEDRIVE_LIST_ITEMS",
      q ? { q } : { top: 200 },
    );
    items = ((d.value as Record<string, unknown>[]) ?? []).map((e) => ({
      id: String(e.id),
      name: String(e.name),
      folder: Boolean(e.folder),
      size: typeof e.size === "number" ? e.size : null,
      mime: ((e.file as { mimeType?: string } | undefined)?.mimeType as string) ?? null,
      modified: (e.lastModifiedDateTime as string) ?? null,
    }));
  } else throw new HttpError(400, "this service has no files to browse");
  return json({
    service: tk,
    items: items.map((i) => ({ ...i, kind: i.folder ? "folder" : library.kindOf(i.name) })),
    next,
  });
}

/** Fetch one file from a service and keep it in the library (once per external file). */
async function importOne(env: Env, sql: Sql, account: string, tk: composio.Toolkit, item: Partial<Item>) {
  let name = library.safeName(String(item.name ?? "file"));
  let data: Uint8Array | null = null;
  let mime: string | null = item.mime ?? null;
  if (tk === "googledrive") {
    const exp = mime ? GOOGLE_EXPORTS[mime] : undefined;
    if (mime?.startsWith("application/vnd.google-apps.") && !exp) throw new HttpError(422, `${name}: this Google file type cannot be exported`);
    const d = await composio.execute(env, account, "GOOGLEDRIVE_DOWNLOAD_FILE", {
      file_id: item.id,
      ...(exp ? { mime_type: exp[0] } : {}),
    });
    if (exp && !name.toLowerCase().endsWith(exp[1])) name += exp[1];
    const ref = d.downloaded_file_content as composio.FileRef;
    data = await composio.fetchFile(ref, library.MAX_FILE_BYTES);
    mime = exp ? exp[0] : ref.mimetype;
  } else if (tk === "dropbox") {
    const d = await composio.execute(env, account, "DROPBOX_READ_FILE", { path: item.path || item.id });
    const v = d.file_content_bytes as unknown;
    data =
      v && typeof v === "object" && "s3url" in (v as object)
        ? await composio.fetchFile(v as composio.FileRef, library.MAX_FILE_BYTES)
        : composio.inlineBytes(v, Number((d.metadata as { size?: number } | undefined)?.size ?? NaN));
  } else if (tk === "one_drive") {
    const d = await composio.execute(env, account, "ONE_DRIVE_DOWNLOAD_FILE", { item_id: item.id, file_name: name });
    const ref = d.content as composio.FileRef;
    data = await composio.fetchFile(ref, library.MAX_FILE_BYTES);
    mime = ref.mimetype;
  }
  if (!data) throw new HttpError(502, `${name}: the service returned no content`);
  return library.store(env, sql, account, name, data, tk as library.Source, {
    sourceRef: `${tk}:${item.id ?? item.path}`,
    mediaType: mime,
  });
}

export async function importFiles(c: Ctx): Promise<Response> {
  const body = await readJson(c.req);
  const tk = composio.toolkit(String(body.service ?? ""));
  const files = Array.isArray(body.files) ? (body.files as Partial<Item>[]) : [];
  if (!files.length || files.length > MAX_IMPORT) throw new HttpError(400, `pick 1 to ${MAX_IMPORT} files`);
  const results = [];
  for (const f of files) {
    if (typeof f?.id !== "string" || typeof f?.name !== "string" || f.folder) {
      results.push({ name: String(f?.name ?? "?"), error: "not a file" });
      continue;
    }
    try {
      results.push(await importOne(c.env, c.sql, c.who!.accountId!, tk, f));
    } catch (err) {
      if (!(err instanceof HttpError)) throw err;
      results.push({ name: f.name, error: err.message });
    }
  }
  return json({ results });
}

/* ---------- triggers ---------- */

export async function createTrigger(c: Ctx): Promise<Response> {
  const body = await readJson(c.req);
  const tk = composio.toolkit(String(body.service ?? ""));
  const spec = TRIGGERS[tk];
  if (!spec) throw new HttpError(400, "this service has no automatic import");
  let config: Record<string, unknown>;
  let label: string;
  if (tk === "googledrive") {
    const folder = typeof body.folder_id === "string" ? body.folder_id.trim() : "";
    if (!/^[A-Za-z0-9_-]{5,200}$/.test(folder)) throw new HttpError(400, "pick a Drive folder to watch");
    config = { folder_id: folder };
    label = `Drive folder ${typeof body.folder_name === "string" ? body.folder_name.slice(0, 100) : folder}`;
  } else {
    const query = typeof body.query === "string" && body.query.trim() ? body.query.trim().slice(0, 200) : "has:attachment";
    config = { query: query.includes("has:attachment") ? query : `${query} has:attachment` };
    label = `Gmail: ${config.query}`;
  }
  const triggerId = await composio.upsertTrigger(c.env, c.who!.accountId!, spec.slug, config);
  const [row] = await c.sql`
    INSERT INTO plato.integration_triggers (account_id, toolkit, trigger_slug, trigger_id, label, config)
    VALUES (${c.who!.accountId}, ${tk}, ${spec.slug}, ${triggerId}, ${label}, ${c.sql.json(config as never)})
    ON CONFLICT (trigger_id) DO UPDATE SET label = EXCLUDED.label, config = EXCLUDED.config
    RETURNING id, toolkit, trigger_slug, label, config, created_at`;
  return json({ trigger: row }, 201);
}

export async function deleteTrigger(c: Ctx, id: string): Promise<Response> {
  const [row] = await c.sql`
    SELECT trigger_id FROM plato.integration_triggers WHERE id = ${id} AND account_id = ${c.who!.accountId}`;
  if (!row) throw new HttpError(404, "not found");
  await composio.deleteTrigger(c.env, row.trigger_id as string);
  await c.sql`DELETE FROM plato.integration_triggers WHERE id = ${id}`;
  return json({ deleted: id });
}

/* ---------- webhook ---------- */

interface Delivery {
  id?: string;
  type?: string;
  metadata?: { trigger_slug?: string; trigger_id?: string; user_id?: string; connected_account_id?: string };
  data?: Record<string, unknown>;
}

/** Public endpoint for Composio. Unsigned or stale deliveries are refused. */
export async function webhook(c: Ctx): Promise<Response> {
  const secret = c.env.COMPOSIO_WEBHOOK_SECRET;
  if (!secret) throw new HttpError(503, "webhooks are not configured");
  const raw = await c.req.text();
  if (raw.length > 1024 * 1024) throw new HttpError(413, "too large");
  if (!(await composio.verifyWebhook(secret, c.req.headers, raw))) throw new HttpError(401, "invalid signature");
  let event: Delivery;
  try {
    event = JSON.parse(raw) as Delivery;
  } catch {
    throw new HttpError(400, "invalid JSON");
  }
  const webhookId = c.req.headers.get("webhook-id")!.slice(0, 200);
  const user = event.metadata?.user_id ?? "";
  const account = user.startsWith("plato-") && UUID_RE.test(user.slice(6)) ? user.slice(6) : null;
  const relevant = event.type === "composio.trigger.message" && account !== null;
  const inserted = await c.sql`
    INSERT INTO plato.integration_events (webhook_id, account_id, type, payload, status)
    SELECT ${webhookId}, a.id, ${String(event.type ?? "unknown").slice(0, 100)}, ${c.sql.json(event as never)},
           ${relevant ? "pending" : "ignored"}
      FROM (SELECT ${account}::uuid AS id) x LEFT JOIN plato.accounts a ON a.id = x.id
    ON CONFLICT (webhook_id) DO NOTHING RETURNING webhook_id`;
  if (inserted.length && relevant) {
    // The request's connection closes when the response is sent, so the import (which runs
    // after it) has its own. A failure stays pending for the cron to retry.
    const sql = db(c.env);
    c.ctx.waitUntil(
      processEvent(c.env, sql, webhookId)
        .catch((e) => console.error("webhook import", e))
        .finally(() => sql.end({ timeout: 5 }).catch(() => undefined)),
    );
  }
  return json({ ok: true });
}

function attachmentsOf(data: Record<string, unknown>): { id: string; name: string; mime: string | null }[] {
  const list = (data.attachment_list ?? data.attachments ?? []) as Record<string, unknown>[];
  return (Array.isArray(list) ? list : [])
    .map((a) => ({
      id: String(a.attachmentId ?? a.attachment_id ?? a.id ?? ""),
      name: String(a.filename ?? a.file_name ?? a.name ?? ""),
      mime: (a.mimeType ?? a.mime_type ?? null) as string | null,
    }))
    .filter((a) => a.id && a.name);
}

/** Import what one trigger delivery points at. Idempotent: library rows are unique per
 * external file, so a retried event never stores a file twice. */
export async function processEvent(env: Env, sql: Sql, webhookId: string): Promise<void> {
  const [ev] = await sql`
    UPDATE plato.integration_events SET attempts = attempts + 1
     WHERE webhook_id = ${webhookId} AND status = 'pending' AND attempts < ${MAX_ATTEMPTS}
     RETURNING account_id, payload, attempts`;
  if (!ev || !ev.account_id) return;
  const event = ev.payload as Delivery;
  const account = ev.account_id as string;
  const [trigger] = await sql`
    SELECT toolkit FROM plato.integration_triggers
     WHERE account_id = ${account} AND trigger_id = ${event.metadata?.trigger_id ?? ""}`;
  try {
    if (!trigger) {
      await sql`UPDATE plato.integration_events SET status = 'ignored', processed_at = now() WHERE webhook_id = ${webhookId}`;
      return;
    }
    const data = event.data ?? {};
    const imported: string[] = [];
    if (trigger.toolkit === "googledrive") {
      const f = (data.file ?? data) as Record<string, unknown>;
      const name = String(f.name ?? f.title ?? "");
      if (f.id && name && f.mimeType !== "application/vnd.google-apps.folder") {
        if (library.kindOf(name) !== "other" || String(f.mimeType ?? "").startsWith("application/vnd.google-apps.")) {
          const out = await importOne(env, sql, account, "googledrive", { id: String(f.id), name, mime: (f.mimeType as string) ?? null });
          imported.push(out.name);
        }
      }
    } else if (trigger.toolkit === "gmail") {
      const messageId = String(data.message_id ?? data.messageId ?? "");
      for (const a of attachmentsOf(data)) {
        if (!messageId || library.kindOf(a.name) === "other") continue;
        const d = await composio.execute(env, account, "GMAIL_GET_ATTACHMENT", {
          message_id: messageId,
          attachment_id: a.id,
          file_name: a.name,
        });
        const ref = d.file as composio.FileRef;
        const bytes = await composio.fetchFile(ref, library.MAX_FILE_BYTES);
        const out = await library.store(env, sql, account, a.name, bytes, "gmail", {
          sourceRef: `gmail:${messageId}:${a.name}`,
          mediaType: a.mime ?? ref.mimetype,
          meta: { message_id: messageId },
        });
        imported.push(out.name);
      }
    }
    await sql`UPDATE plato.integration_events SET status = 'done', processed_at = now(),
                     error = ${imported.length ? null : "nothing to import"} WHERE webhook_id = ${webhookId}`;
  } catch (err) {
    const final = Number(ev.attempts) >= MAX_ATTEMPTS;
    await sql`UPDATE plato.integration_events SET status = ${final ? "failed" : "pending"},
                     error = ${String(err instanceof Error ? err.message : err).slice(0, 500)} WHERE webhook_id = ${webhookId}`;
    throw err;
  }
}

/** Cron: retry deliveries that could not be imported when they arrived. */
export async function retryPending(env: Env, sql: Sql): Promise<number> {
  const rows = await sql`
    SELECT webhook_id FROM plato.integration_events
     WHERE status = 'pending' AND attempts < ${MAX_ATTEMPTS} AND created_at < now() - interval '1 minute'
     ORDER BY created_at LIMIT 20`;
  const results = await Promise.allSettled(rows.map((r) => processEvent(env, sql, r.webhook_id as string)));
  return results.filter((r) => r.status === "rejected").length;
}
