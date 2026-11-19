// Unit checks for Worker modules that need no bindings: Composio webhook signatures and the
// ranged zip reader. Run: node e2e/unit.test.mjs  (bundles the TypeScript with esbuild first)
import assert from "node:assert/strict";
import { createHash, createHmac, randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import vm from "node:vm";
import zlib from "node:zlib";

const root = path.dirname(path.dirname(new URL(import.meta.url).pathname));
const out = fs.mkdtempSync(path.join(os.tmpdir(), "plato-unit-"));
execFileSync(path.join(root, "node_modules/.bin/esbuild"), [
  "--bundle", "--format=esm", "--platform=node", "--log-level=warning",
  `--outdir=${out}`, "--out-extension:.js=.mjs",
  path.join(root, "src/composio.ts"), path.join(root, "src/zip.ts"), path.join(root, "src/headers.ts"),
]);
const composio = await import(path.join(out, "composio.mjs"));
const zip = await import(path.join(out, "zip.mjs"));
const headers = await import(path.join(out, "headers.mjs"));
let n = 0;
const test = async (name, fn) => { await fn(); n++; console.log("·", name); };

// Workers have crypto.subtle.timingSafeEqual; Node's Web Crypto doesn't.
crypto.subtle.timingSafeEqual ??= (a, b) => a.byteLength === b.byteLength && Buffer.from(a).equals(Buffer.from(b));

/* ---------- webhook signatures (Standard Webhooks, keyed with the secret string) ---------- */
const secret = "whsec_" + randomBytes(24).toString("base64");
const sign = (id, ts, body, key = secret) => "v1," + createHmac("sha256", key).update(`${id}.${ts}.${body}`).digest("base64");
const now = 1_763_000_000_000;
const ts = String(now / 1000);
const body = JSON.stringify({ type: "composio.trigger.message", data: { a: 1 } });
const h = (sig, t = ts, id = "msg_1") => new Headers({ "webhook-id": id, "webhook-timestamp": t, "webhook-signature": sig });

await test("a valid signature verifies", async () => assert.equal(await composio.verifyWebhook(secret, h(sign("msg_1", ts, body)), body, now), true));
await test("one of several signatures may match", async () =>
  assert.equal(await composio.verifyWebhook(secret, h(`v1,AAAA ${sign("msg_1", ts, body)}`), body, now), true));
await test("a changed body fails", async () => assert.equal(await composio.verifyWebhook(secret, h(sign("msg_1", ts, body)), body + " ", now), false));
await test("a different message id fails", async () => assert.equal(await composio.verifyWebhook(secret, h(sign("msg_1", ts, body), ts, "msg_2"), body, now), false));
await test("the wrong secret fails", async () => assert.equal(await composio.verifyWebhook(secret, h(sign("msg_1", ts, body, "other")), body, now), false));
await test("deliveries older than 5 minutes are refused", async () => {
  const old = String(now / 1000 - 301);
  assert.equal(await composio.verifyWebhook(secret, h(sign("msg_1", old, body), old), body, now), false);
});
await test("missing or malformed headers are refused", async () => {
  assert.equal(await composio.verifyWebhook(secret, new Headers(), body, now), false);
  assert.equal(await composio.verifyWebhook(secret, h(sign("msg_1", "1e9", body), "1e9"), body, now), false);
});

/* ---------- inline bytes (Dropbox) ---------- */
await test("inline base64 decodes, plain text stays text", async () => {
  assert.deepEqual([...composio.inlineBytes(Buffer.from([0, 255, 1, 2]).toString("base64"))], [0, 255, 1, 2]);
  assert.equal(Buffer.from(composio.inlineBytes("a,b\n1,2\n")).toString(), "a,b\n1,2\n");
  assert.equal(composio.inlineBytes(42), null);
  // With the file size: "abcd" is a 4-byte text file, not base64 for 3 bytes, and the reverse.
  assert.equal(Buffer.from(composio.inlineBytes("abcd", 4)).toString(), "abcd");
  assert.equal(composio.inlineBytes("abcd", 3).byteLength, 3);
  assert.equal(Buffer.from(composio.inlineBytes("x\n", 2)).toString(), "x\n");
});

/* ---------- zip reader over ranged gets ---------- */
function makeZip(files, comment = "") {
  // Minimal PKZIP writer: stored and deflated entries, central directory, EOCD (+ comment).
  const crcTable = Array.from({ length: 256 }, (_, i) => { let c = i; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = (b) => { let c = 0xffffffff; for (const x of b) c = crcTable[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const parts = [], cds = []; let off = 0;
  for (const [name, data, deflate] of files) {
    const nm = Buffer.from(name), raw = Buffer.from(data), body = deflate ? zlib.deflateRawSync(raw) : raw;
    const lh = Buffer.alloc(30); lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(deflate ? 8 : 0, 8);
    lh.writeUInt32LE(crc(raw), 14); lh.writeUInt32LE(body.length, 18); lh.writeUInt32LE(raw.length, 22); lh.writeUInt16LE(nm.length, 26);
    const extra = Buffer.from([0xfe, 0xca, 0, 0]); lh.writeUInt16LE(extra.length, 28);   // local extra field, as some writers add
    const cd = Buffer.alloc(46); cd.writeUInt32LE(0x02014b50, 0); cd.writeUInt16LE(20, 4); cd.writeUInt16LE(20, 6); cd.writeUInt16LE(deflate ? 8 : 0, 10);
    cd.writeUInt32LE(crc(raw), 16); cd.writeUInt32LE(body.length, 20); cd.writeUInt32LE(raw.length, 24); cd.writeUInt16LE(nm.length, 28); cd.writeUInt32LE(off, 42);
    parts.push(lh, nm, extra, body); cds.push(cd, nm); off += 30 + nm.length + extra.length + body.length;
  }
  const cdBuf = Buffer.concat(cds), cm = Buffer.from(comment), e = Buffer.alloc(22);
  e.writeUInt32LE(0x06054b50, 0); e.writeUInt16LE(files.length, 8); e.writeUInt16LE(files.length, 10); e.writeUInt32LE(cdBuf.length, 12); e.writeUInt32LE(off, 16); e.writeUInt16LE(cm.length, 20);
  return Buffer.concat([...parts, cdBuf, e, cm]);
}
const bucketOf = (buf) => {
  const gets = [];
  return { gets, async get(_key, opt) { const { offset, length } = opt.range; gets.push(length); assert.ok(offset >= 0 && offset + length <= buf.length, "range inside the object"); return { arrayBuffer: async () => buf.subarray(offset, offset + length) }; } };
};

await test("entries are listed and read back exactly (stored and deflated)", async () => {
  const big = randomBytes(200_000).toString("hex");
  const buf = makeZip([["pkg/README.md", "# hello\n", false], ["pkg/data/findings.csv", big, true], ["pkg/manuscript/ü.tex", "\\documentclass{article}", true]], "a comment");
  const b = bucketOf(buf);
  const list = await zip.entries(b, "k", buf.length);
  assert.deepEqual(list.map((e) => e.name), ["pkg/README.md", "pkg/data/findings.csv", "pkg/manuscript/ü.tex"]);
  assert.equal(Buffer.from(await zip.readEntry(b, "k", list[0])).toString(), "# hello\n");
  assert.equal(Buffer.from(await zip.readEntry(b, "k", list[1])).toString(), big);
  assert.equal(Buffer.from(await zip.readEntry(b, "k", list[2])).toString(), "\\documentclass{article}");
  assert.ok(Math.max(...b.gets) < buf.length, "never reads the whole archive in one get");
});
await test("a zip made by Python's zipfile reads back", async () => {
  const py = execFileSync("python3", ["-c", "import io,zipfile,sys\nb=io.BytesIO()\nz=zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED)\nz.writestr('p/a.txt','x'*5000)\nz.writestr('p/b.bin',bytes(range(256))*10)\nz.close()\nsys.stdout.buffer.write(b.getvalue())"]);
  const b = bucketOf(py), list = await zip.entries(b, "k", py.length);
  assert.equal(Buffer.from(await zip.readEntry(b, "k", list.find((e) => e.name === "p/a.txt"))).toString(), "x".repeat(5000));
  assert.equal((await zip.readEntry(b, "k", list.find((e) => e.name === "p/b.bin"))).byteLength, 2560);
});
await test("not a zip is an error", async () => {
  const buf = Buffer.from("definitely not a zip file, just text");
  await assert.rejects(zip.entries(bucketOf(buf), "k", buf.length), /not a zip/);
});

/* ---------- security headers ---------- */
await test("API JSON gets the security headers and a CSP that allows nothing", async () => {
  const r = headers.withSecurityHeaders(new Response("{}", { status: 404, headers: { "content-type": "application/json; charset=utf-8" } }));
  assert.equal(r.status, 404);
  assert.equal(r.headers.get("content-security-policy"), "default-src 'none'; frame-ancestors 'none'");
  assert.equal(r.headers.get("x-frame-options"), "SAMEORIGIN");
  assert.equal(r.headers.get("x-content-type-options"), "nosniff");
  assert.match(r.headers.get("strict-transport-security"), /^max-age=\d{8,}/);
  assert.equal(r.headers.get("referrer-policy"), "strict-origin-when-cross-origin");
});
await test("a handler's own CSP wins and file responses get no JSON CSP", async () => {
  const own = headers.withSecurityHeaders(new Response("x", { headers: { "content-type": "text/plain", "content-security-policy": "default-src 'none'; sandbox" } }));
  assert.equal(own.headers.get("content-security-policy"), "default-src 'none'; sandbox");
  const pdf = headers.withSecurityHeaders(new Response("x", { headers: { "content-type": "application/pdf" } }));
  assert.equal(pdf.headers.get("content-security-policy"), null);
  assert.equal(pdf.headers.get("x-content-type-options"), "nosniff");
});
await test("public/_headers allows exactly the inline scripts in index.html", async () => {
  const html = fs.readFileSync(path.join(root, "public/index.html"), "utf8");
  const rules = fs.readFileSync(path.join(root, "public/_headers"), "utf8");
  const csp = rules.match(/^\s+Content-Security-Policy: (.+)$/m)[1];
  const scriptSrc = csp.split(";").map((d) => d.trim()).find((d) => d.startsWith("script-src ")).split(" ").slice(1);
  const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => `'sha256-${createHash("sha256").update(m[1]).digest("base64")}'`);
  assert.ok(inline.length > 0);
  assert.deepEqual(scriptSrc.filter((s) => s.startsWith("'sha256-")).sort(), inline.sort());
  assert.ok(!scriptSrc.includes("'unsafe-inline'") && !scriptSrc.includes("'unsafe-eval'"));
  assert.doesNotMatch(html, /\son[a-z]+="/i, "inline event handlers would be blocked by the CSP");
});

/* ---------- experiment designs (public/app/spec.js): labelled fields, never raw JSON ---------- */
{
  const sandbox = { globalThis: {} };
  vm.runInNewContext(fs.readFileSync(path.join(root, "public/app/spec.js"), "utf8"), sandbox);
  const Spec = sandbox.globalThis.PlatoSpec;
  // The stored text of a real intent the app showed raw; the Python reader uses the same file.
  const stored = fs.readFileSync(path.join(root, "../../tests/scientist/fixtures/intent_design.json"), "utf8").trim();
  const design = JSON.parse(stored);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  const plain = (o) => JSON.parse(JSON.stringify(o));
  await test("a stored design parses to its fields", async () => assert.deepEqual(plain(Spec.parse(stored)), design));
  await test("a design renders as labelled fields, not JSON", async () => {
    const html = Spec.html(stored, esc);
    assert.match(html, /^<dl class="xp-spec">/);
    for (const [label, value] of [["Hypothesis", design.hypothesis], ["Protocol", design.protocol], ["Success criterion", design.success_criterion],
      ["Primary metric", "bias_without_pathology_in_se_units"], ["Test", "difference"]])
      assert.ok(html.includes(`<dt>${label}</dt><dd>${esc(value)}</dd>`), label);
    assert.doesNotMatch(html, /[{}]|&#34;hypothesis&#34;|"hypothesis"/);
  });
  await test("a design encoded twice still parses", async () => assert.deepEqual(plain(Spec.parse(JSON.stringify(stored))), design));
  await test("a design nested in the hypothesis field is unwrapped", async () => {
    const got = plain(Spec.parse(JSON.stringify({ hypothesis: stored, primary_metric: "x" })));
    assert.deepEqual(got, { ...design, primary_metric: "x" });
  });
  await test("plain node text stays a paragraph", async () => {
    for (const t of ["Sample observation text for the claim.", "{Braces} in prose", "[1,2]", '{"title":"x"}', "{not json"]) {
      assert.equal(Spec.parse(t), null, t);
      assert.equal(Spec.html(t, esc), `<div class="para">${esc(t)}</div>`);
    }
    assert.equal(Spec.html("", esc), "");
    assert.deepEqual(plain(Spec.of("A claim.")), { hypothesis: "A claim." });
    assert.deepEqual(plain(Spec.of(null)), {});
  });
  await test("field values are escaped", async () =>
    assert.ok(Spec.html(JSON.stringify({ hypothesis: "<img src=x onerror=1>" }), esc).includes("&#60;img")));
}

fs.rmSync(out, { recursive: true, force: true });
console.log(`${n} passed`);
