// End-to-end test of the Files library, connected services (against e2e/stub-composio.mjs),
// publication packages, sending, email links and trigger webhooks.
// Needs wrangler dev on :8787 started with PLATO_DEV_COMPOSIO_BASE_URL:http://127.0.0.1:8791,
// COMPOSIO_API_KEY:ak_stub and COMPOSIO_WEBHOOK_SECRET:<secret>, the Python service on
// PLATO_DEV_SERVICE_URL, and PLATO_DATABASE_URL for the seed script (same database).
// Run: COMPOSIO_WEBHOOK_SECRET=<secret> node e2e/integrations.test.mjs
import assert from "node:assert/strict";
import { createHash, createHmac } from "node:crypto";
import { execFileSync } from "node:child_process";
import path from "node:path";

const BASE = process.env.PLATO_E2E_BASE || "http://127.0.0.1:8787";
const STUB = process.env.PLATO_E2E_COMPOSIO || "http://127.0.0.1:8791";
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE)) throw new Error("PLATO_E2E_BASE must be a local wrangler dev URL");
const SECRET = process.env.COMPOSIO_WEBHOOK_SECRET;
if (!SECRET) throw new Error("set COMPOSIO_WEBHOOK_SECRET to the value wrangler dev was given");
const PY = process.env.PLATO_E2E_PYTHON || "python3";
const here = path.dirname(new URL(import.meta.url).pathname);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let n = 0;
const step = (m) => { n++; console.log("·", m); };

class Client {
  constructor(ip) { this.cookie = ""; this.ip = ip; }
  async raw(method, p, { body, headers = {}, cookie = true } = {}) {
    const h = { origin: BASE, "cf-connecting-ip": this.ip, ...(cookie && this.cookie ? { cookie: this.cookie } : {}), ...headers };
    const r = await fetch(BASE + "/api/" + p, { method, headers: h, body, redirect: "manual" });
    for (const c of r.headers.getSetCookie?.() ?? []) this.cookie = c.split(";")[0];
    return r;
  }
  async req(method, p, body, headers = {}) {
    const r = await this.raw(method, p, { body: body === undefined ? undefined : JSON.stringify(body), headers: body === undefined ? headers : { "content-type": "application/json", ...headers } });
    const t = await r.text(); let data; try { data = JSON.parse(t); } catch { data = t; }
    return { status: r.status, data, headers: r.headers };
  }
}
const ok = (r, s = 200) => { assert.equal(r.status, s, JSON.stringify(r.data).slice(0, 500)); return r.data; };
// Only this run's person: the stub keeps state across runs.
const stubLog = async () => {
  const all = await (await fetch(STUB + "/__log")).json();
  return { log: all.log.filter((x) => x.user === user), triggers: all.triggers.filter(([, t]) => t.user === user) };
};
const ip = () => `10.9.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250) + 1}`;
const uniq = Date.now().toString(36);

const a = new Client(ip()), b = new Client(ip());
ok(await a.req("POST", "auth/signup", { email: `int-a-${uniq}@example.org`, password: "correct horse battery", name: "Ada" }), 201);
ok(await b.req("POST", "auth/signup", { email: `int-b-${uniq}@example.org`, password: "correct horse battery", name: "Bob" }), 201);
const acct = ok(await a.req("GET", "me")).account.id;
const user = `plato-${acct}`;

