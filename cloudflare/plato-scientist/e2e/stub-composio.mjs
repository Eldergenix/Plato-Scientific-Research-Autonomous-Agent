// Stub of the Composio v3 API for local tests (point PLATO_DEV_COMPOSIO_BASE_URL at it).
// Tool argument names and result shapes follow the live tool schemas (checked 2026-11-18):
// a call with a missing required argument fails the way Composio does. GET /__log returns
// every tool call, upload and trigger, so tests can assert what the Worker sent.
// Run: node e2e/stub-composio.mjs [port]
import http from "node:http";
import { createHash, randomUUID } from "node:crypto";

const PORT = Number(process.argv[2] || 8791);
const ORIGIN = `http://127.0.0.1:${PORT}`;
const conns = [];                 // {id, user, toolkit, status}
const staged = new Map();         // s3key -> {md5, bytes, name, mimetype}
const triggers = new Map();       // trigger id -> {slug, user, config}
const log = [];                   // {tool, user, args}
const FILES = {                   // downloadable files, by id
  "drv-csv": { name: "expression.csv", mimetype: "text/csv", data: Buffer.from("gene,count\nBRCA1,12\nTP53,40\n") },
  "drv-doc": { name: "Protocol.docx", mimetype: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", data: Buffer.from("PK fake docx") },
  "drv-new": { name: "new-samples.vcf", mimetype: "text/x-vcf", data: Buffer.from("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\n1\t100\trs1\tA\tG\n") },
  "od-1": { name: "plate.xlsx", mimetype: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", data: Buffer.from("PK fake xlsx") },
  "att-1": { name: "refs.bib", mimetype: "application/x-bibtex", data: Buffer.from("@article{a,title={T},year={2020}}\n") },
};
const REQUIRED = {
  GOOGLEDRIVE_LIST_FILES: [], GOOGLEDRIVE_DOWNLOAD_FILE: ["file_id"], GOOGLEDRIVE_CREATE_FOLDER: ["folder_name"],
  GOOGLEDRIVE_UPLOAD_FILE: ["file_to_upload"], DROPBOX_LIST_FILES_IN_FOLDER: [], DROPBOX_READ_FILE: ["path"],
  DROPBOX_UPLOAD_FILE: ["path", "content"], ONE_DRIVE_ONEDRIVE_LIST_ITEMS: [], ONE_DRIVE_SEARCH_ITEMS: ["q"],
  ONE_DRIVE_DOWNLOAD_FILE: ["item_id", "file_name"], ONE_DRIVE_ONEDRIVE_UPLOAD_FILE: ["file"],
  GMAIL_SEND_EMAIL: ["recipient_email", "body"], OUTLOOK_OUTLOOK_SEND_EMAIL: ["subject", "body", "to_email"],
  GMAIL_GET_ATTACHMENT: ["message_id", "attachment_id", "file_name"],
};
const TOOLKIT_OF = (tool) => ({ GOOGLEDRIVE: "googledrive", DROPBOX: "dropbox", ONE: "one_drive", GMAIL: "gmail", OUTLOOK: "outlook" })[tool.split("_")[0]];
const ref = (id) => ({ name: FILES[id].name, mimetype: FILES[id].mimetype, s3url: `${ORIGIN}/files/${id}` });
const fileArg = (v, tool) => {
  if (!v || typeof v !== "object" || !v.s3key || !v.name || !v.mimetype) throw new Error(`${tool}: file argument needs name, mimetype and s3key`);
  const s = staged.get(v.s3key);
  if (!s || !s.bytes) throw new Error(`${tool}: ${v.s3key} was never uploaded`);
  return s;
};

function execute(tool, user, args) {
  const missing = (REQUIRED[tool] ?? null);
  if (missing === null) throw new Error(`unknown tool ${tool}`);
  for (const k of missing) if (args[k] === undefined || args[k] === "") throw new Error(`missing required argument ${k}`);
  if (!conns.some((c) => c.user === user && c.toolkit === TOOLKIT_OF(tool) && c.status === "ACTIVE")) throw new Error("no active connection");
  switch (tool) {
    case "GOOGLEDRIVE_LIST_FILES": {
      const inLab = String(args.q).includes("'fld-lab' in parents");
      const files = inLab
        ? [{ id: "drv-csv", name: "expression.csv", mimeType: "text/csv", size: "29" }]
        : [{ id: "fld-lab", name: "Lab", mimeType: "application/vnd.google-apps.folder" },
           { id: "drv-doc", name: "Protocol", mimeType: "application/vnd.google-apps.document" },
           { id: "drv-form", name: "Form", mimeType: "application/vnd.google-apps.form" }];
      return { files, nextPageToken: "" };
    }
    case "GOOGLEDRIVE_DOWNLOAD_FILE": return { downloaded_file_content: ref(args.file_id) };
    case "GOOGLEDRIVE_CREATE_FOLDER": return { id: "fld-" + randomUUID().slice(0, 8), name: args.folder_name, mimeType: "application/vnd.google-apps.folder" };
    case "GOOGLEDRIVE_UPLOAD_FILE": { const s = fileArg(args.file_to_upload, tool); return { id: randomUUID(), name: s.name, size: String(s.bytes.length) }; }
    case "DROPBOX_LIST_FILES_IN_FOLDER":
      return { entries: [{ ".tag": "file", id: "id:dbx1", name: "variants.vcf.gz", path_display: "/variants.vcf.gz", path_lower: "/variants.vcf.gz", size: 4 },
                         { ".tag": "file", id: "id:dbx2", name: "notes.txt", path_display: "/notes.txt", path_lower: "/notes.txt", size: 4 }], has_more: false };
    case "DROPBOX_READ_FILE": {
      // Binary files come back base64, text files as text; metadata.size is the real size.
      const bin = args.path === "/variants.vcf.gz";
      const data = bin ? Buffer.from([0x1f, 0x8b, 8, 0]) : Buffer.from("abcd");
      return { file_content_bytes: bin ? data.toString("base64") : data.toString(), file_name: args.path.slice(1), metadata: { id: "x", name: args.path.slice(1), size: data.length } };
    }
    case "DROPBOX_UPLOAD_FILE": { const s = fileArg(args.content, tool); return { id: randomUUID(), name: s.name, size: s.bytes.length, path_display: args.path }; }
    case "ONE_DRIVE_ONEDRIVE_LIST_ITEMS": return { value: [{ id: "od-1", name: "plate.xlsx", size: 12, file: { mimeType: FILES["od-1"].mimetype } }] };
    case "ONE_DRIVE_SEARCH_ITEMS": return { value: [] };
    case "ONE_DRIVE_DOWNLOAD_FILE": return { content: ref(args.item_id) };
    case "ONE_DRIVE_ONEDRIVE_UPLOAD_FILE": { const s = fileArg(args.file, tool); return { id: randomUUID(), name: s.name, size: s.bytes.length }; }
    case "GMAIL_SEND_EMAIL": case "OUTLOOK_OUTLOOK_SEND_EMAIL": if (args.attachment) fileArg(args.attachment, tool); return { response_data: { id: "m1" } };
    case "GMAIL_GET_ATTACHMENT": return { file: ref(args.attachment_id) };
  }
}

const send = (res, code, body) => { res.writeHead(code, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };
http.createServer((req, res) => {
  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    const raw = Buffer.concat(chunks), url = new URL(req.url, ORIGIN), p = url.pathname;
    let body = {};
    try { body = raw.length && req.headers["content-type"]?.includes("json") ? JSON.parse(raw) : {}; } catch { return send(res, 400, { error: { message: "bad json" } }); }
    if (p.startsWith("/api/") && req.headers["x-api-key"] !== "ak_stub") return send(res, 401, { error: { message: "invalid api key" } });
    if (p === "/__log") return send(res, 200, { log, triggers: [...triggers.entries()], conns });
    if (p.startsWith("/files/")) { const f = FILES[p.slice(7)]; if (!f) return send(res, 404, {}); res.writeHead(200, { "content-type": f.mimetype, "content-length": f.data.length }); return res.end(f.data); }
    if (p.startsWith("/put/") && req.method === "PUT") {
      const s = staged.get(decodeURIComponent(p.slice(5)));
      if (!s) return send(res, 404, {});
      if (createHash("md5").update(raw).digest("hex") !== s.md5) return send(res, 400, { error: "md5 mismatch" });
      if (req.headers["content-type"] !== s.mimetype) return send(res, 400, { error: "content-type mismatch" });
      s.bytes = raw; log.push({ upload: s.name, bytes: raw.length });
      return send(res, 200, {});
    }
    if (p === "/api/v3/auth_configs" && req.method === "GET") return send(res, 200, { items: [] });
    if (p === "/api/v3/auth_configs" && req.method === "POST") return send(res, 201, { auth_config: { id: "ac_" + body.toolkit.slug } });
    if (p === "/api/v3/connected_accounts" && req.method === "GET") {
      const user = url.searchParams.get("user_ids");
      return send(res, 200, { items: conns.filter((c) => c.user === user).map((c) => ({ id: c.id, status: c.status, toolkit: { slug: c.toolkit } })) });
    }
    if (p === "/api/v3/connected_accounts/link" && req.method === "POST") {
      if (!body.auth_config_id || !body.user_id || !body.callback_url) return send(res, 400, { error: { message: "missing fields" } });
      // Sign-in is simulated as completed: the connection is active and the redirect returns to the app.
      const id = "ca_" + randomUUID().slice(0, 8);
      conns.push({ id, user: body.user_id, toolkit: body.auth_config_id.slice(3), status: "ACTIVE" });
      return send(res, 201, { redirect_url: body.callback_url, connected_account_id: id });
    }
    let m;
    if ((m = p.match(/^\/api\/v3\/connected_accounts\/([^/]+)$/)) && req.method === "DELETE") {
      const i = conns.findIndex((c) => c.id === m[1]); if (i < 0) return send(res, 404, { error: { message: "not found" } });
      conns.splice(i, 1); return send(res, 200, { success: true });
    }
    if ((m = p.match(/^\/api\/v3\/tools\/execute\/([A-Z_]+)$/))) {
      log.push({ tool: m[1], user: body.user_id, args: body.arguments });
      try { return send(res, 200, { data: execute(m[1], body.user_id, body.arguments ?? {}), error: null, successful: true }); }
      catch (e) { return send(res, 200, { data: {}, error: e.message, successful: false }); }
    }
    if (p === "/api/v3/files/upload/request" && req.method === "POST") {
      for (const k of ["toolkit_slug", "tool_slug", "filename", "mimetype", "md5"]) if (!body[k]) return send(res, 400, { error: { message: `missing ${k}` } });
      const key = `${body.toolkit_slug}/${body.tool_slug}/${randomUUID()}/${body.filename}`;
      staged.set(key, { md5: body.md5, name: body.filename, mimetype: body.mimetype, bytes: null });
      return send(res, 200, { key, new_presigned_url: `${ORIGIN}/put/${encodeURIComponent(key)}`, metadata: { storage_backend: "s3" } });
    }
    if ((m = p.match(/^\/api\/v3\.1\/trigger_instances\/([A-Z_]+)\/upsert$/)) && req.method === "POST") {
      const id = "ti_" + randomUUID().slice(0, 8);
      triggers.set(id, { slug: m[1], user: body.user_id, config: body.trigger_config });
      return send(res, 200, { trigger_id: id });
    }
    if ((m = p.match(/^\/api\/v3\/trigger_instances\/manage\/([^/]+)$/)) && req.method === "DELETE") {
      if (!triggers.delete(m[1])) return send(res, 410, { error: { message: "gone" } });
      return send(res, 200, { success: true });
    }
    send(res, 404, { error: { message: `no stub for ${req.method} ${p}` } });
  });
}).listen(PORT, "127.0.0.1", () => console.log(`composio stub on ${ORIGIN}`));
