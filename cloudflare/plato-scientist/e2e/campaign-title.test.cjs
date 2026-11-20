// Campaign title on the Overview: the full research question is the h1, at body size (13px), clamped to two lines with a
// "Show more" / "Show less" button only when it overflows; the button is keyboard operable, reports aria-expanded, keeps its
// state across re-renders and appears or hides as the width changes. Self-contained: serves public/ with a mocked API.
//   node e2e/campaign-title.test.cjs public <screenshot dir>       env: THEME=dark|light
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), http = require("http");
const ROOT = process.argv[2] || path.join(__dirname, "../public"), OUT = process.argv[3] || ".", THEME = process.env.THEME || "dark";
const t = new Date().toISOString(), LONG = "11111111-1111-4111-8111-111111111111", SHORT = "22222222-2222-4222-8222-222222222222", MID = "33333333-3333-4333-8333-333333333333";
const Q_LONG = `Does the difference between excitatory-neuron and mature-oligodendrocyte genetic effects on alternative polyadenylation (3'UTR long-isoform usage) change with donor age in aged human cortex single-nucleus data?

Data: discovery paper doi:10.1038/s41588-026-02758-w; donor-level usage matrices, PAS definitions and donor metadata at https://cboix.github.io/snAPA/ (ROSMAP-type aged cohort); summary statistics https://personal.broadinstitute.org/cboix/snAPA_data/apaQTL_sumstats/Exc.3aQTL.sumstats.txt.gz and Oli.3aQTL.sumstats.txt.gz; code https://github.com/xiongxslab/NanJ_Carles_et_al_3aQTL_project.

First determine feasibility: are donor-level usage, donor age (often top-coded at 90+), and genotypes (or a genotype proxy) publicly available? Report exactly which inputs are public vs controlled. If feasible, for 3'aQTLs tested in both cell types, fit a donor-level model usage ~ genotype × cell type × age (with donor random effects, covariates such as sex, PMI, pathology, and cell-count weights), and test the genotype×cell×age interaction both per locus (FDR) and aggregated across loci. Deliver code, data manifest, power curve, results table and a short manuscript draft.`;
const Q_SHORT = "Does HC3 restore coverage?";
const Q_MID = "Does the heteroskedasticity-consistent HC3 estimator restore nominal 95% coverage of the ordinary least squares slope interval when errors grow with the regressor, across sample sizes from twenty to two thousand?";
const camp = (id, q) => ({ id, research_question: q, status: "completed", tokens_used: 1, token_budget_max: 10, gpu_seconds_used: 0, gpu_seconds_max: 1, created_at: t, updated_at: t, program_domain: "genomics", config: {} });
const C = { [LONG]: camp(LONG, Q_LONG), [SHORT]: camp(SHORT, Q_SHORT), [MID]: camp(MID, Q_MID) };
const api = p => {
  if (p === "me") return { account: { id: "a", name: "Test", email: "t@example.com", preferences: { theme: THEME, home: "campaigns" } }, models: {}, key: {}, allowance: {} };
  if (p === "health") return { model: "m" };
  if (p === "campaigns") return { campaigns: Object.values(C) };
  if (p === "projects") return { projects: [] };
  const m = p.match(/^campaigns\/([0-9a-f-]{36})(?:\/(\w+))?$/); if (!m || !C[m[1]]) return null;
  return { undefined: { campaign: C[m[1]], node_counts: [], guard_events: [] }, graph: { nodes: [], edges: [] }, files: { files: [] }, usage: { points: [] } }[m[2]] || null;
};
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2" };
const srv = http.createServer((q, r) => { const u = decodeURIComponent(q.url.split("?")[0]);
  if (u.startsWith("/api/")) { const b = api(u.slice(5)); r.writeHead(b ? 200 : 404, { "content-type": "application/json" }); return r.end(JSON.stringify(b || { error: "nf" })); }
  let f = path.join(ROOT, u === "/" ? "index.html" : u); if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(ROOT, "index.html");
  r.writeHead(200, { "content-type": types[path.extname(f)] || "application/octet-stream" }); fs.createReadStream(f).pipe(r); }).listen(8798);