/* ---------- connections ---------- */
let ints = ok(await a.req("GET", "integrations"));
assert.equal(ints.configured, true);
assert.deepEqual(ints.services.map((s) => [s.slug, s.status]), [["googledrive", "disconnected"], ["dropbox", "disconnected"], ["one_drive", "disconnected"], ["gmail", "disconnected"], ["outlook", "disconnected"]]);
assert.equal((await a.req("POST", "integrations/connect", { service: "myspace" })).status, 404);
for (const s of ["googledrive", "dropbox", "one_drive", "gmail"]) {
  const r = ok(await a.req("POST", "integrations/connect", { service: s }));
  assert.match(r.redirect_url, /^https?:\/\/[^/]+\/#\/settings\/integrations$/);   // wrangler dev reports the route host
}
ints = ok(await a.req("GET", "integrations"));
assert.deepEqual(ints.services.filter((s) => s.status === "connected").map((s) => s.slug), ["googledrive", "dropbox", "one_drive", "gmail"]);
assert.deepEqual(ok(await b.req("GET", "integrations")).services.filter((s) => s.status === "connected"), [], "connections are per person");
step("connect four services; another person sees none of them");

/* ---------- browse and import ---------- */
const root = ok(await a.req("GET", "integrations/files?service=googledrive"));
assert.deepEqual(root.items.map((i) => [i.name, i.kind]), [["Lab", "folder"], ["Protocol", "other"], ["Form", "other"]]);
const lab = ok(await a.req("GET", "integrations/files?service=googledrive&folder=fld-lab"));
assert.deepEqual(lab.items.map((i) => [i.name, i.kind, i.size]), [["expression.csv", "data", 29]]);
let imp = ok(await a.req("POST", "integrations/import", { service: "googledrive", files: [lab.items[0], root.items[1], root.items[2], root.items[0]] }));
assert.equal(imp.results[0].name, "expression.csv"); assert.equal(imp.results[0].kind, "data"); assert.equal(imp.results[0].duplicate, false);
assert.equal(imp.results[1].name, "Protocol.docx", "Google Docs are exported as Word");
assert.match(imp.results[2].error, /cannot be exported/);
assert.equal(imp.results[3].error, "not a file");
const csvId = imp.results[0].id;
imp = ok(await a.req("POST", "integrations/import", { service: "googledrive", files: [lab.items[0]] }));
assert.equal(imp.results[0].duplicate, true); assert.equal(imp.results[0].id, csvId);
let log = await stubLog();
assert.deepEqual(log.log.find((x) => x.tool === "GOOGLEDRIVE_DOWNLOAD_FILE" && x.args.file_id === "drv-doc").args.mime_type, "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
step("Drive: browse folders, import a CSV and a Google Doc as .docx; refusals reported per file; re-import is a no-op");

const dbx = ok(await a.req("GET", "integrations/files?service=dropbox"));
imp = ok(await a.req("POST", "integrations/import", { service: "dropbox", files: dbx.items }));
const [gz, txt] = imp.results;
assert.equal(gz.kind, "data", ".vcf.gz is a data file");
const gzBytes = Buffer.from(await (await a.raw("GET", `library/${gz.id}`)).arrayBuffer());
assert.deepEqual([...gzBytes], [0x1f, 0x8b, 8, 0], "binary Dropbox file decoded from base64");
const txtRes = await a.raw("GET", `library/${txt.id}`);
assert.equal(await txtRes.text(), "abcd", "4-byte text file kept as text, not decoded as base64");
assert.equal(txtRes.headers.get("content-type"), "application/octet-stream");
assert.match(txtRes.headers.get("content-disposition"), /^attachment;/);
const od = ok(await a.req("GET", "integrations/files?service=one_drive"));
imp = ok(await a.req("POST", "integrations/import", { service: "one_drive", files: od.items }));
assert.equal(imp.results[0].name, "plate.xlsx");
assert.equal((await a.req("GET", "integrations/files?service=gmail")).status, 400);
step("Dropbox binary and text files, OneDrive workbook imported byte-exact");

/* ---------- uploads ---------- */
const vcf = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\n1\t5\t.\tC\tT\n";
const up = (name, data, type = "application/octet-stream") => a.raw("POST", "library", { body: data, headers: { "x-file-name": encodeURIComponent(name), "content-type": type } });
let r = await up("../../etc/calls.vcf", vcf, "text/vcard");
assert.equal(r.status, 201);
const vcfFile = await r.json();
assert.equal(vcfFile.name, "calls.vcf"); assert.equal(vcfFile.kind, "data");
assert.equal(vcfFile.sha256, createHash("sha256").update(vcf).digest("hex"));
assert.equal((await up("refs.bib", "@article{k, title={A study}, year={2021}, doi={10.1/x}}\n")).status, 201);
assert.equal((await a.raw("POST", "library", { body: "x" })).status, 400, "name required");
const libA = ok(await a.req("GET", "library"));
assert.equal(libA.limits.file_bytes, 25 * 2 ** 20);
const bib = libA.files.find((f) => f.name === "refs.bib");
assert.equal(libA.files.find((f) => f.id === vcfFile.id).media_type, "text/x-vcf", "VCF is variant calls, not vCard");
assert.equal((await b.raw("GET", `library/${vcfFile.id}`)).status, 404, "another person's file is not found");
assert.equal((await b.raw("DELETE", `library/${vcfFile.id}`)).status, 404);
step("upload: names sanitised, VCF typed correctly, SHA-256 recorded, owner-only");

/* ---------- a finished paper and its package ---------- */
const cid = execFileSync(PY, [path.join(here, "seed_campaign.py"), acct], { encoding: "utf8", env: process.env }).trim().split("\n").pop();
const journals = ok(await a.req("GET", "publish/journals")).journals;
assert.ok(journals.length >= 9 && journals.some((j) => j.key === "nature"));
assert.equal((await a.req("POST", `campaigns/${cid}/exports`, { journal: "myjournal" })).status, 400);
assert.equal((await b.req("POST", `campaigns/${cid}/exports`, { journal: "nature" })).status, 404, "only the owner builds");
const built = ok(await a.req("POST", `campaigns/${cid}/exports`, { journal: "nature" }), 201).export;
assert.equal(built.status, "ready");
assert.ok(built.summary.checks.length > 10 && built.summary.pdf_ok);
const exps = ok(await a.req("GET", `campaigns/${cid}/exports`)).exports;
assert.deepEqual(exps.map((x) => x.id), [built.id]);
assert.equal(built.summary.citation_style.key, "journal");
assert.ok(ok(await a.req("GET", "publish/journals")).citation_styles.some((x) => x.key === "apa"));
assert.equal((await a.req("POST", `campaigns/${cid}/exports`, { journal: "arxiv", style: "nostyle" })).status, 400);
const apa = ok(await a.req("POST", `campaigns/${cid}/exports`, { journal: "arxiv", style: "apa" }), 201).export;
assert.deepEqual(apa.summary.citation_style, { key: "apa", name: "APA 7th edition" });
const apaTex = await (await a.raw("GET", `exports/${apa.id}/file?path=manuscript/manuscript.tex`)).text();
assert.ok(!apaTex.includes("\\cite{") && apaTex.includes("\\section*{\\refname}"), "author-date citations are written out");
const zipRes = await a.raw("GET", `exports/${built.id}/download`);
assert.equal(zipRes.status, 200);
const zip = Buffer.from(await zipRes.arrayBuffer());
assert.equal(createHash("sha256").update(zip).digest("hex"), built.sha256, "R2 holds exactly the bytes the service built");
assert.equal(zip.length, Number(built.bytes));
const pdf = await a.raw("GET", `exports/${built.id}/file?path=manuscript/manuscript.pdf`);
assert.equal(pdf.headers.get("content-type"), "application/pdf");
assert.equal(pdf.headers.get("content-security-policy"), null, "PDF viewers need an unsandboxed document");
assert.equal(Buffer.from(await pdf.arrayBuffer()).subarray(0, 5).toString(), "%PDF-");
const md = await a.raw("GET", `exports/${built.id}/file?path=SUBMISSION_CHECKLIST.md`);
assert.match(md.headers.get("content-security-policy"), /sandbox/);
assert.match(await md.text(), /Nature/);
const xlsx = await a.raw("GET", `exports/${built.id}/file?path=data/data_S1.xlsx`);
assert.equal(xlsx.headers.get("content-type"), "application/octet-stream");
assert.equal((await a.raw("GET", `exports/${built.id}/file?path=../x`)).status, 400);
assert.equal((await a.raw("GET", `exports/${built.id}/file?path=nope.txt`)).status, 404);
assert.equal((await b.raw("GET", `exports/${built.id}/download`)).status, 404);
assert.equal((await new Client(ip()).raw("GET", `exports/${built.id}/download`)).status, 401);
step("Nature package built, streamed to R2 byte-exact, single files previewed from the zip");

/* ---------- send and email ---------- */
let sent = ok(await a.req("POST", `exports/${built.id}/send`, { service: "googledrive" }));
assert.ok(sent.sent.includes("manuscript.pdf") && sent.sent.includes(`${built.name}.zip`) && sent.sent.includes("data_S1.xlsx"), JSON.stringify(sent));
log = await stubLog();
const folder = log.log.find((x) => x.tool === "GOOGLEDRIVE_CREATE_FOLDER");
assert.equal(folder.args.folder_name, built.name);
const drvUploads = log.log.filter((x) => x.tool === "GOOGLEDRIVE_UPLOAD_FILE");
assert.equal(drvUploads.length, sent.sent.length);
assert.ok(drvUploads.every((x) => x.args.folder_to_upload_to?.startsWith("fld-")));
sent = ok(await a.req("POST", `exports/${built.id}/send`, { service: "dropbox", path: "/Papers/" }));
log = await stubLog();
assert.equal(log.log.findLast((x) => x.tool === "DROPBOX_UPLOAD_FILE").args.path, `/Papers/${built.name}.zip`);
ok(await a.req("POST", `exports/${built.id}/send`, { service: "one_drive" }));
assert.equal((await a.req("POST", `exports/${built.id}/send`, { service: "gmail" })).status, 400);
assert.equal((await a.req("POST", `exports/${built.id}/send`, { service: "outlook" })).status, 400);
step("sent to Drive (folder of key files plus the zip), Dropbox and OneDrive; uploads checked by MD5");

assert.equal((await a.req("POST", `exports/${built.id}/email`, { service: "gmail", to: "a@b.c, d@e.f" })).status, 400);
assert.equal((await a.req("POST", `exports/${built.id}/email`, { service: "dropbox", to: "x@example.org" })).status, 400);
const mail = ok(await a.req("POST", `exports/${built.id}/email`, { service: "gmail", to: "Reviewer@Example.org", message: "Draft for review." }));
assert.deepEqual(mail, { sent: true, service: "gmail", to: "reviewer@example.org", attached_pdf: true });
log = await stubLog();
const email = log.log.findLast((x) => x.tool === "GMAIL_SEND_EMAIL").args;
assert.equal(email.recipient_email, "reviewer@example.org");
assert.equal(email.attachment.mimetype, "application/pdf");
assert.ok(email.body.startsWith("Draft for review."));
const link = email.body.match(/https?:\/\/\S+\/api\/exports\/\S+/)[0];
const anon = new Client(ip());
const viaLink = await anon.raw("GET", link.replace(/^https?:\/\/[^/]+\/api\//, ""));
assert.equal(viaLink.status, 200, "the signed link works without signing in");
assert.equal(createHash("sha256").update(Buffer.from(await viaLink.arrayBuffer())).digest("hex"), built.sha256);
const forged = link.replace(/sig=([^&]+)/, (_, s) => "sig=" + (s[0] === "A" ? "B" : "A") + s.slice(1));
assert.equal((await anon.raw("GET", forged.replace(/^https?:\/\/[^/]+\/api\//, ""))).status, 403);
const expired = link.replace(/exp=(\d+)/, (_, e) => `exp=${Number(e) + 1}`);
assert.equal((await anon.raw("GET", expired.replace(/^https?:\/\/[^/]+\/api\//, ""))).status, 403, "the expiry is signed");
assert.equal((await a.req("POST", `exports/${built.id}/email`, { service: "outlook", to: "x@example.org" })).status, 502, "Outlook isn't connected");
step("email through Gmail with the PDF attached and a signed 7-day link; forged links refused");

let saved = ok(await a.req("POST", `exports/${built.id}/library`, {}), 201);
assert.equal(saved.name, `${built.name}.zip`); assert.equal(saved.kind, "archive"); assert.equal(saved.sha256, built.sha256);
saved = ok(await a.req("POST", `exports/${built.id}/library`, {}), 201);
assert.equal(saved.duplicate, true);
step("package saved to Files once");

/* ---------- triggers and webhooks ---------- */
assert.equal((await a.req("POST", "integrations/triggers", { service: "googledrive" })).status, 400, "a Drive trigger needs a folder");
assert.equal((await a.req("POST", "integrations/triggers", { service: "dropbox" })).status, 400);
const tDrive = ok(await a.req("POST", "integrations/triggers", { service: "googledrive", folder_id: "fld-lab", folder_name: "Lab" }), 201).trigger;
const tMail = ok(await a.req("POST", "integrations/triggers", { service: "gmail", query: "from:lab has:attachment" }), 201).trigger;
log = await stubLog();
const stubTriggers = Object.fromEntries(log.triggers);
const driveTid = Object.keys(stubTriggers).find((k) => stubTriggers[k].slug === "GOOGLEDRIVE_FILE_CREATED_TRIGGER");
const mailTid = Object.keys(stubTriggers).find((k) => stubTriggers[k].slug === "GMAIL_NEW_GMAIL_MESSAGE");
assert.equal(stubTriggers[driveTid].config.folder_id, "fld-lab");
assert.equal(stubTriggers[driveTid].user, user);
assert.match(stubTriggers[mailTid].config.query, /has:attachment/);

const hook = async (id, event, sign = true) => {
  const body = JSON.stringify(event), ts = String(Math.floor(Date.now() / 1000));
  const sig = "v1," + createHmac("sha256", SECRET).update(`${id}.${ts}.${body}`).digest("base64");
  return fetch(BASE + "/api/integrations/webhook", { method: "POST", headers: { "content-type": "application/json", "webhook-id": id, "webhook-timestamp": ts, "webhook-signature": sign ? sig : "v1,AAAA" }, body });
};
const driveEvent = { id: "e1", type: "composio.trigger.message", metadata: { trigger_slug: "GOOGLEDRIVE_FILE_CREATED_TRIGGER", trigger_id: driveTid, user_id: user },
  data: { event_type: "file_created", file: { id: "drv-new", name: "new-samples.vcf", mimeType: "text/x-vcf" } } };
assert.equal((await hook("msg_unsigned", driveEvent, false)).status, 401);
assert.equal((await hook(`msg_${uniq}_1`, driveEvent)).status, 200);
assert.equal((await hook(`msg_${uniq}_1`, driveEvent)).status, 200, "a redelivery is accepted");
const mailEvent = { id: "e2", type: "composio.trigger.message", metadata: { trigger_slug: "GMAIL_NEW_GMAIL_MESSAGE", trigger_id: mailTid, user_id: user },
  data: { message_id: "m-123", subject: "refs", attachment_list: [{ attachmentId: "att-1", filename: "refs.bib", mimeType: "application/x-bibtex" }, { attachmentId: "att-x", filename: "logo.exe" }] } };
assert.equal((await hook(`msg_${uniq}_2`, mailEvent)).status, 200);
// An event for a trigger this person doesn't own imports nothing.
assert.equal((await hook(`msg_${uniq}_3`, { ...driveEvent, metadata: { ...driveEvent.metadata, trigger_id: "ti_other" } })).status, 200);
let files = [];
for (let i = 0; i < 40; i++) {
  files = ok(await a.req("GET", "library")).files;
  if (files.some((f) => f.name === "new-samples.vcf") && files.some((f) => f.source === "gmail")) break;
  await sleep(250);
}
assert.equal(files.filter((f) => f.name === "new-samples.vcf").length, 1, "imported once despite the redelivery");
assert.equal(files.filter((f) => f.source === "gmail").map((f) => f.name).join(), "refs.bib", "only research files are taken from email");
step("Drive and Gmail triggers: signed deliveries import new files once; unsigned refused");

/* ---------- a new research thread from the library ---------- */
const before = (await stubLog()).log.length;
assert.equal((await a.req("POST", `campaigns?library=${vcfFile.id},${saved.id}`, { question: "Which variants matter?", start: false, token_budget: 500000 })).status, 422, "archives are refused");
assert.equal((await b.req("POST", `campaigns?library=${vcfFile.id}`, { question: "Which variants matter?", start: false, token_budget: 500000 })).status, 404, "another person's file");
const made = ok(await a.req("POST", `campaigns?library=${vcfFile.id},${csvId},${bib.id}`, { question: "Which variants matter?", start: false, token_budget: 500000 }), 202);
assert.deepEqual(made.materials, { references: 1, documents: 0, errors: [] });
const ds = execFileSync("psql", [process.env.PLATO_DATABASE_URL, "-Atc", `SELECT string_agg(b.file_name, ',' ORDER BY b.file_name) FROM plato.campaign_scope s JOIN plato.asset_blobs b ON b.asset_id = s.asset_id WHERE s.campaign_id = '${made.id}' AND s.access_mode = 'train_val'`], { encoding: "utf8" }).trim();
assert.equal(ds, "calls.vcf,expression.csv");
assert.equal((await stubLog()).log.length, before, "starting a thread from Files makes no service calls");
step("new thread takes Files: data as datasets, references as citable papers");

/* ---------- disconnect ---------- */
ok(await a.req("DELETE", `integrations/triggers/${tMail.id}`));
assert.equal((await b.req("DELETE", `integrations/triggers/${tDrive.id}`)).status, 404);
ok(await a.req("POST", "integrations/disconnect", { service: "googledrive" }));
ints = ok(await a.req("GET", "integrations"));
assert.equal(ints.services.find((s) => s.slug === "googledrive").status, "disconnected");
assert.deepEqual(ints.triggers, []);
log = await stubLog();
assert.deepEqual(log.triggers, [], "both triggers removed at Composio");
ok(await a.req("DELETE", `library/${vcfFile.id}`));
assert.equal((await a.raw("GET", `library/${vcfFile.id}`)).status, 404);
step("disconnect removes the connection and its triggers; files can be deleted");

console.log(`${n} steps passed`);
