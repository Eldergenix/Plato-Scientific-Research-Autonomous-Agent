// End-to-end API test against wrangler dev + the local Python service + the stub Messages API.
// Run: node e2e/api.test.mjs /tmp/stub-requests.jsonl  (the stub's request log, truncated at start)
import assert from "node:assert/strict";
import fs from "node:fs";
const BASE = process.env.PLATO_E2E_BASE || "http://127.0.0.1:8787";
// These tests sign up accounts and use the dev admin token: local wrangler dev only.
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE)) throw new Error("PLATO_E2E_BASE must be a local wrangler dev URL");
const B = BASE + "/api/";
const ORIGIN = BASE;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
class Client {
  constructor(ip) { this.cookie = ""; this.ip = ip; }
  async req(method, path, body, extra = {}) {
    const headers = { origin: ORIGIN, "cf-connecting-ip": this.ip, ...(this.cookie ? { cookie: this.cookie } : {}), ...extra };
    if (body !== undefined) headers["content-type"] = "application/json";
    const r = await fetch(B + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    const sc = r.headers.getSetCookie?.() ?? [];
    for (const c of sc) { const v = c.split(";")[0]; this.cookie = v.endsWith("=") ? "" : v; if (c.includes("Max-Age=0")) this.cookie = ""; }
    let data = null; const t = await r.text(); try { data = JSON.parse(t) } catch { data = t }
    return { status: r.status, data, setCookie: sc };
  }
}
const uniq = Date.now().toString(36);
fs.writeFileSync(process.argv[2], "");
const a = new Client("10.0.0." + (Math.floor(Math.random() * 200) + 1));
const b = new Client("10.0.1." + (Math.floor(Math.random() * 200) + 1));
const ok = (r, s = 200) => { assert.equal(r.status, s, JSON.stringify(r.data)); return r.data; };

// Unauthenticated
assert.deepEqual(ok(await a.req("GET", "me")), { account: null });   // signed out: not an error
assert.equal((await a.req("GET", "campaigns")).status, 401);
assert.equal((await a.req("GET", "me", undefined, { cookie: "__Host-plato_session=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" })).status, 200);
// Cross-origin write refused
assert.equal((await a.req("POST", "auth/login", { email: "x@y.z", password: "p" }, { origin: "https://evil.example" })).status, 403);
// Non-JSON refused
const form = await fetch(B + "auth/signup", { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: "email=a" });
assert.equal(form.status, 415);
// Validation
assert.equal((await a.req("POST", "auth/signup", { email: "bad", password: "longenough1" })).status, 400);
assert.equal((await a.req("POST", "auth/signup", { email: `a-${uniq}@example.org`, password: "short" })).status, 400);
// Sign up A
const su = await a.req("POST", "auth/signup", { email: `A-${uniq}@Example.org`, password: "correct horse battery", name: "Ada" });
ok(su, 201);
const ck = su.setCookie[0];
assert.match(ck, /^__Host-plato_session=[A-Za-z0-9_-]{43}; Path=\/; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax$/);
let me = ok(await a.req("GET", "me"));
assert.equal(me.account.email, `a-${uniq}@example.org`);
assert.equal(me.account.name, "Ada");
assert.equal(me.account.is_admin, false);
assert.deepEqual(me.allowance, { cap: 1500000, committed: 0, own_key: false });
// Models: Opus 5.5 orchestrates, Haiku 5.5 sub-agents; Opus tokens count 40x against the allowance.
assert.equal(me.models.orchestrator, "claude-opus-5-5");
assert.equal(me.models.workers, "claude-haiku-5-5");
assert.deepEqual(me.models.weights, { "claude-opus-5-5": 40, "claude-haiku-5-5": 1 });
assert.equal(me.key, null);
assert.equal((await b.req("POST", "auth/signup", { email: `a-${uniq}@example.org`, password: "another password" })).status, 409);
// Preferences
ok(await a.req("PATCH", "me", { preferences: { theme: "light", compact_grid: true }, name: "Ada L" }));
assert.equal((await a.req("PATCH", "me", { preferences: { evil: 1 } })).status, 400);
assert.equal((await a.req("PATCH", "me", { preferences: { theme: "neon" } })).status, 400);
me = ok(await a.req("GET", "me"));
assert.deepEqual(me.account.preferences, { theme: "light", compact_grid: true });
assert.equal(me.account.name, "Ada L");
// Logout / login
ok(await a.req("POST", "auth/logout"));
assert.equal(a.cookie, "");
assert.deepEqual(ok(await a.req("GET", "me")), { account: null });
assert.equal((await a.req("GET", "projects")).status, 401);
assert.equal((await a.req("POST", "auth/login", { email: `a-${uniq}@example.org`, password: "wrong password!" })).status, 401);
assert.equal((await a.req("POST", "auth/login", { email: `nobody-${uniq}@example.org`, password: "wrong password!" })).status, 401);
ok(await a.req("POST", "auth/login", { email: `A-${uniq}@example.org`, password: "correct horse battery" }));
// Own key: bad format, rejected by Anthropic, accepted
assert.equal((await a.req("PUT", "me/key", { key: "nope" })).status, 400);
assert.equal((await a.req("PUT", "me/key", { key: "sk-ant-bad-key-000000000000000000000" })).status, 422);
const k = ok(await a.req("PUT", "me/key", { key: "sk-ant-api03-ownkeyownkeyownkey-ABCD" }));
assert.equal(k.key.last4, "ABCD");
me = ok(await a.req("GET", "me"));
assert.equal(me.key.last4, "ABCD");
assert.ok(!JSON.stringify(me).includes("ownkeyownkey"), "key never echoed");
assert.deepEqual(me.allowance.own_key, true);
ok(await a.req("DELETE", "me/key"));
assert.equal(ok(await a.req("GET", "me")).key, null);
// Sign up B
ok(await b.req("POST", "auth/signup", { email: `b-${uniq}@example.org`, password: "bbbbbbbbbbbb" }), 201);
// Projects: A asks for research; the agent starts a thread
const pr = ok(await a.req("POST", "projects", { text: "Please research whether OLS intervals keep coverage under heteroskedasticity." }), 201);
const pid = pr.id;
let proj;
for (let i = 0; i < 60; i++) { proj = ok(await a.req("GET", `projects/${pid}`)); if (proj.project.agent_status !== "working") break; await sleep(250); }
assert.equal(proj.project.agent_status, "idle", JSON.stringify(proj.project));
assert.equal(proj.project.title, "Please research whether OLS intervals keep coverage under heteroskedasticity.");
const roles = proj.messages.map((m) => m.role).join(",");
assert.equal(roles, "user,assistant,user,assistant");
assert.ok(proj.messages.every((m) => m.content.every((b) => b.type !== "thinking")), "thinking hidden from UI");
const use = proj.messages[1].content.find((b) => b.type === "tool_use");
assert.equal(use.name, "start_research_thread");
assert.equal(proj.threads.length, 1);
const tid = proj.threads[0].id;
assert.equal(proj.threads[0].token_budget_max, 400000);
// The model saw its own thinking replayed unchanged (append-only history).
const reqs = fs.readFileSync(process.argv[2], "utf8").trim().split("\n").map((l) => JSON.parse(l)).filter((r) => r.body.messages[0].content[0].text?.includes("OLS intervals"));
assert.equal(reqs.length, 2);
assert.deepEqual(reqs[1].body.messages.slice(0, 1), reqs[0].body.messages);
assert.equal(reqs[1].body.messages[1].content[0].type, "thinking");
assert.ok(reqs[1].body.messages[1].content[0].signature.startsWith("sig-"));
assert.equal(reqs[0].body.system[0].text, reqs[1].body.system[0].text);
assert.equal(reqs[0].body.output_config.effort, "medium");
assert.equal(reqs[0].key, "0000", "default key used");
assert.equal(reqs[0].body.model, "claude-opus-5-5");
assert.equal(reqs[0].body.fallbacks, "default");
assert.match(reqs[0].beta, /server-side-fallback-2026-07-01/);
assert.ok(!("temperature" in reqs[0].body) && !("thinking" in reqs[0].body));
// Thread visible to A (campaign routes), not to B
ok(await a.req("GET", `campaigns/${tid}`));
assert.equal((await b.req("GET", `campaigns/${tid}`)).status, 404);
assert.equal((await b.req("GET", `campaigns/${tid}/graph`)).status, 404);
assert.equal((await b.req("POST", `campaigns/${tid}/run`)).status, 404);
assert.equal((await b.req("GET", `projects/${pid}`)).status, 404);
assert.equal((await b.req("POST", `projects/${pid}/messages`, { text: "hi" })).status, 404);
const listA = ok(await a.req("GET", "campaigns")).campaigns.map((c) => c.id);
const listB = ok(await b.req("GET", "campaigns")).campaigns.map((c) => c.id);
assert.ok(listA.includes(tid) && !listB.includes(tid));
assert.equal(listB.length, 0, "B sees none of the legacy (unowned) campaigns");
// Allowance: committed includes the running thread's reserved budget
me = ok(await a.req("GET", "me"));
// plus the agent's two Opus calls: 2 x (1200 + 300) tokens x 40.
assert.ok(me.allowance.committed >= 400000 + 120000, JSON.stringify(me.allowance));
// A direct campaign over the remaining allowance is refused with 402
const big = await a.req("POST", "campaigns", { question: "Does y exceed 2?", token_budget: 2000000, start: false });
assert.equal(big.status, 402, JSON.stringify(big.data));
assert.match(big.data.error, /left this month/);
const small = ok(await a.req("POST", "campaigns", { question: "Does y exceed 2?", token_budget: 200000, start: false }), 202);
// Follow-up with context, then a status question that uses list_threads
ok(await a.req("POST", `projects/${pid}/messages`, { text: "what's the status?", context: { campaign_id: tid } }), 201);
const busy = await a.req("POST", `projects/${pid}/messages`, { text: "again" });
assert.ok(busy.status === 409 || busy.status === 201, String(busy.status));
for (let i = 0; i < 60; i++) { proj = ok(await a.req("GET", `projects/${pid}`)); if (proj.project.agent_status !== "working") break; await sleep(250); }
const after = proj.messages.at(-1).id;
assert.equal(ok(await a.req("GET", `projects/${pid}?after=${after}`)).messages.length, 0);
const ctxMsg = proj.messages.find((m) => m.role === "user" && m.content.some((b) => b.type === "text" && b.text.startsWith("<context>")));
assert.ok(ctxMsg, "context block stored");
// Context naming another person's thread is dropped
ok(await b.req("POST", "projects", { text: "hello there", context: { campaign_id: tid } }), 201);
const pb = ok(await b.req("GET", "projects")).projects[0];
const pbd = ok(await b.req("GET", `projects/${pb.id}`));
assert.ok(!JSON.stringify(pbd.messages[0]).includes("<context>"));
// Projects list, rename, delete
const plist = ok(await a.req("GET", "projects")).projects;
assert.equal(plist[0].id, pid);
assert.equal(plist[0].threads, 1);
assert.equal(plist[0].active, 1);
ok(await a.req("PATCH", `projects/${pid}`, { title: "Coverage study" }));
// Own key: the agent and the thread it starts run on it, uncapped
ok(await a.req("PUT", "me/key", { key: "sk-ant-api03-ownkeyownkeyownkey-WXYZ" }));
const p2 = ok(await a.req("POST", "projects", { text: "Investigate a 5M token question please" }), 201).id;
let pj;
for (let i = 0; i < 60; i++) { pj = ok(await a.req("GET", `projects/${p2}`)); if (pj.project.agent_status !== "working") break; await sleep(250); }
assert.equal(pj.project.agent_status, "idle", JSON.stringify(pj.project));
const ownReqs = fs.readFileSync(process.argv[2], "utf8").trim().split("\n").map((l) => JSON.parse(l)).filter((r) => r.body.messages[0].content.at(-1).text?.includes("5M token"));
assert.ok(ownReqs.length >= 1 && ownReqs.every((r) => r.key === "WXYZ"), JSON.stringify(ownReqs.map((r) => r.key)));
const t2 = pj.threads[0];
const t2row = ok(await a.req("GET", `campaigns/${t2.id}`)).campaign;
assert.equal(t2row.own_key, true);
const bigOwn = await a.req("POST", "campaigns", { question: "Does y exceed 2?", token_budget: 5000000, start: false });
assert.equal(bigOwn.status, 202, "own key is not capped");
ok(await a.req("DELETE", "me/key"));
// Admin: claim with wrong / right token
assert.equal((await a.req("GET", "admin/accounts")).status, 403);
assert.equal((await a.req("POST", "me/admin", { token: "nope" })).status, 403);
ok(await a.req("POST", "me/admin", { token: "dev" }));
const accts = ok(await a.req("GET", "admin/accounts"));
assert.ok(accts.accounts.length >= 2);
const bId = accts.accounts.find((x) => x.email === `b-${uniq}@example.org`).id;
ok(await a.req("PATCH", `admin/accounts/${bId}`, { monthly_token_cap: 123 }));
assert.equal(ok(await b.req("GET", "me")).allowance.cap, 123);
assert.equal((await a.req("PATCH", `admin/accounts/${accts.accounts.find((x) => x.email.startsWith("a-" + uniq)).id}`, { is_admin: false })).status, 400);
// Admin now sees legacy campaigns too
assert.ok(ok(await a.req("GET", "campaigns")).campaigns.length > listA.length);
// Sessions and password change
const a2 = new Client(a.ip);
ok(await a2.req("POST", "auth/login", { email: `a-${uniq}@example.org`, password: "correct horse battery" }));
const sess = ok(await a.req("GET", "me/sessions")).sessions;
assert.equal(sess.length, 2);
assert.equal(sess.filter((s) => s.current).length, 1);
assert.equal((await a.req("POST", "me/password", { current: "wrong", password: "a brand new password" })).status, 403);
ok(await a.req("POST", "me/password", { current: "correct horse battery", password: "a brand new password" }));
assert.deepEqual(ok(await a2.req("GET", "me")), { account: null }, "other session revoked");
assert.equal((await a2.req("GET", "projects")).status, 401, "revoked session refused");
ok(await a.req("GET", "me"));
// Bearer token still works (scripts) and is admin; it has no account for projects
const bearer = await fetch(B + "health", { headers: { authorization: "Bearer dev" } });
assert.equal(bearer.status, 200);
assert.equal((await fetch(B + "projects", { headers: { authorization: "Bearer dev" } })).status, 403);
assert.equal((await fetch(B + "health", { headers: { authorization: "Bearer nope" } })).status, 401);
// Delete account B
assert.equal((await b.req("DELETE", "me", { password: "wrong" })).status, 403);
ok(await b.req("DELETE", "me", { password: "bbbbbbbbbbbb" }));
assert.deepEqual(ok(await b.req("GET", "me")), { account: null });
assert.equal((await b.req("GET", "projects")).status, 401);
// Login throttling by email: 10 failures, then 429
const c = new Client("10.9.9." + (Math.floor(Math.random() * 200) + 1));
let last;
for (let i = 0; i < 11; i++) last = await c.req("POST", "auth/login", { email: `a-${uniq}@example.org`, password: "guess " + i + "xxxxx" });
assert.equal(last.status, 429);
console.log("API OK", { pid, tid, small: small.id });
