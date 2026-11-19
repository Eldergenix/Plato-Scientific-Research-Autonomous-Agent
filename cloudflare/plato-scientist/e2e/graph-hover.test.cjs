// Hover on graph lines: in the campaign Graph tab and the Data tab network (2D SVG and 3D canvas), hovering a node marks
// its lines and hovering a line marks that line; marked lines are the accent blue, dashed and flowing, and still (no flow)
// with reduced motion (OS setting or the app's Reduce motion preference). Self-contained: serves public/ with a mocked API.
//   node e2e/graph-hover.test.cjs public <screenshot dir>       env: THEME=dark|light MOTION=no-preference|reduce PREF=1
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), http = require("http");
const ROOT = process.argv[2] || path.join(__dirname, "../public"), OUT = process.argv[3] || ".", MOTION = process.env.MOTION || "no-preference", THEME = process.env.THEME || "dark";
const t = new Date().toISOString(), C = "11111111-1111-4111-8111-111111111111";
const N = (id, type, status, title) => ({ id, node_type: type, status, title, metrics: {}, created_at: t, hypothesis_or_spec: "" });
const nodes = [N("g", "goal", "open", "Does HC3 restore coverage?"), N("i1", "intent", "verified", "Simulate coverage under heteroskedastic errors"), N("i2", "intent", "verified", "Compare bootstrap intervals"),
  N("f1", "fact", "verified", "Classical coverage falls to 0.89"), N("f2", "fact", "verified", "HC3 restores coverage"), N("f3", "fact", "refuted", "Bootstrap undercovers at n=20"), N("fd", "finding", "verified", "HC3 is the safe default")];
const edges = [["g", "i1", "decomposes"], ["g", "i2", "decomposes"], ["i1", "f1", "yields"], ["i1", "f2", "yields"], ["i2", "f3", "yields"], ["f2", "fd", "proves"], ["f3", "fd", "refutes"]].map(([s, tt, e], k) => ({ id: "e" + k, source_node_id: s, target_node_id: tt, edge_type: e }));
const campaign = { id: C, research_question: "Does HC3 restore coverage?", status: "completed", tokens_used: 1, token_budget_max: 10, gpu_seconds_used: 0, gpu_seconds_max: 1, created_at: t, updated_at: t, program_domain: "statistics", config: {} };
const SIF = "TP53\tactivates\tMDM2\nMDM2\tinhibits\tTP53\nTP53\tactivates\tCDKN1A\nCDKN1A\tinhibits\tCDK2\nCDK2\tbinds\tCCNE1\nATM\tactivates\tTP53\nATM\tactivates\tCHEK2\nCHEK2\tactivates\tTP53\nTP53\tactivates\tBAX\nBAX\tbinds\tBCL2\n";
const files = [{ id: "file1", node_id: "f1", file_name: "p53_pathway.sif", evidence_type: "data_file", created_at: t, size_bytes: SIF.length }];
const api = p => {
  if (p === "me") return { account: { id: "a", name: "Test", email: "t@example.com", preferences: { theme: THEME, home: "campaigns", reduce_motion: process.env.PREF === "1" } }, models: {}, key: {}, allowance: {} };
  if (p === "health") return { model: "m" };
  if (p === "campaigns") return { campaigns: [campaign] };
  if (p === "projects") return { projects: [] };
  if (p === `campaigns/${C}`) return { campaign, node_counts: [], guard_events: [] };
  if (p === `campaigns/${C}/graph`) return { nodes, edges };
  if (p === `campaigns/${C}/files`) return { files };
  if (p === `campaigns/${C}/usage`) return { points: [] };
  return null;
};
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2" };
const srv = http.createServer((q, r) => { const u = decodeURIComponent(q.url.split("?")[0]);
  if (u.startsWith("/api/")) { const p = u.slice(5); if (p === "evidence/file1") { r.writeHead(200, { "content-type": "text/plain" }); return r.end(SIF); }
    const b = api(p); r.writeHead(b ? 200 : 404, { "content-type": "application/json" }); return r.end(JSON.stringify(b || { error: "nf " + p })); }
  let f = path.join(ROOT, u === "/" ? "index.html" : u); if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(ROOT, "index.html");
  r.writeHead(200, { "content-type": types[path.extname(f)] || "application/octet-stream" }); fs.createReadStream(f).pipe(r); }).listen(8799);