const fail = m => { throw new Error(m); };
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: THEME, deviceScaleFactor: +(process.env.SCALE || 1) });
  const pg = await ctx.newPage(); const errs = []; pg.on("console", m => m.type() === "error" && errs.push(m.text())); pg.on("pageerror", e => errs.push(String(e)));
  const state = () => pg.evaluate(() => { const h = document.querySelector("#pane h1.cq"), btn = document.querySelector("#cqBtn"), cs = getComputedStyle(h);
    return { size: cs.fontSize, lh: cs.lineHeight, h: Math.round(h.getBoundingClientRect().height), btn: btn && !btn.hidden && btn.getClientRects().length > 0, exp: btn?.getAttribute("aria-expanded"), label: btn?.textContent.trim(),
      text: h.textContent.length, over: document.documentElement.scrollWidth > innerWidth }; });
  const open = async id => { await pg.goto(`http://127.0.0.1:8798/#/c/${id}/overview`); await pg.waitForSelector("#pane h1.cq"); await pg.waitForTimeout(500); };
  // 1. long title: 13px, two lines, button shown collapsed
  await open(LONG); let s = await state(); console.log("long collapsed", s);
  if (s.size !== "13px" || s.lh !== "20px") fail("title should be 13px/20px");
  if (s.h !== 40 || !s.btn || s.exp !== "false" || s.label !== "Show more") fail("long title should clamp to 2 lines with Show more");
  if (s.text !== Q_LONG.length) fail("full question must stay in the h1 for screen readers");
  await pg.screenshot({ path: `${OUT}/title-long-collapsed-${THEME}.png`, clip: { x: 230, y: 40, width: 1000, height: 260 } });
  // 2. keyboard: focus the button, Enter expands, Space collapses
  await pg.focus("#cqBtn"); await pg.keyboard.press("Enter"); await pg.waitForTimeout(200); s = await state(); console.log("long expanded", s);
  if (s.h <= 120 || s.exp !== "true" || s.label !== "Show less" || !s.btn) fail("Enter should expand");
  const paras = await pg.$eval("#cq", h => getComputedStyle(h).whiteSpace); if (paras !== "pre-line") fail("expanded title should keep paragraphs");
  await pg.screenshot({ path: `${OUT}/title-long-expanded-${THEME}.png`, clip: { x: 230, y: 40, width: 1000, height: 420 } });
  // 3. state survives a re-render (another tab and back) and focus stays usable
  await pg.click('[data-tab="graph"], a[href$="/graph"]').catch(() => pg.goto(`http://127.0.0.1:8798/#/c/${LONG}/graph`)); await pg.waitForTimeout(300);
  await open(LONG); s = await state(); console.log("after re-render", s); if (s.exp !== "true" || s.h <= 120) fail("expanded state lost on re-render");
  await pg.focus("#cqBtn"); await pg.keyboard.press("Space"); await pg.waitForTimeout(200); s = await state(); if (s.h !== 40 || s.exp !== "false") fail("Space should collapse");
  // 4. short title: one line, no button
  await open(SHORT); s = await state(); console.log("short", s); if (s.h !== 20 || s.btn) fail("short title must show no button");
  // 5. mid title: fits in 2 lines on desktop, clamps on a phone; button follows the width
  await open(MID); s = await state(); console.log("mid desktop", s); if (s.btn) fail("mid title fits on desktop: no button");
  await pg.setViewportSize({ width: 390, height: 844 }); await pg.waitForTimeout(400); s = await state(); console.log("mid phone", s);
  if (!s.btn || s.h !== 40) fail("mid title should clamp with a button on a phone");
  await open(LONG); s = await state(); console.log("long phone", s); if (s.over) fail("page scrolls sideways on a phone (long URLs must wrap)");
  await pg.screenshot({ path: `${OUT}/title-long-phone-collapsed-${THEME}.png` });
  await pg.click("#cqBtn"); await pg.waitForTimeout(200); s = await state(); console.log("long phone expanded", s); if (s.over || s.exp !== "true") fail("phone expand failed or overflows");
  await pg.screenshot({ path: `${OUT}/title-long-phone-expanded-${THEME}.png` });
  if (errs.length) fail("console errors: " + errs.join(" | "));
  console.log("PASS", THEME); await b.close(); srv.close();
})().catch(e => { console.error("FAIL", e.message); process.exit(1); });
