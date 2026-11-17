/* Plato UI kit: smart skeletons, text morph, live charts (Liveline) and layout
   transitions. Framework free and app agnostic. Every effect degrades to an instant
   update under prefers-reduced-motion, and nothing here throws into the console. */
(() => {
"use strict";
const RM = matchMedia("(prefers-reduced-motion: reduce)");
const still = () => RM.matches;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const quiet = p => { p?.catch?.(() => {}); return p; };

/* ---------- spring easing ----------
   A damped spring (k=260, c=24, m=1: ~3% overshoot) sampled into CSS linear(), so CSS
   transitions, WAAPI and view transitions all share one motion curve. */
const SPRING = (() => {
  const k = 260, c = 24, w0 = Math.sqrt(k), z = c / (2 * w0), wd = w0 * Math.sqrt(1 - z * z);
  const x = t => 1 - Math.exp(-z * w0 * t) * (Math.cos(wd * t) + (z * w0 / wd) * Math.sin(wd * t));
  let T = 0;
  for (let t = 0; t < 2; t += 1 / 240) if (Math.abs(1 - x(t)) > 0.002) T = t;
  T += 1 / 240;
  const pts = Array.from({length: 41}, (_, i) => +x(T * i / 40).toFixed(4));
  pts[40] = 1;
  const ok = CSS.supports("transition-timing-function", "linear(0, 1)");
  return {ms: Math.round(T * 1000), ease: ok ? `linear(${pts.join(", ")})` : "cubic-bezier(.22,1,.36,1)"};
})();
const OUT = "cubic-bezier(.22,1,.36,1)";
document.documentElement.style.setProperty("--spring", SPRING.ease);
document.documentElement.style.setProperty("--spring-ms", SPRING.ms + "ms");

/* ---------- smart skeletons ----------
   The real view is rendered with sample data, laid out but invisible; its text lines and
   boxes are measured and replaced by bars, so the skeleton matches the final layout and
   nothing shifts when data arrives. Bars share one shimmer phase across the page; the
   skeleton only appears after 150 ms, so fast loads never flash it. */
const BOX = "svg,img,canvas,.chip,.btn,.bar,.field,.seg,.pips,.kbd,.live,[data-sk-box]";
const HOLD = 150, PERIOD = 1600;
const T0 = new Map();
/** Skeleton markup for a string template; paint(root) measures it once it is in the DOM. */
const skel = (html, key) => { if (key != null && !T0.has(key)) T0.set(key, performance.now()); return skelHtml(html); };
const skelHtml = html => `<div class="sk" data-sk><span class="sr" role="status">Loading…</span><div class="sk-src" inert aria-hidden="true">${html}</div><div class="sk-layer" aria-hidden="true"></div></div>`;

function paintOne(sk) {
  const src = sk.querySelector(".sk-src"), layer = sk.querySelector(".sk-layer");
  if (!src || !layer || !sk.isConnected) return;
  const base = sk.getBoundingClientRect();
  if (!base.width) return;
  sk.dataset.w = Math.round(base.width);
  const bars = [], clipOf = new Map();
  const clipFor = el => {  // nearest ancestor that clips overflow (e.g. ellipsis titles)
    if (clipOf.has(el)) return clipOf.get(el);
    let r = null;
    if (el !== src && el.parentElement) {
      const cs = getComputedStyle(el);
      r = cs.overflowX !== "visible" ? el.getBoundingClientRect() : clipFor(el.parentElement);
    }
    clipOf.set(el, r);
    return r;
  };
  const inBox = el => { const a = el.closest(BOX); return a && src.contains(a); };
  src.querySelectorAll(BOX).forEach(el => {
    if (el.parentElement && inBox(el.parentElement)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    const cs = getComputedStyle(el);
    const round = el.tagName.toLowerCase() === "svg" && r.width <= 16 && Math.abs(r.width - r.height) < 1;
    bars.push({l: r.left, t: r.top, w: r.width, h: r.height, rad: round ? "50%" : (parseFloat(cs.borderRadius) ? cs.borderRadius : "4px")});
  });
  const walk = document.createTreeWalker(src, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  let prev = null;
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    const el = n.parentElement;
    if (!n.nodeValue.trim() || !el || inBox(el)) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize) || 13, h = Math.max(6, Math.round(fs * 0.68));
    const clip = clipFor(el);
    range.selectNodeContents(n);
    for (const r of range.getClientRects()) {
      let l = r.left, w = r.width;
      if (clip) { const rr = Math.min(l + w, clip.right); l = Math.max(l, clip.left); w = rr - l; }
      if (w < 2) continue;
      const t = r.top + (r.height - h) / 2;
      if (prev && Math.abs(prev.t - t) < 2 && l - (prev.l + prev.w) < fs * 0.6 && l >= prev.l) {
        prev.w = Math.max(prev.w, l + w - prev.l);
        continue;
      }
      prev = {l, t, w, h, rad: Math.min(4, h / 2) + "px"};
      bars.push(prev);
    }
  }
  layer.style.setProperty("--d", `-${Math.round(performance.now() % PERIOD)}ms`);
  layer.innerHTML = bars.map(b => `<i style="left:${(b.l - base.left).toFixed(1)}px;top:${(b.t - base.top).toFixed(1)}px;width:${b.w.toFixed(1)}px;height:${b.h.toFixed(1)}px;border-radius:${b.rad};--x:${b.l.toFixed(0)}px"></i>`).join("");
}
const RO = typeof ResizeObserver === "function" ? new ResizeObserver(entries => {
  for (const e of entries) {
    const sk = e.target;
    if (!sk.isConnected) { RO.unobserve(sk); continue; }
    if (Math.round(e.contentRect.width) !== +sk.dataset.w) requestAnimationFrame(() => paintOne(sk));
  }
}) : null;
/** Paint every skeleton under root that has not been measured yet. */
function paint(root = document) {
  root.querySelectorAll("[data-sk]:not([data-w])").forEach(sk => { paintOne(sk); RO?.observe(sk); });
}
/** Replace host's content with a skeleton of `sampleHtml`; `key` ties it to reveal(). */
function skeleton(host, sampleHtml, key) {
  if (!host) return;
  host.setAttribute("aria-busy", "true");
  host.innerHTML = skelHtml(sampleHtml);
  T0.set(key ?? host, performance.now());
  paint(host);
}
/** Called after the real content replaced a skeleton: fade it in, staggering a sequence
    of blocks when there are several. Instant when the skeleton never became visible. */
function reveal(host, key) {
  const t0 = T0.get(key ?? host);
  T0.delete(key ?? host);
  if (!host) return;
  host.removeAttribute("aria-busy");
  if (t0 == null || still() || performance.now() - t0 < HOLD) return;
  const seq = host.querySelector("[data-seq]");
  const items = [...(seq || host).children].slice(0, 14);
  const many = items.length > 2;
  items.forEach((el, i) => quiet(el.animate([{opacity: 0, transform: "translateY(4px)"}, {opacity: 1, transform: "none"}],
    {duration: 260, delay: many ? i * 32 : 0, easing: OUT, fill: "backwards"}).finished));
}
/** In-flow swap: new content with the container height easing to its new size. */
function swap(host, html, key) {
  if (!host) return;
  const h0 = host.getBoundingClientRect().height;
  host.innerHTML = html;
  const h1 = host.getBoundingClientRect().height;
  if (!still() && Math.abs(h1 - h0) > 2)
    quiet(host.animate([{height: h0 + "px", overflow: "hidden"}, {height: h1 + "px", overflow: "hidden"}], {duration: SPRING.ms, easing: SPRING.ease}).finished);
  reveal(host, key);
}

/* ---------- text morph ----------
   Glyphs shared by the old and new text glide to their new place (FLIP); the rest blur in
   or out. Numbers key digits by place value so a changed digit rolls in the direction of
   the change. A visually hidden copy carries the text for screen readers. */
const SEG = typeof Intl !== "undefined" && Intl.Segmenter ? new Intl.Segmenter(undefined, {granularity: "grapheme"}) : null;
const glyphs = s => SEG ? Array.from(SEG.segment(s), x => x.segment) : Array.from(s);
const keysOf = (gs, num) => {
  if (num) return gs.map((g, i) => (/\d/.test(g) ? "d" : "s" + g) + ":" + (gs.length - i));
  const n = {};
  return gs.map(g => g + ":" + (n[g] = (n[g] || 0) + 1));
};
/* Glyphs of one word share a nowrap .mw, so morphing text still wraps between words. */
function words(spans) {
  const out = [];
  let w = null;
  for (const s of spans) {
    if (/^[ \t\n]+$/.test(s.textContent)) { w = null; out.push(s); continue; }
    if (!w) { w = document.createElement("span"); w.className = "mw"; out.push(w); }
    w.append(s);
  }
  return out;
}
function build(el, text, num) {
  const gs = glyphs(text), ks = keysOf(gs, num);
  el.innerHTML = `<span class="sr">${esc(text)}</span><span class="mx" aria-hidden="true"></span>`;
  el.lastChild.append(...words(gs.map((g, i) => { const s = document.createElement("span"); s.dataset.k = ks[i]; s.textContent = g; return s; })));
  el.dataset.mt = text;
}
const oneLine = els => new Set(els.map(e => e.offsetTop)).size <= 1;
/** Morph el's text to `text`. opts.num: digit roll; opts.dir: +1 up / -1 down. */
function morph(el, text, opts = {}) {
  if (!el) return;
  text = String(text ?? "");
  const num = opts.num ?? el.hasAttribute("data-num");
  const prev = el.dataset.mt ?? el.textContent;
  if (prev === text && el.dataset.mt != null) return;
  if (still() || !el.isConnected || !el.getClientRects().length) { el.dataset.mt = text; el.textContent = text; return; }
  let mx = el.querySelector(":scope > .mx");
  if (!mx) { build(el, prev, num); mx = el.querySelector(":scope > .mx"); }
  mx.getAnimations({subtree: true}).forEach(a => a.cancel());
  mx.querySelectorAll("[data-out]").forEach(s => s.remove());
  const w0 = mx.getBoundingClientRect().width;
  const old = new Map();
  for (const s of mx.querySelectorAll("[data-k]")) old.set(s.dataset.k, {el: s, x: s.offsetLeft, y: s.offsetTop, g: s.textContent});
  const flat0 = oneLine([...old.values()].map(o => o.el));
  const gs = glyphs(text), ks = keysOf(gs, num);
  let dir = opts.dir;
  if (dir == null) { const a = parseFloat(prev.replace(/[^\d.-]/g, "")), b = parseFloat(text.replace(/[^\d.-]/g, "")); dir = Number.isFinite(a) && Number.isFinite(b) && b < a ? -1 : 1; }
  const used = new Set(), next = [];
  gs.forEach((g, i) => {
    const o = old.get(ks[i]);
    if (o && o.g === g && !used.has(ks[i])) { used.add(ks[i]); next.push({el: o.el, o}); }
    else { const s = document.createElement("span"); s.dataset.k = ks[i]; s.textContent = g; next.push({el: s}); }
  });
  mx.replaceChildren(...words(next.map(n => n.el)));
  el.querySelector(":scope > .sr").textContent = text;
  el.dataset.mt = text;
  const kept = new Set(next.map(n => n.el));
  const exits = [...old.values()].filter(o => !kept.has(o.el));
  for (const o of exits) {
    o.el.dataset.out = "";
    o.el.style.cssText = `position:absolute;left:${o.x}px;top:${o.y}px`;
    mx.append(o.el);
  }
  const w1 = next.reduce((w, n) => Math.max(w, n.el.offsetLeft + n.el.offsetWidth), 0);
  const D = SPRING.ms;
  let entering = 0;
  for (const n of next) {
    if (n.o) {
      const dx = n.o.x - n.el.offsetLeft, dy = n.o.y - n.el.offsetTop;
      if (dx || dy) quiet(n.el.animate([{transform: `translate(${dx}px,${dy}px)`}, {transform: "none"}], {duration: D, easing: SPRING.ease}).finished);
    } else {
      const from = num ? {opacity: 0, transform: `translateY(${dir * 0.55}em)`, filter: "blur(1.5px)"} : {opacity: 0, transform: "scale(.6)", filter: "blur(3px)"};
      quiet(n.el.animate([from, {opacity: 1, transform: "none", filter: "none"}], {duration: D, delay: num ? 0 : Math.min(entering++ * 14, 160), easing: SPRING.ease, fill: "backwards"}).finished);
    }
  }
  for (const o of exits) {
    const to = num ? {opacity: 0, transform: `translateY(${-dir * 0.55}em)`, filter: "blur(1.5px)"} : {opacity: 0, transform: "scale(.6)", filter: "blur(3px)"};
    const a = o.el.animate([{opacity: 1, transform: "none", filter: "none"}, to], {duration: D * 0.55, easing: "cubic-bezier(.4,0,1,1)", fill: "forwards"});
    a.onfinish = () => o.el.remove();
    quiet(a.finished);
  }
  if (flat0 && oneLine(next.map(n => n.el)) && Math.abs(w1 - w0) > 0.5)
    quiet(mx.animate([{width: w0 + "px"}, {width: w1 + "px"}], {duration: D, easing: SPRING.ease}).finished);
}

/* ---------- continuity across re-renders ----------
   Views re-render with innerHTML. Elements marked data-mk remember their last text per
   key, so a re-render morphs from it instead of jumping. */
const MEM = new Map();
function hydrate(root, scope = "") {
  root.querySelectorAll("[data-mk]").forEach(el => {
    if (el.closest(".sk-src")) return;  // skeleton samples never seed the memory
    const k = scope + el.dataset.mk, next = el.textContent, v = parseFloat(el.dataset.v), prev = MEM.get(k);
    MEM.set(k, {t: next, v});
    if (prev && prev.t !== next) {
      el.dataset.mt = prev.t;
      el.textContent = prev.t;
      morph(el, next, {dir: Number.isFinite(v) && Number.isFinite(prev.v) ? (v < prev.v ? -1 : 1) : undefined});
    } else el.dataset.mt = next;
  });
}

/* ---------- live charts ----------
   Liveline draws every chart: React and liveline ship as one vendored IIFE that loads on
   first use. Each chart keeps one element per key, so an innerHTML re-render re-attaches
   the same canvas and React root and the line keeps moving from where it was. */
const LL_SRC = "/vendor/liveline-0.0.7/liveline.js";
let llReady = null;
const loadLL = () => llReady ??= new Promise((ok, no) => {
  if (window.LivelineKit) return ok(window.LivelineKit);
  const s = document.createElement("script");
  s.src = LL_SRC;
  s.async = true;
  s.onload = () => window.LivelineKit ? ok(window.LivelineKit) : no(new Error("The chart library did not start."));
  s.onerror = () => { llReady = null; s.remove(); no(new Error("Could not load the chart library.")); };
  document.head.append(s);
});
const CHARTS = new Map();
/** Mount or update the Liveline chart `key` inside `slot` with Liveline props. */
function chart(slot, key, props) {
  if (!slot) return;
  let c = CHARTS.get(key);
  if (!c) { c = {el: document.createElement("div"), inst: null, props}; c.el.className = "ll-in"; CHARTS.set(key, c); }
  c.props = props;
  if (c.el.parentNode !== slot) slot.replaceChildren(c.el);
  if (c.inst) { c.inst.update(props); return; }
  quiet(loadLL().then(K => { if (!c.inst && CHARTS.get(key) === c) c.inst = K.mount(c.el, c.props); },
    e => { if (c.el.isConnected) { c.el.className = "ll-in ll-err"; c.el.textContent = e.message; } }));
}
/** Unmount charts no longer on the page (their animation loops would keep running). */
function sweepCharts() {
  for (const [k, c] of CHARTS) if (!c.el.isConnected) { c.inst?.unmount(); CHARTS.delete(k); }
}

/* ---------- layout transitions ----------
   View Transitions morph the panes between layouts on the compositor; the transition's
   promises are always handled, so a skipped transition never logs an error. */
function transition(update, cls = "vt") {
  if (still() || typeof document.startViewTransition !== "function") { update(); return Promise.resolve(); }
  const html = document.documentElement;
  html.classList.add(cls);
  let t;
  try { t = document.startViewTransition(update); } catch { html.classList.remove(cls); update(); return Promise.resolve(); }
  quiet(t.ready); quiet(t.updateCallbackDone);
  return quiet(t.finished.finally(() => html.classList.remove(cls)));
}

/* ---------- clipboard + files ---------- */
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {}
  const ta = document.createElement("textarea");
  ta.value = text; ta.setAttribute("readonly", ""); ta.style.cssText = "position:fixed;opacity:0;pointer-events:none";
  document.body.append(ta); ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch {}
  ta.remove();
  return ok;
}
/** Morph a button's label to `done` for a moment (copy, export, request...), then back. */
function flash(btn, done, ms = 1600) {
  const lbl = btn?.querySelector("[data-lbl]") || btn;
  if (!lbl) return;
  const orig = lbl.dataset.orig ?? (lbl.dataset.mt ?? lbl.textContent);
  lbl.dataset.orig = orig;
  morph(lbl, done);
  clearTimeout(btn._ft);
  btn._ft = setTimeout(() => { morph(lbl, orig); delete lbl.dataset.orig; }, ms);
}
/** RFC 4180 CSV. Numbers stay numeric; text that a spreadsheet would run as a formula
    (=, +, -, @ first) is prefixed with an apostrophe. */
function csv(rows) {
  const cell = v => {
    if (v == null) return "";
    if (typeof v === "number") return Number.isFinite(v) ? String(v) : "";
    v = String(v);
    if (/^[=+\-@\t\r]/.test(v)) v = "'" + v;
    return /[",\n\r]/.test(v) || v.startsWith("'") ? `"${v.replace(/"/g, '""')}"` : v;
  };
  return rows.map(r => r.map(cell).join(",")).join("\r\n") + "\r\n";
}
function download(name, text, type = "text/plain") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], {type}));
  a.download = name;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

window.Kit = Object.freeze({still, SPRING, skel, paint, skeleton, reveal, swap, morph, hydrate, chart, sweepCharts, transition, copyText, flash, csv, download});
})();
