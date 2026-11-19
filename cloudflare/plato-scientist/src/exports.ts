/**
 * Publication packages: built by the campaign's container, stored in R2, downloaded,
 * previewed (single files read out of the zip), sent to a connected Drive, Dropbox or
 * OneDrive, or emailed through the person's Gmail or Outlook with a signed link.
 */
import type { Ctx } from "./auth";
import { authenticate, ownKey } from "./auth";
import { containerError, toContainer } from "./campaigns";
import * as composio from "./composio";
import { b64url, enc, type Env, HttpError, json, monthlyCap, readJson, type Sql, unb64 } from "./lib";
import * as library from "./library";
import styles from "./citation_styles.json";
import catalogue from "./journals.json";
import { entries, readEntry } from "./zip";

const JOURNALS = new Set((catalogue as { key: string }[]).map((j) => j.key));
const STYLES = new Set((styles as { key: string }[]).map((s) => s.key));
const LINK_DAYS = 7;
/** Files sent to Google Drive one by one (its upload tool takes at most 5 MB a file). */
const DRIVE_MAX = 5 * 1024 * 1024;
const ATTACH_MAX = 18 * 1024 * 1024; // under Gmail's 25 MB after base64 expansion

export async function journals(_c: Ctx): Promise<Response> {
  return json({ journals: catalogue, citation_styles: styles });
}

async function campaignFor(c: Ctx, id: string) {
  const [row] = await c.sql`SELECT account_id, own_key, status FROM plato.research_campaigns WHERE id = ${id}`;
  if (!row || (!c.who!.isAdmin && row.account_id !== c.who!.accountId)) throw new HttpError(404, "not found");
  return row;
}

async function exportRow(sql: Sql, id: string) {
  const [row] = await sql`
    SELECT e.id, e.campaign_id, e.journal, e.status, e.name, e.r2_key, e.bytes, e.sha256, e.summary, e.created_at,
           c.account_id
      FROM plato.publication_exports e JOIN plato.research_campaigns c ON c.id = e.campaign_id
     WHERE e.id = ${id}`;
  return row;
}

async function ownedExport(c: Ctx, id: string) {
  const row = await exportRow(c.sql, id);
  if (!row || (!c.who!.isAdmin && row.account_id !== c.who!.accountId)) throw new HttpError(404, "not found");
  if (row.status !== "ready") throw new HttpError(409, "this package is not ready");
  return row;
}

const publicRow = (r: Record<string, unknown>) => ({
  id: r.id,
  campaign_id: r.campaign_id,
  journal: r.journal,
  status: r.status,
  name: r.name,
  bytes: r.bytes,
  sha256: r.sha256,
  summary: r.summary,
  created_at: r.created_at,
});

export async function listExports(c: Ctx, id: string): Promise<Response> {
  await campaignFor(c, id);
  const rows = await c.sql`
    SELECT id, campaign_id, journal, status, name, bytes, sha256, summary, created_at
      FROM plato.publication_exports WHERE campaign_id = ${id} AND status <> 'building'
     ORDER BY created_at DESC LIMIT 50`;
  return json({ exports: rows });
}

