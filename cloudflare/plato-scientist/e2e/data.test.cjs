// End-to-end check of the experiment data views (Data tab, experiment pages) with the real
// plato-lab outputs in e2e/fixtures/viz, seeded through the scientist's store by seed_viz.py.
// Run against wrangler dev on a local database:
//   PLATO_E2E_PYTHON=/path/to/venv/python PLATO_E2E_DSN=postgresql://postgres:postgres@127.0.0.1:5432/plato_viz \
//     node e2e/data.test.cjs <screenshot dir>
// Fails on any console error, page error or failed API call.
const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const path = require("path");
const BASE = process.env.PLATO_E2E_BASE || "http://127.0.0.1:8787";
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE)) throw new Error("PLATO_E2E_BASE must be a local wrangler dev URL");
const DSN = process.env.PLATO_E2E_DSN;
if (!DSN || !/@(127\.0\.0\.1|localhost)[:/]/.test(DSN)) throw new Error("PLATO_E2E_DSN must point at a local database");
const PY = process.env.PLATO_E2E_PYTHON || "python3";
const OUT = process.argv[2] || ".";
const SCALE = +(process.env.PLATO_E2E_SCALE || 1);

const errors = [];
const step = (m) => console.log("·", m);
const fail = (m) => { throw new Error(m); };
const eq = (a, b, m) => { if (a !== b) fail(`${m}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`); };
const ok = (v, m) => { if (!v) fail(m); };