const RED = MOTION === "reduce" || process.env.PREF === "1";
const fail = m => { throw new Error(m); };
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: THEME, reducedMotion: MOTION, deviceScaleFactor: +(process.env.SCALE || 1) });
  const pg = await ctx.newPage(); const errs = []; pg.on("console", m => m.type() === "error" && errs.push(m.text())); pg.on("pageerror", e => errs.push(String(e)));
  const anim = sel => pg.$eval(sel, el => { const cs = getComputedStyle(el); return { stroke: cs.stroke, dash: cs.strokeDasharray, anim: cs.animationName, play: cs.animationName !== "none" && el.getAnimations().length, w: cs.strokeWidth }; });
  const accent = async () => pg.evaluate(() => { const d = document.createElement("i"); d.style.color = "var(--accent)"; document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c; });
  // 1. campaign Graph tab
  await pg.goto(`http://127.0.0.1:8799/#/c/${C}/graph`); await pg.waitForSelector(".gcanvas .ge",{state:"attached"}); await pg.waitForTimeout(600);
  const acc = await accent();
  await pg.hover('.gn[data-node="i1"]'); await pg.waitForTimeout(400);
  const hotN = await pg.$$eval(".ge-ln.edge-hot", l => l.map(x => x.parentNode.dataset.s + ">" + x.parentNode.dataset.t).sort());
  console.log("graph node hover hot:", hotN); if (hotN.join() !== "g>i1,i1>f1,i1>f2") fail("graph node hover edges wrong");
  const st = await anim(".ge-ln.edge-hot"); console.log("style", st, "accent", acc);
  if (st.stroke !== acc || st.dash.replace(/px/g, "") !== "5, 3") fail("not accent dashed");
  if (RED ? st.anim !== "none" : st.anim !== "edge-flow") fail("animation state wrong for " + MOTION);
  await pg.screenshot({ path: `${OUT}/graph-node-${THEME}-${MOTION}.png`, clip: { x: 230, y: 40, width: 1000, height: 420 } });
  // edge hover: mid-point of the f3>fd path
  const mid = await pg.$eval('.ge[data-s="f3"] .ge-hit', p => { const L = p.getTotalLength(), q = p.getPointAtLength(L / 2), m = p.getScreenCTM(); return [q.x * m.a + m.e, q.y * m.d + m.f]; });
  await pg.mouse.move(mid[0], mid[1]); await pg.waitForTimeout(400);
  const hotE = await pg.$$eval(".ge-ln.edge-hot", l => l.map(x => x.parentNode.dataset.s + ">" + x.parentNode.dataset.t)); const nb = await pg.$$eval(".gn.nb", l => l.map(x => x.dataset.node).sort());
  console.log("graph edge hover:", hotE, nb); if (hotE.join() !== "f3>fd" || nb.join() !== "f3,fd") fail("graph edge hover wrong");
  await pg.screenshot({ path: `${OUT}/graph-edge-${THEME}-${MOTION}.png`, clip: { x: 230, y: 40, width: 1000, height: 420 } });
  await pg.mouse.move(5, 880); await pg.waitForTimeout(200); if (await pg.$$eval(".edge-hot,.gn.nb", l => l.length)) fail("graph not cleared on leave");
  // 2. Data tab network 2D
  await pg.goto(`http://127.0.0.1:8799/#/c/${C}/data/file1`); await pg.waitForSelector(".dv-net svg [data-n]",{state:"attached"}); await pg.waitForTimeout(400);
  const tp = await pg.$eval(".dv-net svg [data-n]", () => [...document.querySelectorAll(".dv-net [data-n] text")].find(x => x.textContent === "TP53").parentNode.dataset.n);
  await pg.hover(`.dv-net [data-n="${tp}"] circle:not(.hit)`); await pg.waitForTimeout(400);
  const n2 = await pg.$$eval(".dv-edges line.edge-hot", l => l.length); console.log("2D TP53 hot edges", n2); if (n2 !== 6) fail("2D node hover should mark 6 lines");
  const s2 = await anim(".dv-edges line.edge-hot"); console.log("2D style", s2); if (s2.stroke !== acc) fail("2D not accent");
  if (RED ? s2.anim !== "none" : s2.anim !== "edge-flow") fail("2D anim state wrong");
  const mk = await pg.$eval(".dv-edges line.edge-hot.k-act", el => getComputedStyle(el).markerEnd); console.log("marker", mk); if (!mk.includes("dvAh")) fail("accent arrowhead missing");
  await pg.screenshot({ path: `${OUT}/net2d-node-${THEME}-${MOTION}.png`, clip: { x: 230, y: 40, width: 1200, height: 700 } });
  const hm = await pg.$eval('.dv-ehit [data-h="9"]', l => { const b = l.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; });
  await pg.mouse.move(hm[0], hm[1]); await pg.waitForTimeout(300);
  const e2 = await pg.$$eval(".dv-edges line.edge-hot", l => l.map(x => x.dataset.e)); const tip = await pg.$eval(".dv-tip", x => x.hidden ? "" : x.textContent);
  console.log("2D edge hover", e2, tip); if (e2.join() !== "9" || !tip.includes("BAX")) fail("2D edge hover wrong");
  await pg.screenshot({ path: `${OUT}/net2d-edge-${THEME}-${MOTION}.png`, clip: { x: 230, y: 40, width: 1200, height: 700 } });
  // 3. network 3D
  await pg.click('[data-ddim="3d"]'); await pg.waitForSelector(".dv-net canvas"); await pg.waitForTimeout(500);
  const cb = await pg.$eval(".dv-net canvas", c => { const b = c.getBoundingClientRect(); return [b.x, b.y, b.width, b.height]; });
  // find a node: scan for the tooltip
  let found = false;
  for (let y = 20; y < cb[3] && !found; y += 8) for (let x = 20; x < cb[2] && !found; x += 8) { await pg.mouse.move(cb[0] + x, cb[1] + y); if (await pg.$eval(".dv-tip", t => !t.hidden && /degree/.test(t.textContent))) found = true; }
  if (!found) fail("3D: no node found");
  const px = async () => pg.$eval(".dv-net canvas", c => { const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data; let n = 0, h = 0; for (let i = 0; i < d.length; i += 4) { if (d[i + 3] > 200 && d[i] < 40 && d[i + 1] > 120 && d[i + 1] < 170 && d[i + 2] > 220) n++; } for (let i = 0; i < d.length; i += 1) h = (h * 31 + d[i]) | 0; return [n, h]; });
  const a1 = await px(); await pg.waitForTimeout(250); const a2 = await px();
  console.log("3D accent px / frame hash", a1, a2); if (a1[0] < 20) fail("3D: no accent line pixels");
  if (RED ? a1[1] !== a2[1] : a1[1] === a2[1]) fail("3D: flow state wrong for " + MOTION);
  await pg.screenshot({ path: `${OUT}/net3d-${THEME}-${MOTION}.png`, clip: { x: 230, y: 40, width: 1200, height: 700 } });
  if (errs.length) fail("console errors: " + errs.join(" | "));
  console.log("PASS", THEME, MOTION); await b.close(); srv.close();
})().catch(e => { console.error("FAIL", e.message); process.exit(1); });