export async function createExport(c: Ctx, id: string): Promise<Response> {
  const campaign = await campaignFor(c, id);
  if (campaign.status !== "completed") throw new HttpError(409, "The paper is not finished yet.");
  const body = await readJson(c.req);
  const journal = typeof body.journal === "string" ? body.journal : "";
  if (!JOURNALS.has(journal)) throw new HttpError(400, "unknown journal");
  // "journal" (or nothing) keeps the journal's own citation style.
  const style = typeof body.style === "string" && body.style !== "journal" ? body.style : "";
  if (style && !STYLES.has(style)) throw new HttpError(400, "unknown citation style");
  const owner = campaign.account_id as string | null;
  const key = campaign.own_key ? await ownKey(c.env, c.sql, owner) : null;
  if (campaign.own_key && !key) throw new HttpError(409, "This thread runs on its owner's API key, which was removed.");
  const q = new URLSearchParams();
  if (owner) q.set("account", owner);
  if (style) q.set("style", style);
  // The default key's monthly allowance applies to the owner (admins are uncapped).
  if (!campaign.own_key && owner) {
    const [a] = await c.sql`SELECT is_admin, monthly_token_cap FROM plato.accounts WHERE id = ${owner}`;
    if (a && !a.is_admin) {
      q.set("cap", String(monthlyCap(c.env, a.monthly_token_cap as number | null)));
    }
  }
  const res = await toContainer(c.env, id, `/internal/campaigns/${id}/exports/${journal}?${q}`, { method: "POST" }, key);
  if (!res.ok) throw new HttpError(res.status >= 500 ? 502 : res.status, await containerError(res));
  const exportId = res.headers.get("x-plato-export-id");
  const r2Key = res.headers.get("x-plato-export-key");
  const length = Number(res.headers.get("content-length") ?? NaN);
  if (!exportId || !r2Key || !res.body || !Number.isFinite(length)) throw new HttpError(502, "the package build returned no file");
  try {
    // Stream straight into R2: the zip never sits in the Worker's memory.
    const { readable, writable } = new FixedLengthStream(length);
    const [, put] = await Promise.all([
      res.body.pipeTo(writable),
      c.env.EXPORTS.put(r2Key, readable, {
        httpMetadata: { contentType: "application/zip" },
        customMetadata: { campaign: id, journal },
      }),
    ]);
    if (!put) throw new Error("R2 put returned null");
  } catch (err) {
    await c.sql`UPDATE plato.publication_exports SET status = 'failed', error = ${String(err).slice(0, 500)},
                       updated_at = now() WHERE id = ${exportId}`;
    throw new HttpError(502, "could not store the package");
  }
  await c.sql`UPDATE plato.publication_exports SET status = 'ready', updated_at = now() WHERE id = ${exportId}`;
  return json({ export: publicRow((await exportRow(c.sql, exportId))!) }, 201);
}

/* ---------- the typeset paper ---------- */

/** The finished paper as a PDF (preprint layout), for the in-app viewer. Built once per
 * manuscript version by the campaign's container (pdfLaTeX, no model call) and kept in
 * R2, so later views never wake the container. ``?download=1`` saves it instead. */
export async function manuscriptPdf(c: Ctx, id: string): Promise<Response> {
  const campaign = await campaignFor(c, id);
  if (campaign.status !== "completed") throw new HttpError(409, "The paper is not finished yet.");
  const [version] = await c.sql`
    SELECT e.id FROM plato.evidence_artifacts e JOIN plato.exploration_nodes n ON n.id = e.node_id
     WHERE n.campaign_id = ${id} AND n.node_type = 'goal' AND n.dedup_key = 'root-goal'
       AND e.artifact_type = 'latex_section' AND e.content IS NOT NULL
     ORDER BY e.created_at DESC LIMIT 1`;
  if (!version) throw new HttpError(404, "manuscript not written yet");
  const key = `previews/${id}/${version.id}.pdf`;
  let body: ReadableStream | ArrayBuffer;
  const cached = await c.env.EXPORTS.get(key);
  if (cached) body = cached.body;
  else {
    const res = await toContainer(c.env, id, `/internal/campaigns/${id}/manuscript.pdf`, { method: "GET" });
    if (!res.ok) {
      const status = res.status === 409 || res.status === 422 ? res.status : 502;
      throw new HttpError(status, await containerError(res));
    }
    const data = await res.arrayBuffer();
    if (new TextDecoder().decode(data.slice(0, 5)) !== "%PDF-") throw new HttpError(502, "the typesetter returned no PDF");
    await c.env.EXPORTS.put(key, data, {
      httpMetadata: { contentType: "application/pdf" },
      customMetadata: { campaign: id, latex: String(version.id) },
    });
    body = data;
  }
  const download = c.url.searchParams.get("download") === "1";
  return new Response(body, {
    headers: {
      "content-type": "application/pdf",
      "content-disposition": `${download ? "attachment" : "inline"}; filename="paper-${id.slice(0, 8)}.pdf"`,
      etag: `"${version.id}"`,
      "cache-control": "private, max-age=86400",
      "x-content-type-options": "nosniff",
    },
  });
}

