// Browser check of the Publish tab, Connected services, Files and the new-thread library
// picker. Needs the same setup as e2e/integrations.test.mjs (wrangler dev with the Composio
// stub, the Python service, PLATO_DATABASE_URL for the seed script).
// Run: node e2e/publish-ui.test.cjs <screenshot dir>   Fails on any console or page error.
const { chromium } = require("playwright");
const { execFileSync } = require("node:child_process");
const path = require("node:path");
const BASE = process.env.PLATO_E2E_BASE || "http://127.0.0.1:8787";
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE)) throw new Error("PLATO_E2E_BASE must be a local wrangler dev URL");
const OUT = process.argv[2] || ".";
const PY = process.env.PLATO_E2E_PYTHON || "python3";
const errors = [];
const step = (m) => console.log("·", m);
const fail = (m) => { throw new Error(m); };

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark", acceptDownloads: true });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text() + " @ " + (m.location()?.url || "")); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  const shot = (n) => page.screenshot({ path: `${OUT}/pub-${n}.png` });
  // Requests from the page itself, so the session cookie rides along exactly as in the app.
  const api = async (method, p, data) => {
    const r = await page.evaluate(async ([m, u, d]) => {
      const res = await fetch("/api/" + u, { method: m, headers: d === undefined ? {} : { "content-type": "application/json" }, body: d === undefined ? undefined : JSON.stringify(d) });
      return { status: res.status, text: await res.text() };
    }, [method, p, data]);
    if (r.status >= 400) fail(`${method} ${p}: ${r.status} ${r.text}`);
    return JSON.parse(r.text);
  };
  const head = (u) => page.evaluate(async (u) => { const r = await fetch(u); const b = new Uint8Array(await r.arrayBuffer());
    return { status: r.status, type: r.headers.get("content-type"), magic: String.fromCharCode(...b.slice(0, 5)) }; }, u);

  await page.goto(BASE + "/#/signup");
  await page.fill('input[name="name"]', "Rosalind Franklin");
  await page.fill('input[name="email"]', `pub${Date.now()}@example.com`);
  await page.fill('input[name="password"]', "correct horse battery");
  await page.click("#authBtn");
  await page.waitForFunction(() => !document.body.classList.contains("signed-out"));
  const acct = (await api("GET", "me")).account.id;

  // 1. Connected services: nothing connected yet, then Drive and Gmail (sign-in is simulated by the stub)
  await page.goto(BASE + "/#/settings/integrations");
  await page.waitForSelector('[data-iact="connect"][data-svc="googledrive"]');
  const navItems = await page.$$eval("#nav .item", (els) => els.map((e) => e.textContent.trim()));
  if (!navItems.includes("Connected services") || !navItems.includes("Files")) fail("settings nav " + JSON.stringify(navItems));
  await shot("services-empty-dark");
  await api("POST", "integrations/connect", { service: "googledrive" });
  await api("POST", "integrations/connect", { service: "gmail" });
  await page.reload();
  await page.waitForSelector('[data-iact="disconnect"][data-svc="googledrive"]');
  if ((await page.$$('[data-iact="trigger"]')).length !== 2) fail("automatic import rows for Drive and Gmail");
  // Watch a Drive folder through the folder browser
  await page.click('[data-iact="trigger"][data-svc="googledrive"]');
  await page.waitForSelector("#brBody .br-row.nav");
  if (!(await page.isDisabled("#brGo"))) fail("watch enabled at the root");
  await page.click("#brBody .br-row.nav");
  await page.waitForFunction(() => document.querySelector("#brCrumb").textContent.includes("Lab"));
  await page.click("#brGo");
  await page.waitForSelector('[data-iact="untrigger"]');
  await shot("services-dark");
  step("connected services: connect state, folder browser, automatic import added");

  // 2. Files: upload, import from Drive
  await page.goto(BASE + "/#/settings/files");
  await page.waitForSelector("#libUp", { state: "attached" });
  await page.setInputFiles("#libUp", [
    { name: "calls.vcf", mimeType: "text/x-vcf", buffer: Buffer.from("##fileformat=VCFv4.2\n#CHROM\tPOS\n1\t5\n") },
    { name: "refs.bib", mimeType: "application/x-bibtex", buffer: Buffer.from("@article{k,title={A study},year={2021}}\n") },
  ]);
  await page.waitForFunction(() => document.querySelectorAll("#pane table.members tbody tr").length === 2);
  await page.click('[data-iact="browse"][data-svc="googledrive"]');
  await page.waitForSelector("#brBody .br-row.nav");
  await page.click("#brBody .br-row.nav");
  await page.waitForSelector('#brBody input[type="checkbox"]');
  await page.check('#brBody input[type="checkbox"]');
  if ((await page.textContent("#brMsg")) !== "1 selected") fail("selection count");
  await page.click("#brGo");
  await page.waitForFunction(() => [...document.querySelectorAll("#pane table.members td")].some((td) => td.textContent === "expression.csv"));
  const rows = await page.$$eval("#pane table.members tbody tr", (trs) => trs.map((tr) => [...tr.children].slice(0, 4).map((td) => td.textContent.trim())));
  const kinds = Object.fromEntries(rows.map((r) => [r[0], [r[1], r[3]]]));
  if (JSON.stringify(kinds["calls.vcf"]) !== '["Data","Uploaded"]' || JSON.stringify(kinds["refs.bib"]) !== '["References","Uploaded"]' || JSON.stringify(kinds["expression.csv"]) !== '["Data","Google Drive"]')
    fail("files table " + JSON.stringify(rows));
  await shot("files-dark");
  step("files: upload a VCF and a .bib, import a CSV from Drive");

  // 3. Publish: an unfinished campaign says so; a finished one builds a Nature package
  const cid = execFileSync(PY, [path.join(__dirname, "seed_campaign.py"), acct], { encoding: "utf8", env: process.env }).trim().split("\n").pop();
  await page.goto(BASE + `/#/c/${cid}/publish`);
  await page.waitForSelector("#pubJournal");
  const tabs = await page.$$eval("#tabs .tab", (t) => t.map((x) => x.textContent.trim()));
  if (tabs.at(-1) !== "Publish") fail("tabs " + JSON.stringify(tabs));
  const opts = await page.$$eval("#pubJournal option", (o) => o.map((x) => x.textContent));
  for (const j of ["Nature", "Nature Communications", "Science", "Cell", "New England Journal of Medicine", "The Lancet", "JAMA", "Genes", "arXiv"]) if (!opts.some((o) => o.includes(j))) fail(`journal ${j} missing: ${opts}`);
  await page.selectOption("#pubJournal", "nature");
  await page.waitForFunction(() => document.querySelector(".pub-build").textContent.includes("Title ≤ 75 characters"));
  // Citation style picker: the journal's own style first, then the general styles.
  const styles = await page.$$eval("#pubStyle option", (o) => o.map((x) => [x.value, x.textContent]));
  if (styles[0][0] !== "journal" || !styles[0][1].includes("Nature's own: Nature")) fail("style default " + JSON.stringify(styles[0]));
  for (const s of ["APA 7th edition", "Vancouver / NLM (Citing Medicine)", "Harvard (Cite Them Right 12th edition)", "Chicago 18th edition (author-date)"])
    if (!styles.some((x) => x[1] === s)) fail(`style ${s} missing`);
  await page.selectOption("#pubStyle", "apa");
  await page.waitForFunction(() => document.querySelector(".pub-build").textContent.includes("asks for its own reference style"));
  await page.selectOption("#pubStyle", "journal");
  await page.waitForFunction(() => !document.querySelector(".pub-build").textContent.includes("asks for its own reference style"));
  await shot("publish-empty-dark");
  await page.click("#pubBuild");
  await page.waitForSelector(".pub-card [data-pact=send]", { timeout: 180000 });
  const card = await page.$eval(".pub-card", (c) => c.textContent);
  if (!/Nature/.test(card) || !/passed/.test(card)) fail("package card " + card);
  if ((await page.$$(".pub-list li")).length < 10) fail("checks list not shown after a build");
  const dl = await page.$eval('.pub-card a[download]', (a) => a.getAttribute("href"));
  const zr = await head(dl);
  if (zr.status !== 200 || !zr.magic.startsWith("PK")) fail("download " + JSON.stringify(zr));
  const pv = await page.$eval('.pub-card a[target=_blank]', (a) => a.getAttribute("href"));
  const pr = await head(pv);
  if (pr.type !== "application/pdf" || pr.magic !== "%PDF-") fail("preview " + JSON.stringify(pr));
  await shot("publish-dark");
  // Send to Drive and email through Gmail from the dialogs
  await page.click(".pub-card [data-pact=send]");
  await page.waitForSelector('#sendForm select[name="service"]');
  if (!(await page.isHidden("#pathRow"))) fail("folder path shown for Drive");
  await page.click("#sendBtn");
  await page.waitForSelector(".toast:has-text('to Google Drive')", { timeout: 60000 });
  await page.click(".pub-card [data-pact=email]");
  await page.waitForSelector('#mailForm input[name="to"]');
  await page.fill('#mailForm input[name="to"]', "not an email");
  await page.click("#mailBtn");
  await page.waitForSelector("#mailErr:not([hidden])");
  await page.fill('#mailForm input[name="to"]', "reviewer@example.org");
  await page.fill('#mailForm textarea[name="message"]', "Draft attached.");
  await shot("email-dark");
  await page.click("#mailBtn");
  await page.waitForSelector(".toast:has-text('Emailed to reviewer@example.org')", { timeout: 60000 });
  await page.click(".pub-card [data-pact=library]");
  await page.waitForSelector(".toast:has-text('Saved')");
  step("publish: journal picker with limits, build, checks, download, PDF preview, send, email, save");

  // 4. New research thread with files from the library
  await page.goto(BASE + "/#/campaigns");
  await page.waitForSelector("#newBtn");
  await page.click("#newBtn");
  await page.waitForSelector("#libBtn");
  await page.click("#libBtn");
  await page.waitForSelector("#libPick input[type=checkbox]");
  const offered = await page.$$eval("#libPick .br-row .trunc", (e) => e.map((x) => x.textContent));
  if (offered.some((n) => n.endsWith(".zip"))) fail("archives offered: " + offered);
  for (const name of ["calls.vcf", "refs.bib"]) await page.check(`#libPick label:has-text("${name}") input`);
  if ((await page.textContent("#libLbl")) !== "2 files from Files") fail("picker label");
  await page.fill('#newForm textarea[name="question"]', "Which variants change expression?");
  await page.selectOption('#newForm select[name="token_budget"]', "500000");   // within the test allowance
  await shot("new-thread-dark");
  await page.click("#createBtn");
  await page.waitForFunction(() => /^#\/c\/[0-9a-f-]{36}/.test(location.hash), null, { timeout: 30000 });
  step("new thread from Files");

  // 5. Phone width, light theme
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: "light" });
  await api("PATCH", "me", { preferences: { theme: "light" } });
  await page.goto(BASE + `/#/c/${cid}/publish`);
  await page.waitForSelector(".pub-card");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth || [...document.querySelectorAll(".pub-card,.pub-build")].some((e) => e.getBoundingClientRect().right > innerWidth + 1));
  if (overflow) fail("horizontal overflow at 390px");
  await shot("publish-light-390");
  await page.goto(BASE + "/#/settings/files");
  await page.waitForSelector("#pane table.members");
  await shot("files-light-390");
  step("390px light layouts without horizontal overflow");

  await browser.close();
  if (errors.length) { console.log("CONSOLE ERRORS:\n" + errors.join("\n")); process.exit(1); }
  console.log("PASS, no console errors");
})().catch((e) => { console.error(e); if (errors.length) console.log("CONSOLE ERRORS:\n" + errors.join("\n")); process.exit(1); });
