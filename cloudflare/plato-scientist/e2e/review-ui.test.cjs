// Browser check of the Manuscript tab: the peer review side panel (open, close, resize,
// keyboard, persistence), claims marked in the paper and linked both ways, the PDF view and
// LaTeX beside it, the review line on the live paper card, a legacy review, small screens.
// Needs wrangler dev on :8787 (with PLATO_DEV_SERVICE_URL) and the Python service with
// pdflatex, plus PLATO_DATABASE_URL for the seed script (same database).
// Run: node e2e/review-ui.test.cjs <screenshot dir>   Fails on any console or page error.
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
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text() + " @ " + (m.location()?.url || "")); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  const shot = (n, opts = {}) => page.screenshot({ path: `${OUT}/rv-${n}.png`, ...opts });
  const api = async (p) => page.evaluate(async (u) => { const r = await fetch("/api/" + u); return { status: r.status, type: r.headers.get("content-type"), text: r.headers.get("content-type")?.includes("json") ? await r.text() : "" }; }, p);

  await page.goto(BASE + "/#/signup");
  await page.fill('input[name="name"]', "Rosalind Franklin");
  await page.fill('input[name="email"]', `rv${Date.now()}@example.com`);
  await page.fill('input[name="password"]', "correct horse battery");
  await page.click("#authBtn");
  await page.waitForFunction(() => !document.body.classList.contains("signed-out"));
  const acct = JSON.parse((await api("me")).text).account.id;
  const cid = execFileSync(PY, [path.join(__dirname, "seed_reviewed_paper.py"), acct], { encoding: "utf8", env: process.env }).trim().split("\n").pop();
  step(`seeded ${cid}`);

  // 1. The panel opens beside the paper with the decision on the revised paper and every claim
  await page.evaluate(() => { localStorage.removeItem("plato_review_open"); localStorage.removeItem("plato_review_w"); });
  await page.goto(`${BASE}/#/c/${cid}/manuscript`);
  await page.reload();
  await page.waitForSelector("#review:not([hidden]) .rv-claim");
  await page.waitForFunction(() => window.katex && document.querySelector("#pane .ms-paper .katex"));
  const head = await page.textContent("#review .rv-dec");
  if (!head.includes("Minor revision")) fail("decision on the revised paper: " + head);
  const verdict = await page.textContent(".rv-verdict");
  if (!verdict.includes("First review: Major revision") || !verdict.includes("On the revised paper")) fail("first-round decision: " + verdict);
  if ((await page.$$(".rv-claim")).length !== 7) fail("seven claims");
  const removed = await page.$$eval(".rv-quote.gone", (els) => els.length);
  if (removed !== 1) fail("the removed claim is struck through");
  const cols = await page.$eval("#body", (b) => getComputedStyle(b).gridTemplateColumns.split(" ").map(parseFloat));
  if (cols.length !== 2 || Math.abs(cols[1] - 420) > 1) fail("panel track 420px: " + cols);
  await shot("panel-dark");
  step("panel open with decision, scores and seven claims");

  // 2. Claims are marked in the paper by verdict (Highlight API), from the final quotes
  const marks = await page.evaluate(() => Object.fromEntries(["approved", "needs_revision", "rejected"].map((k) => [k, CSS.highlights.get("rv-" + k)?.size || 0])));
  if (marks.approved !== 5 || marks.needs_revision !== 1 || marks.rejected !== 0) fail("marks " + JSON.stringify(marks));
  // The rejected "proves ... never safe" claim was revised: its card points at the new sentence
  const before = await page.$eval("#pane", (p) => p.scrollTop);
  await page.click('.rv-claim[data-a="3"] .rv-quote');
  await page.waitForFunction(() => CSS.highlights.get("rv-focus")?.size === 1);
  const focusText = await page.evaluate(() => [...CSS.highlights.get("rv-focus")][0].toString());
  if (!focusText.includes("larger samples did not remove the bias")) fail("jump target: " + focusText);
  await page.waitForTimeout(500);
  const after = await page.$eval("#pane", (p) => p.scrollTop);
  if (!(after > before)) fail("paper scrolled to the claim");
  await shot("jump-dark");
  // Clicking a marked sentence in the paper selects its card
  const pt = await page.evaluate(() => { const hl = [...CSS.highlights.get("rv-needs_revision")][0]; const r = hl.getClientRects()[0]; return { x: r.left + 6, y: r.top + r.height / 2 }; });
  await page.mouse.click(pt.x, pt.y);
  await page.waitForSelector('.rv-claim.on[data-a="5"]');
  step("claims marked in the paper and linked both ways");

  // 3. Filters re-render only the list
  // (by the reviewer's verdict; the outcome line says what the revision did)
  const afterRev = await page.textContent(".rv-sec .rv-note.t3");
  if (!afterRev.includes("5 resolved") || !afterRev.includes("1 unresolved") || !afterRev.includes("1 removed")) fail("after-revision tally: " + afterRev);
  await page.click('[data-rv-filter="rejected"]');
  if ((await page.$$(".rv-claim")).length !== 2) fail("rejected filter");
  const outs = await page.$$eval(".rv-claim .rv-out b", (els) => els.map((e) => e.textContent));
  if (outs.join("|") !== "Resolved in the revision.|Removed from the paper in the revision.") fail("outcomes " + outs);
  await page.click('[data-rv-filter="needs_revision"]');
  if ((await page.$$(".rv-claim")).length !== 1) fail("needs revision filter");
  if ((await page.getAttribute('[data-rv-filter="needs_revision"]', "aria-pressed")) !== "true") fail("filter pressed");
  await page.click('[data-rv-filter="all"]');

  // 4. Resize by dragging and from the keyboard; the width persists
  const grip = await page.$(".rv-grip");
  const gb = await grip.boundingBox();
  await page.mouse.move(gb.x + 4, gb.y + 200);
  await page.mouse.down();
  await page.mouse.move(gb.x - 60, gb.y + 200, { steps: 4 });
  await page.mouse.move(gb.x - 116, gb.y + 200, { steps: 4 });
  await page.mouse.up();
  let w = await page.$eval("#review", (e) => e.getBoundingClientRect().width);
  if (Math.abs(w - 540) > 3) fail("dragged width " + w);
  await grip.focus();
  await page.keyboard.press("ArrowLeft");
  w = await page.$eval("#review", (e) => e.getBoundingClientRect().width);
  if (Math.abs(w - 556) > 3) fail("keyboard width " + w);
  const vnow = await grip.getAttribute("aria-valuenow");
  if (Math.abs(+vnow - w) > 1) fail("aria-valuenow " + vnow + " vs " + w);
  await page.keyboard.press("End");
  w = await page.$eval("#review", (e) => e.getBoundingClientRect().width);
  if (Math.abs(w - 320) > 3) fail("minimum width " + w);
  await page.mouse.move(gb.x, gb.y + 200); // drag past the maximum is clamped
  const g2 = await grip.boundingBox();
  await page.mouse.move(g2.x + 4, g2.y + 200);
  await page.mouse.down();
  await page.mouse.move(100, g2.y + 200, { steps: 6 });
  await page.mouse.up();
  w = await page.$eval("#review", (e) => e.getBoundingClientRect().width);
  if (w > 760.5) fail("maximum width " + w);
  await page.dblclick(".rv-grip");
  w = await page.$eval("#review", (e) => e.getBoundingClientRect().width);
  if (Math.abs(w - 420) > 3) fail("double-click reset " + w);
  await grip.focus();
  for (let i = 0; i < 3; i++) await page.keyboard.press("Shift+ArrowLeft");
  if ((await page.evaluate(() => localStorage.getItem("plato_review_w"))) !== "612") fail("width saved");
  step("resize by drag, keyboard and double-click, clamped and saved");

  // 5. Close (button and Escape), reopen from the bar; state persists across reloads
  await page.click("[data-rv-close]");
  await page.waitForSelector("#review[hidden]", { state: "attached" });
  if ((await page.evaluate(() => CSS.highlights.size)) !== 0) fail("marks cleared when closed");
  const full = await page.$eval("#pane", (p) => p.getBoundingClientRect().width);
  if (full < 1100) fail("paper takes the width when the panel is closed: " + full);
  if ((await page.getAttribute("[data-rv-toggle]", "aria-expanded")) !== "false") fail("toggle state");
  await shot("closed-dark");
  await page.reload();
  await page.waitForSelector("#pane .ms-paper");
  if (!(await page.$("#review[hidden]"))) fail("closed state persisted");
  await page.click("[data-rv-toggle]");
  await page.waitForSelector("#review:not([hidden])");
  w = await page.$eval("#review", (e) => e.getBoundingClientRect().width);
  if (Math.abs(w - 612) > 3) fail("width persisted " + w);
  await page.focus("#review .rv-claim .rv-quote");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#review[hidden]", { state: "attached" });
  await page.click("[data-rv-toggle]");
  await page.dblclick(".rv-grip");
  step("close, Escape, reopen, persisted");

  // 6. PDF: typeset on first view, cached after; LaTeX with the PDF beside it
  await page.click('[data-ms="pdf"]');
  await page.waitForSelector("iframe.pdf-frame");
  const src = await page.getAttribute("iframe.pdf-frame", "src");
  if (!src.startsWith("blob:")) fail("pdf frame src " + src);
  const magic = await page.evaluate(async (u) => { const b = new Uint8Array(await (await fetch(u)).arrayBuffer()); return String.fromCharCode(...b.slice(0, 5)) + b.length; }, src.split("#")[0]);
  if (!magic.startsWith("%PDF-")) fail("pdf bytes " + magic);
  const dl = await page.getAttribute('a[download]', "href");
  const res = await api(dl.replace("/api/", ""));
  if (res.status !== 200 || res.type !== "application/pdf") fail("download link " + JSON.stringify(res));
  if (!(await page.$("#review:not([hidden])"))) fail("panel stays beside the PDF");
  await shot("pdf-dark");
  await page.click('[data-ms="src"]');
  await page.click("[data-ms-split]");
  await page.waitForSelector(".ms-split pre.src + iframe.pdf-frame");
  if ((await page.getAttribute("[data-ms-split]", "aria-pressed")) !== "true") fail("split pressed");
  await shot("latex-pdf-dark");
  await page.click("[data-ms-split]");
  await page.click('[data-ms="paper"]');
  await page.waitForFunction(() => CSS.highlights.get("rv-approved")?.size === 5);
  step("PDF view, download, LaTeX beside the PDF");

  // 7. The live paper card on Overview shows one review line and opens the panel
  await page.evaluate(() => localStorage.setItem("plato_review_open", "0"));
  await page.goto(`${BASE}/#/c/${cid}/overview`);
  await page.reload();
  await page.waitForSelector("#props");
  await page.click('#props [data-pv="paper"]');
  await page.waitForSelector("#props .rv-strip");
  const strip = await page.textContent("#props .rv-strip");
  if (!strip.includes("Minor revision") || !strip.includes("4 approved · 1 needs revision · 2 rejected")) fail("strip " + strip);
  await page.click("#props [data-rv-open]");
  await page.waitForSelector("#review:not([hidden]) .rv-claim");
  step("review line on the live paper opens the panel");

  // 8. Light theme
  await page.emulateMedia({ colorScheme: "light" });
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  await page.waitForTimeout(200);
  await shot("panel-light");
  await page.evaluate(() => document.documentElement.removeAttribute("data-theme"));
  await page.emulateMedia({ colorScheme: "dark" });

  // 9. Small screens: the panel slides over the paper and has no resize grip
  await page.setViewportSize({ width: 820, height: 900 });
  await page.reload();
  await page.waitForSelector("#pane .ms-paper");
  const pos = await page.$eval("#review", (e) => [getComputedStyle(e).position, e.getBoundingClientRect().width, getComputedStyle(e.querySelector(".rv-grip")).display]);
  if (pos[0] !== "fixed" || pos[1] > 441 || pos[2] !== "none") fail("small-screen panel " + pos);
  await shot("narrow-dark");
  await page.setViewportSize({ width: 1440, height: 900 });

  // 10. A review from before claim-by-claim verdicts still renders (required changes only)
  await page.route(`**/api/campaigns/${cid}/manuscript`, async (route) => {
    const r = await route.fetch(); const m = await r.json();
    m.peer_review = JSON.stringify({ soundness: 2, presentation: 3, contribution: 2, decision: "major_revision", summary: "Legacy review.", required_changes: ["State n."] });
    route.fulfill({ response: r, json: m });
  });
  await page.reload();
  await page.waitForSelector("#review .rv-verdict");
  const legacy = await page.textContent("#review");
  if (!legacy.includes("Major revision") || !legacy.includes("State n.") || (await page.$(".rv-claim"))) fail("legacy review");
  if (!(await page.$("#review details.rv-fold[open]"))) fail("reviewer panel open for legacy reviews");
  await page.unroute(`**/api/campaigns/${cid}/manuscript`);
  step("legacy review renders");

  if (errors.length) fail("console errors:\n" + errors.join("\n"));
  await browser.close();
  console.log("review UI: all checks passed");
})().catch((e) => { console.error(e); process.exit(1); });