/* ---------- download, signed links and single files ---------- */

async function linkKey(env: Env): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey("raw", unb64(env.PLATO_SECRETS_KEY), "HKDF", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(32), info: enc.encode("plato/export-links/v1") },
    base,
    { name: "HMAC", hash: "SHA-256", length: 256 },
    false,
    ["sign", "verify"],
  );
}

export async function signedLink(env: Env, origin: string, exportId: string): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + LINK_DAYS * 86400;
  const sig = b64url(await crypto.subtle.sign("HMAC", await linkKey(env), enc.encode(`${exportId}.${exp}`)));
  return `${origin}/api/exports/${exportId}/download?exp=${exp}&sig=${sig}`;
}

async function validLink(env: Env, exportId: string, exp: string | null, sig: string | null): Promise<boolean> {
  if (!exp || !sig || !/^\d{1,12}$/.test(exp) || Number(exp) < Date.now() / 1000) return false;
  try {
    return await crypto.subtle.verify("HMAC", await linkKey(env), unb64(sig), enc.encode(`${exportId}.${exp}`));
  } catch {
    return false;
  }
}

/** The zip. Signed in, or with a valid signed link (sent by email, valid 7 days). */
export async function download(c: Ctx, id: string): Promise<Response> {
  const p = c.url.searchParams;
  let row: Record<string, unknown> | undefined;
  if (p.has("sig")) {
    if (!(await validLink(c.env, id, p.get("exp"), p.get("sig")))) throw new HttpError(403, "This link has expired or is invalid.");
    row = await exportRow(c.sql, id);
    if (!row || row.status !== "ready") throw new HttpError(404, "not found");
  } else {
    c.who = await authenticate(c);
    if (!c.who) throw new HttpError(401, "Sign in to continue.");
    row = await ownedExport(c, id);
  }
  const obj = await c.env.EXPORTS.get(row.r2_key as string);
  if (!obj) throw new HttpError(404, "not found");
  return new Response(obj.body, {
    headers: {
      "content-type": "application/zip",
      "content-length": String(obj.size),
      "content-disposition": `attachment; filename="${row.name}.zip"`,
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

const PREVIEW_TYPES: Record<string, string> = {
  pdf: "application/pdf",
  png: "image/png",
  md: "text/plain; charset=utf-8",
  tex: "text/plain; charset=utf-8",
  csv: "text/plain; charset=utf-8",
  json: "application/json",
  xml: "text/plain; charset=utf-8",
  bib: "text/plain; charset=utf-8",
  cff: "text/plain; charset=utf-8",
};

async function entryBytes(env: Env, row: Record<string, unknown>, path: string) {
  const all = await entries(env.EXPORTS, row.r2_key as string, Number(row.bytes));
  const e = all.find((x) => x.name === `${row.name}/${path}`);
  if (!e) throw new HttpError(404, "file not in package");
  return { entry: e, data: await readEntry(env.EXPORTS, row.r2_key as string, e) };
}

/** One file from the package (``?path=manuscript/manuscript.pdf``): viewed inline for PDFs
 * and images, as text otherwise, downloaded with ``&download=1``. */
export async function exportFile(c: Ctx, id: string): Promise<Response> {
  const row = await ownedExport(c, id);
  const path = c.url.searchParams.get("path") ?? "";
  if (!/^[A-Za-z0-9._/-]{1,300}$/.test(path) || path.includes("..")) throw new HttpError(400, "invalid path");
  const { data } = await entryBytes(c.env, row, path);
  const ext = path.split(".").pop()!.toLowerCase();
  const download = c.url.searchParams.get("download") === "1" || !(ext in PREVIEW_TYPES);
  return new Response(data, {
    headers: {
      "content-type": download ? "application/octet-stream" : PREVIEW_TYPES[ext],
      "content-disposition": `${download ? "attachment" : "inline"}; filename="${path.split("/").pop()}"`,
      // Browsers refuse to run their PDF viewer in a sandboxed document, so a PDF goes
      // without the sandbox; its viewer never runs script on this origin.
      ...(download || ext !== "pdf"
        ? { "content-security-policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox" }
        : {}),
      "x-content-type-options": "nosniff",
      "cache-control": "private, max-age=3600",
    },
  });
}

/* ---------- send to a connected service ---------- */

const DRIVE_FILES = [
  "manuscript/manuscript.pdf",
  "manuscript/manuscript.docx",
  "manuscript/manuscript.tex",
  "manuscript/manuscript.jats.xml",
  "manuscript/references.bib",
  "manuscript/references.ris",
  "submission/cover_letter.docx",
  "supplement/supplementary_information.pdf",
  "data/data_S1.xlsx",
  "README.md",
  "SUBMISSION_CHECKLIST.md",
];

const MIME: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  tex: "application/x-tex",
  xml: "application/xml",
  bib: "application/x-bibtex",
  ris: "application/x-research-info-systems",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  md: "text/markdown",
  zip: "application/zip",
};
const mimeOf = (name: string) => MIME[name.split(".").pop()!.toLowerCase()] ?? "application/octet-stream";

export async function sendExport(c: Ctx, id: string): Promise<Response> {
  const row = await ownedExport(c, id);
  const body = await readJson(c.req);
  const tk = composio.toolkit(String(body.service ?? ""));
  if (!composio.TOOLKITS[tk].files) throw new HttpError(400, "pick Google Drive, Dropbox or OneDrive");
  const account = c.who!.accountId!;
  const name = row.name as string;
  const sent: string[] = [];
  const skipped: string[] = [];
  if (tk === "googledrive") {
    const folder = await composio.execute(c.env, account, "GOOGLEDRIVE_CREATE_FOLDER", {
      folder_name: name,
      ...(typeof body.folder_id === "string" && body.folder_id ? { parent_id: body.folder_id } : {}),
    });
    const folderId = (folder.id ?? (folder as { response_data?: { id?: string } }).response_data?.id) as string | undefined;
    const files = Number(row.bytes) <= DRIVE_MAX ? [...DRIVE_FILES, "__zip__"] : DRIVE_FILES;
    for (const path of files) {
      let fileName: string;
      let data: Uint8Array;
      if (path === "__zip__") {
        const obj = await c.env.EXPORTS.get(row.r2_key as string);
        if (!obj) continue;
        fileName = `${name}.zip`;
        data = new Uint8Array(await obj.arrayBuffer());
      } else {
        try {
          data = (await entryBytes(c.env, row, path)).data;
        } catch {
          continue; // not in this package (for example no PDF when it failed to compile)
        }
        fileName = path.split("/").pop()!;
      }
      if (data.byteLength > DRIVE_MAX) {
        skipped.push(fileName);
        continue;
      }
      const file = await composio.stageFile(c.env, tk, "GOOGLEDRIVE_UPLOAD_FILE", fileName, mimeOf(fileName), data);
      await composio.execute(c.env, account, "GOOGLEDRIVE_UPLOAD_FILE", {
        file_to_upload: file,
        ...(folderId ? { folder_to_upload_to: folderId } : {}),
      });
      sent.push(fileName);
    }
  } else {
    const obj = await c.env.EXPORTS.get(row.r2_key as string);
    if (!obj) throw new HttpError(404, "not found");
    const data = new Uint8Array(await obj.arrayBuffer());
    const fileName = `${name}.zip`;
    if (tk === "dropbox") {
      const folder = typeof body.path === "string" && body.path.startsWith("/") ? body.path.replace(/\/+$/, "") : "/Plato";
      const file = await composio.stageFile(c.env, tk, "DROPBOX_UPLOAD_FILE", fileName, "application/zip", data);
      await composio.execute(c.env, account, "DROPBOX_UPLOAD_FILE", {
        path: `${folder}/${fileName}`,
        content: file,
        mode: "add",
        autorename: true,
      });
    } else {
      const file = await composio.stageFile(c.env, tk, "ONE_DRIVE_ONEDRIVE_UPLOAD_FILE", fileName, "application/zip", data);
      await composio.execute(c.env, account, "ONE_DRIVE_ONEDRIVE_UPLOAD_FILE", {
        file,
        folder: typeof body.path === "string" && body.path ? body.path : "/Plato",
      });
    }
    sent.push(fileName);
  }
  return json({ service: tk, sent, skipped });
}

/* ---------- email ---------- */

const EMAIL_RE = /^[^\s@<>(),;:"]+@[^\s@<>(),;:"]+\.[^\s@<>(),;:"]+$/;

export async function emailExport(c: Ctx, id: string): Promise<Response> {
  const row = await ownedExport(c, id);
  const body = await readJson(c.req);
  const tk = composio.toolkit(String(body.service ?? ""));
  if (!composio.TOOLKITS[tk].email) throw new HttpError(400, "pick Gmail or Outlook");
  const to = String(body.to ?? "").trim().toLowerCase();
  if (!EMAIL_RE.test(to) || to.length > 254) throw new HttpError(400, "enter one valid email address");
  const note = typeof body.message === "string" ? body.message.slice(0, 4000) : "";
  const summary = (row.summary ?? {}) as { counts?: Record<string, number> };
  const link = await signedLink(c.env, c.url.origin, id);
  const subject = (typeof body.subject === "string" && body.subject.trim()
    ? body.subject.trim()
    : `Publication package: ${row.name}`).slice(0, 200);
  const lines = [
    note,
    note ? "" : null,
    `The publication package "${row.name}" (${row.journal}) is ready.`,
    `Download the complete package (${Math.round(Number(row.bytes) / 1024)} KB; link valid for ${LINK_DAYS} days):`,
    link,
    "",
    "It contains the manuscript (PDF, LaTeX, Word, JATS XML), the Supplementary Information, source data (CSV and Excel), code, logs and a submission checklist.",
    summary.counts ? `Main text: ${summary.counts.main_text_words} words; ${summary.counts.references} references; ${summary.counts.figures} figures.` : null,
    "",
    "Sent from Plato (jarvisos.xyz).",
  ].filter((l) => l !== null);
  let attachment: Record<string, string> | null = null;
  try {
    const { data } = await entryBytes(c.env, row, "manuscript/manuscript.pdf");
    if (data.byteLength <= ATTACH_MAX) {
      const tool = tk === "gmail" ? "GMAIL_SEND_EMAIL" : "OUTLOOK_OUTLOOK_SEND_EMAIL";
      attachment = await composio.stageFile(c.env, tk, tool, `${row.name}.pdf`, "application/pdf", data);
    }
  } catch {
    attachment = null; // no PDF in this package: the link still carries everything
  }
  const text = lines.join("\n");
  if (tk === "gmail") {
    await composio.execute(c.env, c.who!.accountId!, "GMAIL_SEND_EMAIL", {
      recipient_email: to,
      subject,
      body: text,
      is_html: false,
      ...(attachment ? { attachment } : {}),
    });
  } else {
    await composio.execute(c.env, c.who!.accountId!, "OUTLOOK_OUTLOOK_SEND_EMAIL", {
      to_email: to,
      subject,
      body: text,
      ...(attachment ? { attachment } : {}),
    });
  }
  return json({ sent: true, service: tk, to, attached_pdf: Boolean(attachment) });
}

/** Save the package to the person's library too (so it can be sent or reused later). */
export async function saveToLibrary(c: Ctx, id: string): Promise<Response> {
  const row = await ownedExport(c, id);
  const obj = await c.env.EXPORTS.get(row.r2_key as string);
  if (!obj) throw new HttpError(404, "not found");
  const out = await library.store(c.env, c.sql, c.who!.accountId!, `${row.name}.zip`, new Uint8Array(await obj.arrayBuffer()), "export", {
    sourceRef: `export:${id}`,
    mediaType: "application/zip",
  });
  return json(out, 201);
}
