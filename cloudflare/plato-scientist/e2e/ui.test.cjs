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
  const doc = await page.goto(BASE + "/#/c/00000000-0000-4000-8000-000000000000/overview");
  // public/_headers: the page runs under the CSP (any violation is a console error, failing below).
  const hdr = await doc.allHeaders();
  if (!/script-src 'self' 'sha256-/.test(hdr["content-security-policy"] || "")) fail("no CSP on the page: " + hdr["content-security-policy"]);
  if (hdr["x-frame-options"] !== "SAMEORIGIN" || !hdr["strict-transport-security"]) fail("security headers missing");
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
  await page.waitForSelector("#homeC textarea");
  if (await page.isVisible("#askFab")) fail("ask button shown on the agent page");
  // Linear's Agent page, measured: 712×104 composer (#1b1b1c, 10px radius, 12px padding, 15/24 weight-450
  // editor), 24px blue send that stays enabled, 336px watermark 208px above it, three 135px example cards
  const home = await page.evaluate(() => {
    const g = (s) => document.querySelector(s), cs = (s) => getComputedStyle(g(s)), r = (s) => g(s).getBoundingClientRect();
    const comp = cs("#homeC"), ta = cs("#homeC textarea"), send = cs("#homeC .send");
    return { title: g("#chatT").textContent.trim(), ph: g("#homeC textarea").placeholder, w: Math.round(r("#homeC").width), h: Math.round(r("#homeC").height),
      bg: comp.backgroundColor, radius: comp.borderTopLeftRadius, pad: comp.paddingTop, font: `${ta.fontSize}/${ta.lineHeight}/${ta.fontWeight}`,
      send: `${send.backgroundColor} ${send.width} ${send.height}`, sendOn: !g("#homeC .send").disabled, plus: cs("#homeC [data-add]").width,
      wm: document.querySelectorAll(".ah-wm path").length, wmGap: Math.round(r("#homeC").top - r(".ah-wm").top),
      cards: [...document.querySelectorAll(".ah-card")].map((c) => Math.round(c.getBoundingClientRect().height)), chip: g(".ah-chip")?.getAttribute("href") };
  });
  const wantHome = { title: "New chat", ph: "Ask Plato…", w: 712, h: 104, bg: "rgb(27, 27, 28)", radius: "10px", pad: "12px", font: "15px/24px/450",
    send: "rgb(0, 147, 255) 24px 24px", sendOn: true, plus: "24px", wm: 10, wmGap: 208, cards: [135, 135, 135], chip: "#/settings/api-key" };
  for (const k of Object.keys(wantHome)) if (JSON.stringify(home[k]) !== JSON.stringify(wantHome[k])) fail(`agent home ${k}: ${JSON.stringify(home[k])} (want ${JSON.stringify(wantHome[k])})`);
  await page.click("#chatT");
  await page.waitForSelector("#chatM:not([hidden]) .mi-e");
  if ((await page.textContent("#chatM .mi-e")) !== "No history") fail("chat menu without history");
  const menu = await page.$eval("#chatM", (m) => { const s = getComputedStyle(m); return `${s.backgroundColor} ${s.borderTopLeftRadius} ${m.offsetWidth}`; });
  if (menu !== "rgb(40, 40, 40) 12px 321") fail("chat menu style " + menu);
  await page.keyboard.press("Escape");
  await page.waitForSelector("#chatM", { state: "hidden" });
  await page.click('.ah-card[data-ex="1"]');
  if ((await page.inputValue("#homeC textarea")) !== (await page.evaluate(() => EXAMPLES[1].q))) fail("example card did not fill the composer");
  // "Show other examples" pages through all six, three at a time, keeping Linear's card geometry
  await page.click(".ah-exh [data-ex-more]");
  const page2 = await page.$$eval(".ah-card", (cs) => cs.map((c) => `${c.dataset.ex}:${Math.round(c.getBoundingClientRect().height)}`).join(","));
  if (page2 !== "3:135,4:135,5:135") fail("second examples page " + page2);
  await page.click('.ah-card[data-ex="4"]');
  if (!(await page.inputValue("#homeC textarea")).includes("Pantheon+")) fail("second-page card did not fill the composer");
  await page.click(".ah-exh [data-ex-more]");
  if ((await page.$$eval(".ah-card", (cs) => cs.map((c) => c.dataset.ex).join(","))) !== "0,1,2") fail("examples did not wrap to the first page");
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
  step("agent home default, Linear Agent composer, watermark, examples and chat menu; theme shell; ask button with glint");

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
  const conv = await page.evaluate(() => ({ title: document.querySelector("#chatT").textContent.trim(), bubble: getComputedStyle(document.querySelector("#chatIn .bubble")).backgroundColor,
    md: getComputedStyle(document.querySelector("#chatIn .md")).fontSize, col: Math.round(document.querySelector("#chatIn").getBoundingClientRect().width) }));
  if (conv.title !== "Please research whether OLS intervals keep coverage under heteroskedasticity" || conv.bubble !== "rgb(27, 27, 28)" || conv.md !== "15px" || conv.col > 712)
    fail("conversation shell " + JSON.stringify(conv));
  await page.click("#chatT");
  await page.waitForSelector('#chatM:not([hidden]) [data-pm="delete"]');
  const items = await page.$$eval("#chatM .mi", (ms) => ms.map((m) => (m.getAttribute("aria-current") ? "*" : "") + m.textContent.trim().split("\n")[0]));
  if (items[0] !== "New chat" || !items.some((t) => t.startsWith("*Please research")) || !items.includes("Rename…")) fail("project chat menu " + JSON.stringify(items));
  await page.keyboard.press("Escape");
  await shot("project-dark");
  step("home prompt → project → thread card, threads panel, title menu");

  // follow-up in the project, with the new thread attached through "+"
  await page.click("#projC [data-add]");
  await page.waitForSelector("#projC .menu:not([hidden]) [data-pick]", { timeout: 15000 });
  await page.click("#projC .menu [data-pick]");
  await page.waitForSelector("#projC .ctx");
  await page.fill("#projC textarea", "Thanks, what is the status?");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => [...document.querySelectorAll("#chatIn .tool")].some((t) => t.textContent.includes("Checked research threads")), null, { timeout: 30000 });
  await page.waitForSelector("#chatIn .msg.me .ctxchip");
  if (await page.isVisible("#projC .ctx")) fail("attached thread not cleared after sending");
  step("follow-up with a thread attached by + runs list_threads; context chip on the message");

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
  await page.waitForSelector("#homeC, .set h1");
  step("log out, wrong password, log in");

  // 8. command menu lists projects
  await page.goto(BASE + "/#/campaigns");
  await page.waitForSelector("#newTop");
  await page.waitForSelector('#nav [data-sec="projects"]');   // projects load after sign-in; wait for them
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
  await page.click(".ah-exh [data-ex-x]");
  await page.waitForSelector("#ahEx", { state: "detached" });
  await page.reload();
  await page.waitForSelector("#homeC");
  if (await page.$("#ahEx")) fail("dismissed examples came back");
  // After the reload the nav fills in asynchronously: wait for the project links before reading one.
  await page.waitForSelector('#nav a.item[href^="#/p/"]');
  const proj = await page.$$eval('#nav a.item[href^="#/p/"]', (as) => as.map((a) => a.getAttribute("href")).at(-1));
  if (!proj) fail("no project in the nav");
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
  step("light theme and 390px layouts; examples stay dismissed");

  await browser.close();
  if (errors.length) { console.log("CONSOLE ERRORS:\n" + errors.join("\n")); process.exit(1); }
  console.log("PASS, no unexpected console errors");
})().catch(async (e) => { console.error("FAIL", e.message); try { await PAGE.screenshot({ path: OUT + "/ui-fail.png" }); console.log("hash", await PAGE.evaluate(() => location.hash)); console.log((await PAGE.textContent("#body")).slice(0, 1500)); } catch {} if (errors.length) console.log("CONSOLE ERRORS:\n" + errors.join("\n")); process.exit(1); });
