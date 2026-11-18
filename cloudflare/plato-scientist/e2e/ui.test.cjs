// End-to-end UI check of accounts, the agent home, projects, the ask panel and settings.
// Run against wrangler dev with the stub Messages API: node e2e/ui.test.cjs <screenshot dir>
// Fails on any console error or page error that a step did not expect.
const { chromium } = require("playwright");
const BASE = process.env.PLATO_E2E_BASE || "http://127.0.0.1:8787";
// These tests sign up accounts and use the dev admin token: local wrangler dev only.
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE)) throw new Error("PLATO_E2E_BASE must be a local wrangler dev URL");

const OUT = process.argv[2] || ".";
const email = `ui${Date.now()}@example.com`, pw = "correct horse battery";
let expected = [];
let PAGE = null;          // substrings of console errors a step triggers on purpose
const errors = [];
const step = (m) => console.log("·", m);
const fail = (m) => { throw new Error(m); };

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
  const page = PAGE = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") { const t = m.text() + " @ " + (m.location()?.url || ""); if (!expected.some((e) => t.includes(e))) errors.push(t); } });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/api/")) console.log("  http", r.status(), r.request().method(), r.url().replace(BASE, "")); });
  const shot = (n) => page.screenshot({ path: `${OUT}/ui-${n}.png` });
  const css = (sel, prop) => page.$eval(sel, (el, p) => getComputedStyle(el)[p], prop);

  // 1. signed out → login
  await page.goto(BASE + "/#/c/00000000-0000-4000-8000-000000000000/overview");
  await page.waitForSelector("#authForm");
  if (!page.url().endsWith("#/login")) fail("not redirected to login: " + page.url());
  if (await page.isVisible(".app")) fail("app visible while signed out");
  await shot("login-dark");
  step("signed out → login screen");

  // 2. sign up
  await page.click('a[href="#/signup"]');
  await page.waitForSelector('#authForm input[name="name"]');
  await page.fill('input[name="name"]', "Ada Lovelace");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', "short");
  await page.click("#authBtn");
  await page.waitForSelector("#authErr:not([hidden])");
  await page.fill('input[name="password"]', pw);
  await shot("signup-dark");
  await page.click("#authBtn");
  // the deep link from before sign-in is restored (and 404s, since that campaign doesn't exist)
  await page.waitForFunction(() => location.hash.startsWith("#/c/00000000"));
  expected.push("404 (Not Found) @ " + BASE + "/api/campaigns/00000000-0000-4000-8000-000000000000");
  await page.waitForSelector("#pane .empty h3");
  step("sign up → deep link restored");

  // 3. agent home is the default
  await page.goto(BASE + "/#/");
  await page.waitForSelector(".ah h1");
  const h1 = await page.textContent(".ah h1");
  if (!h1.includes("Ada")) fail("greeting: " + h1);
  if (await page.isVisible("#askFab")) fail("ask button shown on the agent page");
  // Linear custom theme (dark): #101010 frame, #171717 raised panel, blue pill primary
  await page.goto(BASE + "/#/campaigns");
  await page.waitForSelector("#newTop");
  const bg = await css("#newTop", "backgroundColor"), fg = await css("#newTop", "color"), br = await css("#newTop", "borderTopLeftRadius");
  if (bg !== "rgb(0, 147, 255)" || fg !== "rgb(253, 254, 255)" || parseFloat(br) < 14) fail(`primary button ${bg} / ${fg} / ${br}`);
  const shell = await page.evaluate(() => {
    const g = (sel, p) => getComputedStyle(document.querySelector(sel))[p];
    return { body: g("body", "backgroundColor"), main: g(".main", "backgroundColor"), frame: g(".main", "borderTopColor"), radius: g(".main", "borderTopLeftRadius"),
      nav: g(".item.on", "backgroundColor"), text: g("body", "color") };
  });
  const want = { body: "rgb(16, 16, 16)", main: "rgb(23, 23, 23)", frame: "rgb(40, 40, 42)", radius: "12px", nav: "rgba(255, 255, 255, 0.11)", text: "rgb(228, 228, 230)" };
  for (const k of Object.keys(want)) if (shell[k] !== want[k]) fail(`theme ${k}: ${shell[k]} (want ${want[k]})`);
  if (!(await page.isVisible("#askFab"))) fail("ask button missing on campaigns");
  const glint = await page.$eval("#askFab .glint", (el) => ({ style: el.getAttribute("style"), inner: el.firstElementChild.getAttribute("aria-hidden"), vars: el.firstElementChild.firstElementChild.getAttribute("style") }));
  if (!glint.style.includes("top: -7px") || glint.inner !== "true" || !glint.vars.includes("--x-backgroundColor: lch(100% 0 0 / 0.15)")) fail("glint markup " + JSON.stringify(glint));
  await shot("campaigns-dark");
  step("agent home default; Linear theme shell and blue primary; ask button with glint");

  // 4. prompt the agent from home → project; the orchestrator starts a research thread
  await page.goto(BASE + "/#/agent");
  await page.waitForSelector("#homeC textarea");
  await shot("agent-home-dark");
  await page.fill("#homeC textarea", "Please research whether OLS intervals keep coverage under heteroskedasticity");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => location.hash.startsWith("#/p/"));
  await page.waitForSelector("#chatIn .msg.me .bubble");
  await page.waitForSelector("#chatIn a.tcard", { timeout: 30000 });
  await page.waitForFunction(() => !document.querySelector("#chatIn .thinking") && document.querySelectorAll("#chatIn .msg.ai .md").length >= 2, null, { timeout: 30000 });
  await page.waitForSelector("#threads a.trow");
  await page.waitForSelector('#nav [data-sec="projects"]');
  await shot("project-dark");
  step("home prompt → project → thread card and threads panel");

  // follow-up in the project
  await page.fill("#projC textarea", "Thanks, what is the status?");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => [...document.querySelectorAll("#chatIn .tool")].some((t) => t.textContent.includes("Checked research threads")), null, { timeout: 30000 });
  step("follow-up runs list_threads");

  // 5. open the thread → campaign; ⌘J opens the ask panel with that thread as context
  const threadHref = await page.getAttribute("#threads a.trow", "href");
  await page.click("#threads a.trow");
  await page.waitForFunction((h) => location.hash === h, threadHref);
  await page.waitForSelector("#tabs a.tab.on");
  const pill = await page.evaluate(() => { const on = getComputedStyle(document.querySelector("#tabs a.tab.on")), off = getComputedStyle(document.querySelector("#tabs a.tab:not(.on)"));
    return { on: on.backgroundColor, onC: on.color, off: off.backgroundColor, offC: off.color, h: on.height, r: on.borderTopLeftRadius }; });
  if (pill.on !== "rgb(49, 49, 50)" || pill.onC !== "rgb(255, 255, 255)" || pill.off !== "rgb(34, 34, 34)" || pill.offC !== "rgb(152, 153, 154)" || pill.h !== "28px" || parseFloat(pill.r) < 14)
    fail("pill tabs " + JSON.stringify(pill));
  await shot("campaign-dark");
  await page.waitForSelector("#askFab:not([hidden])");
  await page.keyboard.press("Control+j");
  await page.waitForSelector("#ask:not([hidden]) #askC textarea");
  await page.waitForSelector("#askC .ctx");
  if (await page.isVisible("#askFab")) fail("ask button visible while the panel is open");
  await shot("ask-empty-dark");
  await page.fill("#askC textarea", "Explain this thread in plain words");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => [...document.querySelectorAll("#askIn .md")].some((m) => m.textContent.includes("You said: Explain this thread")), null, { timeout: 30000 });
  await page.waitForSelector("#askIn .ctxchip");
  await shot("ask-answer-dark");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#ask", { state: "hidden" });
  await page.waitForSelector("#askFab:not([hidden])");
  // reopening restores the same conversation
  await page.click("#askBtn");
  await page.waitForFunction(() => [...document.querySelectorAll("#askIn .md")].some((m) => m.textContent.includes("You said")), null, { timeout: 15000 });
  await page.keyboard.press("Escape");
  step("⌘J ask panel with thread context; Esc closes; conversation persists");

  // 6. settings: preferences
  await page.click("#acct");
  await page.waitForSelector(".set h1");
  if ((await page.textContent(".set h1")) !== "Preferences") fail("settings landing");
  if (!(await page.isVisible("#nav .back"))) fail("settings nav back link");
  const sw = await page.$eval('input.switch[data-pref="open_paper_while_writing"]', (el) => ({ w: el.offsetWidth, h: el.offsetHeight, bg: getComputedStyle(el).backgroundColor, on: el.checked }));
  if (sw.w !== 30 || sw.h !== 18 || !sw.on || sw.bg !== "rgb(52, 199, 89)") fail("switch on " + JSON.stringify(sw));
  const off = await css('input.switch[data-pref="reduce_motion"]', "backgroundColor");
  if (off !== "rgba(120, 120, 128, 0.36)") fail("switch off dark " + off);
  await shot("settings-prefs-dark");
  await page.click('input.switch[data-pref="reduce_motion"]');
  await page.waitForFunction(() => document.documentElement.dataset.motion === "reduce");
  await page.selectOption('select[data-pref="theme"]', "light");
  await page.waitForFunction(() => document.documentElement.dataset.theme === "light");
  await page.waitForTimeout(400);
  const offL = await css('input.switch[data-pref="send_with_mod_enter"]', "backgroundColor");
  if (offL !== "rgb(233, 233, 234)") fail("switch off light " + offL);
  await shot("settings-prefs-light");
  await page.reload();
  await page.waitForSelector(".set h1");
  if (!(await page.isChecked('input.switch[data-pref="reduce_motion"]'))) fail("reduce motion not persisted");
  if ((await page.evaluate(() => document.documentElement.dataset.theme)) !== "light") fail("theme not persisted");
  await page.click('input.switch[data-pref="reduce_motion"]');
  await page.selectOption('select[data-pref="theme"]', "dark");
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark" && document.documentElement.dataset.motion === "");
  step("preferences: switches, theme, reduce motion persist");

  // profile
  await page.click('#nav a[href="#/settings/profile"]');
  await page.waitForSelector("#nameIn");
  await page.fill("#nameIn", "Ada King");
  await page.press("#nameIn", "Enter");
  await page.waitForFunction(() => document.querySelector("#acct").textContent.includes("Ada King"));
  await shot("settings-profile-dark");
  step("profile name updates the account chip");

  // API key: bad, then good, then remove
  await page.click('#nav a[href="#/settings/api-key"]');
  await page.waitForSelector("#keyForm");
  await page.fill('#keyForm input[name="key"]', "sk-ant-bad-0000000000000000000000000");
  expected.push("422 (Unprocessable Entity) @ " + BASE + "/api/me/key");
  await page.click("#keyForm button");
  await page.waitForSelector(".toast", { timeout: 10000 });
  await page.fill('#keyForm input[name="key"]', "sk-ant-good-0000000000000000000wxyz");
  await page.click("#keyForm button");
  await page.waitForSelector('[data-act="key-remove"]', { timeout: 10000 });
  const keyText = await page.textContent("#pane");
  if (!keyText.includes("sk-ant-…wxyz") || keyText.includes("0000000000000000000wxyz")) fail("key display");
  await shot("settings-key-dark");
  await page.click('[data-act="key-remove"]');
  await page.click("#cfYes");
  await page.waitForSelector("#keyForm");
  await page.waitForSelector(".meter");
  step("API key: rejected bad key, saved good key (last4 only), removed");

  // security: sessions; admin token → members
  await page.click('#nav a[href="#/settings/security"]');
  await page.waitForFunction(() => document.querySelector("#sessions")?.textContent.includes("This device"));
  await page.fill('#adminForm input[name="token"]', "wrong");
  expected.push("403 (Forbidden) @ " + BASE + "/api/me/admin");
  await page.click("#adminForm button");
  await page.waitForSelector(".toast");
  await page.fill('#adminForm input[name="token"]', "dev");
  await page.click("#adminForm button");
  await page.waitForSelector('#nav a[href="#/settings/members"]');
  await shot("settings-security-dark");
  await page.click('#nav a[href="#/settings/members"]');
  await page.waitForSelector("#members table.members tbody tr td.who");
  await shot("settings-members-dark");
  step("security sessions; admin claim; members table");

  // 7. log out → login → back in
  await page.click('#nav a[href="#/settings/security"]');
  await page.click('[data-act="logout"]');
  await page.waitForSelector("#authForm");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', "wrong password!!");
  expected.push("401 (Unauthorized) @ " + BASE + "/api/auth/login");
  await page.click("#authBtn");
  await page.waitForSelector("#authErr:not([hidden])");
  await page.fill('input[name="password"]', pw);
  await page.click("#authBtn");
  await page.waitForSelector(".ah h1, .set h1");
  step("log out, wrong password, log in");

  // 8. command menu lists projects
  await page.goto(BASE + "/#/campaigns");
  await page.waitForSelector("#newTop");
  await page.keyboard.press("Control+k");
  await page.waitForSelector("#cmdL .cmd-s");
  const secs = await page.$$eval("#cmdL .cmd-s", (e) => e.map((x) => x.textContent));
  if (!secs.includes("Projects")) fail("command menu sections " + secs);
  await page.keyboard.press("Escape");
  step("command menu has projects");

  // 9. light theme screenshots and phone width
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto(BASE + "/#/settings/preferences");
  await page.waitForSelector('select[data-pref="theme"]');
  await page.selectOption('select[data-pref="theme"]', "system");
  await page.waitForFunction(() => document.documentElement.dataset.theme === "light");
  await page.goto(BASE + "/#/agent");
  await page.waitForSelector("#homeC");
  await shot("agent-home-light");
  const pbg = await page.$eval(".btn.primary, .send", (el) => getComputedStyle(el).backgroundColor);
  console.log("  light primary/send bg", pbg);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  await shot("m-agent-light");
  const proj = await page.$$eval("#recent a.prow", (as) => as.map((a) => a.getAttribute("href")).at(-1));
  await page.goto(BASE + "/" + proj);
  await page.waitForSelector("#thBtn", { state: "visible", timeout: 10000 });
  await shot("m-project-light");
  await page.click("#thBtn");
  await page.waitForSelector("#props a.trow");
  await shot("m-threads-light");
  await page.keyboard.press("Escape");
  await page.goto(BASE + "/#/campaigns");
  await page.waitForSelector("#askFab:not([hidden])");
  await page.click("#askBtn");
  await page.waitForSelector("#ask:not([hidden])");
  await shot("m-ask-light");
  await page.keyboard.press("Escape");
  await page.goto(BASE + "/#/settings/api-key");
  await page.waitForSelector(".set h1");
  await shot("m-settings-light");
  const ow = await page.evaluate(() => document.documentElement.scrollWidth);
  if (ow > 390) fail("horizontal overflow at 390px: " + ow);
  step("light theme and 390px layouts");

  await browser.close();
  if (errors.length) { console.log("CONSOLE ERRORS:\n" + errors.join("\n")); process.exit(1); }
  console.log("PASS, no unexpected console errors");
})().catch(async (e) => { console.error("FAIL", e.message); try { await PAGE.screenshot({ path: OUT + "/ui-fail.png" }); console.log("hash", await PAGE.evaluate(() => location.hash)); console.log((await PAGE.textContent("#body")).slice(0, 1500)); } catch {} if (errors.length) console.log("CONSOLE ERRORS:\n" + errors.join("\n")); process.exit(1); });