(async () => {
  // 1. an account, then a campaign seeded with the real outputs
  const email = `viz${Date.now()}@example.com`;
  const r = await fetch(BASE + "/api/auth/signup", { method: "POST", headers: { "content-type": "application/json", origin: BASE, "cf-connecting-ip": "10.9." + (Date.now() % 250) + ".7" },
    body: JSON.stringify({ name: "Data Viewer", email, password: "correct horse battery" }) });
  if (r.status !== 200 && r.status !== 201) fail("signup failed: " + r.status + " " + await r.text());
  const cookie = (r.headers.getSetCookie?.() || []).map(c => c.split(";")[0]).find(c => c.includes("="));
  ok(cookie, "no session cookie");
  const seed = JSON.parse(execFileSync(PY, [path.join(__dirname, "seed_viz.py"), "--dsn", DSN, "--email", email], { encoding: "utf8" }));
  const C = seed.campaign, X = seed.experiments, FILES = seed.files;
  step(`seeded campaign ${C} with ${Object.keys(FILES).length} files: ${Object.keys(FILES).join(", ")}`);
  eq(Object.keys(FILES).length, 11, "files recorded by store_outputs");

  const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark", deviceScaleFactor: SCALE });
  const [name, value] = cookie.split("=");
  // the session is a __Host- cookie (Secure, Path=/): Chromium accepts Secure cookies on loopback http
  await ctx.addCookies([{ name, value: cookie.slice(name.length + 1), domain: new URL(BASE).hostname, path: "/", secure: true, httpOnly: true, sameSite: "Lax" }]);
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text() + " @ " + (m.location()?.url || "")); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("response", (res) => { if (res.status() >= 400 && res.url().includes("/api/")) errors.push(`http ${res.status()} ${res.url().replace(BASE, "")}`); });
  const shot = (n) => page.screenshot({ path: `${OUT}/data-${n}.png` });
  const open = async (file) => { await page.goto(`${BASE}/#/c/${C}/data/${FILES[file]}`); await page.waitForSelector(`.dv[data-file="${FILES[file]}"] .dv-body > :not(.dv-skel)`, { timeout: 20000 }); };
  const viewer = (file) => `.dv[data-file="${FILES[file]}"]`;

  // 2. Data tab: list, filters, counts
  await page.goto(`${BASE}/#/c/${C}/data`);
  await page.waitForSelector(".dl-list .dv-row");
  await page.waitForSelector('.tab[href$="/data"] .c');
  const tab = await page.textContent('.tab[href$="/data"]');
  eq(tab.replace(/\s+/g, ""), "Data11", "Data tab label and count");
  eq(await page.locator(".dl-list .dv-row").count(), 11, "file rows");
  const filters = await page.$$eval(".dl-fs button", bs => bs.map(b => b.textContent.replace(/\s+/g, "")));
  step("filters " + filters.join(" "));
  eq(filters.join(","), "All11,Figures1,Tables5,Structures4,Networks1", "filter counts (the JSON network is re-sorted once opened)");
  step("Data tab lists 11 files in 4 experiments");

  // 3. proteomics table: volcano, tooltip, table sorting and filtering
  await open("ubi4_vs_ctrl_differential.csv");
  const v = viewer("ubi4_vs_ctrl_differential.csv");
  eq(await page.$eval(`${v} [data-dtype]`, s => s.value), "volcano", "default chart for a differential table");
  const dots = await page.locator(`${v} svg.dv-svg circle`).count();
  ok(dots >= 1300, `volcano points: ${dots}`);
  const legend = await page.textContent(`${v} .dv-legend`);
  const up = +legend.match(/Up (\d+)/)[1], down = +legend.match(/Down (\d+)/)[1];
  eq(up + down, 4, "significant proteins (manifest: 4 at 5% FDR, |log2FC| > 1)");
  ok((await page.textContent(`${v} svg.dv-svg`)).includes("SQSTM1"), "top hit labelled");
  const box = await page.locator(`${v} svg.dv-svg`).boundingBox();
  // hover the SQSTM1 point: find its label and move just left-below it
  const lab = await page.locator(`${v} svg text.dv-lab`, { hasText: "SQSTM1" }).boundingBox();
  await page.mouse.move(lab.x - 4, lab.y + lab.height + 3);
  await page.waitForSelector(`${v} .dv-tip:not([hidden])`);
  ok((await page.textContent(`${v} .dv-tip`)).includes("SQSTM1"), "tooltip names the protein");
  await shot("volcano-dark");
  step(`volcano: ${dots} proteins, ${up} up / ${down} down, tooltip works`);
  await page.click(`${v} [data-dview="table"]`);
  await page.waitForSelector(`${v} table.dg`);
  ok((await page.textContent(`${v} .gfoot`)).includes("1–50 of 1356"), "table paging");
  await page.click(`${v} th:nth-child(3) button`); await page.click(`${v} th:nth-child(3) button`);   // log2FC descending
  eq(await page.textContent(`${v} tbody tr:first-child td:nth-child(2)`), "RPS27A", "largest log2FC first");
  await page.fill(`${v} [data-dq]`, "NUP155"); await page.waitForTimeout(250);
  ok((await page.textContent(`${v} .gfoot`)).includes("1–1 of 1"), "filter rows");
  step("table: sort and filter");

  // 4. enrichment: bars, then the term-gene network in 2D and 3D
  await open("go_enrichment.csv");
  const g = viewer("go_enrichment.csv");
  eq(await page.$eval(`${g} [data-dtype]`, s => s.value), "enrichment", "default chart for an enrichment table");
  eq(await page.locator(`${g} svg.dv-svg rect`).count(), 20, "top 20 terms");
  ok((await page.textContent(`${g} svg.dv-svg`)).includes("nuclear chromosome segregation"), "top term");
  await shot("enrichment-dark");
  await page.click(`${g} [data-dview="network"]`);
  await page.waitForSelector(`${g} .dv-nodes g`);
  const tg = await page.locator(`${g} .dv-nodes g`).count();
  ok(tg > 30, "term-gene network nodes: " + tg);
  await page.click(`${g} [data-ddim="3d"]`);
  await page.waitForSelector(`${g} canvas`);
  step(`enrichment: 20 terms; term-gene network with ${tg} nodes in 2D and 3D`);

  // 5. KEGG pathway JSON: 2D with fold-change colours, 3D orbit
  await open("kegg_cell_cycle.json");
  const k = viewer("kegg_cell_cycle.json");
  await page.waitForSelector(`${k} .dv-nodes g`);
  eq(await page.locator(`${k} .dv-nodes g`).count(), 39, "KEGG hsa04110 nodes");
  eq(await page.locator(`${k} .dv-edges line`).count(), 37, "KEGG hsa04110 edges");
  ok((await page.textContent(`${k} .dv-legend`)).includes("log2FC"), "fold-change colour key");
  await page.hover(`${k} .dv-nodes g:has(text:text-is("CDK1")) circle:not(.hit)`);
  await page.waitForSelector(`${k} .dv-tip:not([hidden])`);
  ok((await page.textContent(`${k} .dv-tip`)).includes("log2FC 2.422"), "node tooltip shows fold change");
  await shot("pathway-2d-dark");
  await page.click(`${k} [data-ddim="3d"]`);
  const cv = await page.waitForSelector(`${k} canvas`);
  const cb = await cv.boundingBox();
  await page.mouse.move(cb.x + cb.width / 2, cb.y + cb.height / 2); await page.mouse.down(); await page.mouse.move(cb.x + cb.width / 2 + 120, cb.y + cb.height / 2 + 40, { steps: 6 }); await page.mouse.up();
  await shot("pathway-3d-dark");
  // the filter list now files the JSON under Networks
  const nets = await page.textContent('.dl-fs [data-dfilter="network"]');
  eq(nets.replace(/\s+/g, ""), "Networks2", "JSON network re-filed after parsing");
  step("KEGG cell cycle: 39 nodes, 37 edges, 2D and 3D");

  // 6. protein structures: 3D (3Dmol.js) and 2D (secondary structure + contact map)
  await open("ubiquitin_1ubq.pdb");
  const u = viewer("ubiquitin_1ubq.pdb");
  await page.waitForSelector(`${u} .dv-3d canvas`, { timeout: 20000 });
  const facts = await page.textContent(`${u} .dv-facts`);
  ok(/1 chain/.test(facts) && /76 residues/.test(facts), "ubiquitin summary: " + facts);
  await page.waitForTimeout(600);
  await shot("protein-3d-dark");
  await page.selectOption(`${u} [data-dcolor]`, "rainbow");
  await page.click(`${u} [data-ddim="2d"]`);
  await page.waitForSelector(`${u} .dv-cmap canvas`);
  const helix = await page.locator(`${u} .dv-ss .ss-h`).count(), strand = await page.locator(`${u} .dv-ss .ss-s`).count();
  ok(helix > 5 && strand > 5, `ubiquitin has helix (${helix}) and strand (${strand}) residues`);
  eq((await page.textContent(`${u} .dv-seq`)).replace(/\s/g, "").slice(0, 10), "MQIFVKTLTG", "ubiquitin sequence");
  await shot("protein-2d-dark");
  step(`ubiquitin: 3D cartoon, 2D track (${helix} helix, ${strand} strand residues) and contact map`);
  await open("hemoglobin_4hhb.cif");
  const h = viewer("hemoglobin_4hhb.cif");
  await page.waitForSelector(`${h} .dv-3d canvas`, { timeout: 20000 });
  ok(/4 chains/.test(await page.textContent(`${h} .dv-facts`)), "haemoglobin has 4 chains");
  ok((await page.textContent(`${h} .dv-facts`)).includes("HEM"), "haem ligand listed");
  await page.click(`${h} [data-dsurf]`); await page.waitForTimeout(800);
  await shot("hemoglobin-3d-dark");
  step("haemoglobin: 4 chains with haem, surface on");

  // 7. small molecules: 2D drawings (OpenChemLib) and 3D (3Dmol.js)
  await open("ligands.sdf");
  const l = viewer("ligands.sdf");
  await page.click(`${l} [data-ddim="2d"]`);
  await page.waitForSelector(`${l} .dv-mol img`);
  eq(await page.locator(`${l} .dv-mol img`).count(), 3, "three ligands drawn");
  const caps = await page.$$eval(`${l} .dv-mol figcaption`, fs => fs.map(f => f.innerText.replace(/\s+/g, " ").trim()));
  ok(caps[0].startsWith("aspirin C9H8O4") && caps[2].startsWith("caffeine C8H10N4O2"), "names and formulas: " + caps.join(" | "));
  await page.waitForFunction(sel => [...document.querySelectorAll(sel)].every(i => i.complete && i.naturalWidth > 0), `${l} .dv-mol img`);
  await shot("ligands-2d-dark");
  await page.click(`${l} [data-ddim="3d"]`);
  await page.waitForSelector(`${l} .dv-3d canvas`);
  eq(await page.locator(`${l} [data-dmol] option`).count(), 3, "molecule picker");
  await page.selectOption(`${l} [data-dmol]`, "2");
  step("ligands: 3 drawn in 2D with formulas; 3D with a picker");
  await open("ligand_descriptors.csv");
  const d = viewer("ligand_descriptors.csv");
  await page.click(`${d} [data-dview="mols"]`);
  await page.waitForSelector(`${d} .dv-mol img`);
  eq(await page.locator(`${d} .dv-mol img`).count(), 3, "SMILES column drawn");
  step("descriptor table: SMILES drawn as molecules");

  // 8. figure
  await open("volcano.png");
  await page.waitForFunction(sel => { const i = document.querySelector(sel); return i && i.complete && i.naturalWidth > 0; }, `${viewer("volcano.png")} img.dv-img`);
  step("figure renders");

  // 9. experiment pages: workflow states
  const wf = async (key) => { await page.goto(`${BASE}/#/c/${C}/experiments/${key}`); await page.waitForSelector(".wf .wf-s");
    await page.waitForFunction(() => ![...document.querySelectorAll(".wf-l")].some(e => e.textContent.includes("Reading the recipe")));
    return page.$$eval(".wf-s", ss => ss.map(s => [s.querySelector("b").textContent, s.className.match(/wf-(done|fail|run|todo|skip)/)[1], s.textContent])); };
  let steps = await wf(X.proteomics);
  eq(steps.map(s => s[0]).join(","), "Designed,Environment,Run,Outputs,Measured,Replicated,Checked,Outcome", "workflow steps");
  eq(steps.map(s => s[1]).join(","), "done,done,done,done,done,done,done,done", "proteomics workflow all done");
  ok(steps[1][2].includes("2 setup commands") && steps[1][2].includes("experiment.py"), "environment read from the recipe: " + steps[1][2]);
  ok(steps[3][2].includes("1 table") && steps[3][2].includes("1 figure"), "outputs counted: " + steps[3][2]);
  ok(steps[7][2].includes("Verified finding"), "outcome");
  await page.waitForSelector(".xp .dv .dv-body > :not(.dv-skel)");
  await shot("experiment-dark");
  steps = await wf(X.structures);
  eq(steps[6][1], "fail", "structures: statistics check failed"); ok(steps[7][2].includes("Claim refuted"), "structures refuted");
  await page.goto(`${BASE}/#/c/${C}/experiments`); await page.waitForSelector("a.row.xrow");
  eq(await page.locator("a.row.xrow").count(), 7, "experiments listed");
  const running = await page.getAttribute('a.row.xrow:has-text("chain length")', "href");
  steps = await wf(running.split("/").pop());
  eq(steps[2][1], "run", "running experiment shows the run in progress");
  const dead = await page.getAttribute('a.row.xrow:has-text("adenosine")', "href").catch(() => null);
  await page.goto(`${BASE}/#/c/${C}/experiments`); await page.waitForSelector("a.row.xrow");
  steps = await wf((await page.getAttribute('a.row.xrow:has-text("adenosine")', "href")).split("/").pop());
  eq(steps[2][1], "fail", "exhausted experiment"); ok(steps[2][2].includes("after 3 attempts"), "attempts shown");
  step("experiment pages: done, refuted, running and exhausted workflows");

  // 9b. a design is shown as labelled fields, never as its stored JSON, on the experiment page
  // and in the node panel
  const design = JSON.parse(require("fs").readFileSync(path.join(__dirname, "../../../tests/scientist/fixtures/intent_design.json"), "utf8"));
  const want = [["Hypothesis", design.hypothesis], ["Protocol", design.protocol], ["Success criterion", design.success_criterion],
    ["Primary metric", design.primary_metric], ["Test", design.test_kind]];
  const specOn = (sel) => page.$$eval(`${sel} .xp-spec dt`, dts => dts.map(dt => [dt.textContent, dt.nextElementSibling.textContent]));
  const noJson = async (sel) => { const t = await page.textContent(sel); ok(!t.includes('"hypothesis"') && !t.includes('{"'), `raw JSON shown in ${sel}`); };
  await page.goto(`${BASE}/#/c/${C}/experiments/${X.design}`); await page.waitForSelector(".xp .xp-spec");
  eq(JSON.stringify(await specOn(".xp")), JSON.stringify(want), "experiment page design fields");
  await noJson(".xp");
  await page.goto(`${BASE}/#/c/${C}/graph`); await page.click(`.gn[data-node="${X.design}"]`);
  await page.waitForSelector("#props .pp .xp-spec");
  eq(JSON.stringify(await specOn("#props .pp")), JSON.stringify(want), "node panel design fields");
  await noJson("#props .pp");
  await shot("design-panel-dark");
  step("a stored design renders as labelled fields on the experiment page and in the node panel");

  // 10. light theme and a narrow window
  await page.emulateMedia({ colorScheme: "light" });
  await page.evaluate(() => { document.documentElement.dataset.theme = "light"; });
  await open("kegg_cell_cycle.json"); await page.waitForSelector(`${k} .dv-nodes g`);
  await shot("pathway-2d-light");
  await open("ubiquitin_1ubq.pdb"); await page.waitForSelector(`${u} .dv-3d canvas`); await page.waitForTimeout(500);
  await shot("protein-3d-light");
  await page.setViewportSize({ width: 390, height: 844 });
  await open("ubi4_vs_ctrl_differential.csv"); await page.waitForTimeout(300);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok(overflow <= 0, "no horizontal page scroll at phone width: " + overflow);
  await shot("volcano-phone-light");
  step("light theme and phone width");

  await browser.close();
  if (errors.length) fail("console/page errors:\n" + errors.join("\n"));
  console.log("PASS data viewer e2e");
})().catch((e) => { console.error("FAIL", e.message); if (errors.length) console.error(errors.join("\n")); process.exit(1); });
