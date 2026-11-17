/* Plato UI kit: smart skeletons, text morph, radial / gauge / slope charts and layout
   transitions. Framework free and app agnostic. Every effect degrades to an instant
   update under prefers-reduced-motion, and nothing here throws into the console. */
(() => {
"use strict";
const RM = matchMedia("(prefers-reduced-motion: reduce)");
const still = () => RM.matches;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
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
   Views re-render with innerHTML. Elements marked data-mk (text) or data-arc (chart arc)
   remember their last value per key, so a re-render morphs from it instead of jumping. */
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
  root.querySelectorAll("[data-arc]").forEach((el, i) => {
    if (el.closest(".sk-src")) return;
    const k = scope + el.dataset.arc, da = el.getAttribute("stroke-dasharray"), off = el.getAttribute("stroke-dashoffset") || "0";
    const prev = MEM.get(k);
    MEM.set(k, {da, off});
    if (still() || (prev && prev.da === da && prev.off === off)) return;
    const from = prev || {da: "0 100", off: el.dataset.arc0 || off};
    quiet(el.animate([{strokeDasharray: from.da, strokeDashoffset: from.off}, {strokeDasharray: da, strokeDashoffset: off}],
      {duration: prev ? 700 : 1100, delay: prev ? 0 : 80 + (+el.dataset.i || i) * 90, easing: OUT, fill: "backwards"}).finished);
  });
}

/* ---------- radial charts ---------- */
const arcDash = (v, cap) => v >= 99.95 ? ["100 0", "0"] : v <= 2 * cap ? ["0.001 100", (-v / 2).toFixed(3)] : [`${(v - 2 * cap).toFixed(3)} 100`, (-cap).toFixed(3)];
const pctText = v => Math.round(clamp(v, 0, 1) * 100) + "%";
function legend(id, series) {
  return `<div class="rl" role="list">${series.map(s => `<button type="button" class="rl-i" role="listitem" data-series="${esc(s.key)}" data-cv="${esc(s.cv ?? pctText(s.value))}" data-cl="${esc(s.cl ?? s.label)}">
    <i style="background:${s.color}"></i><span class="trunc">${esc(s.label)}</span><b data-mk="${esc(id)}:l:${esc(s.key)}" data-num data-v="${s.value}">${esc(s.lv ?? pctText(s.value))}</b></button>`).join("")}</div>`;
}
function centre(id, c, style = "") {
  return `<div class="rc"${style ? ` style="${style}"` : ""} data-c0v="${esc(c.value)}" data-c0l="${esc(c.label)}"><b data-mk="${esc(id)}:cv" data-num>${esc(c.value)}</b><span data-mk="${esc(id)}:cl">${esc(c.label)}</span></div>`;
}
/** Concentric rings, one per series (value 0..1), with rounded caps and a centre readout.
    The chart grows with the series count so the readout always gets a `hole`-wide centre. */
function rings({id, series, sw = 8, gap = 3, hole = 88, size, center, label}) {
  size ??= Math.max(140, hole + 2 * sw + 2 * (series.length - 1) * (sw + gap) + 2);
  const c = size / 2, R = c - sw / 2 - 1, inner = R - (series.length - 1) * (sw + gap) - sw / 2;
  const g = series.map((s, i) => {
    const r = R - i * (sw + gap);
    if (r <= sw) return "";
    const v = clamp(s.value, 0, 1) * 100, cap = (sw / 2) / (2 * Math.PI * r) * 100, [da, off] = arcDash(v, cap);
    return `<g data-series="${esc(s.key)}"><circle class="trk" cx="${c}" cy="${c}" r="${r}" stroke-width="${sw}"/>` +
      (v > 0 ? `<circle class="arc" data-arc="${esc(id)}:${esc(s.key)}" data-i="${i}" data-arc0="${(-cap).toFixed(3)}" cx="${c}" cy="${c}" r="${r}" stroke="${s.color}" stroke-width="${sw}" pathLength="100" stroke-dasharray="${da}" stroke-dashoffset="${off}" transform="rotate(-90 ${c} ${c})"/>` : "") +
      `<circle class="hit" cx="${c}" cy="${c}" r="${r}" stroke-width="${sw + gap}"/></g>`;
  }).join("");
  return `<div class="radial" data-radial="${esc(id)}"><div class="rf" style="width:${size}px;height:${size}px">
    <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="${esc(label)}">${g}</svg>${centre(id, center, `padding:0 ${Math.max(0, c - inner + 4).toFixed(1)}px`)}</div>${legend(id, series)}</div>`;
}
/** Semicircle gauge: concentric half rings over the top, readout under the arc. */
function gauge({id, series, w = 196, sw = 10, gap = 6, center, label}) {
  const c = w / 2, R = c - sw / 2 - 1, h = Math.ceil(c + 4);
  const g = series.map((s, i) => {
    const r = R - i * (sw + gap);
    if (r <= sw) return "";
    const d = `M ${(c - r).toFixed(2)} ${c} A ${r} ${r} 0 0 1 ${(c + r).toFixed(2)} ${c}`;
    const v = clamp(s.value, 0, 1) * 100, cap = (sw / 2) / (Math.PI * r) * 100;
    const da = v <= 2 * cap ? "0.001 100" : `${(v - 2 * cap).toFixed(3)} 100`, off = v <= 2 * cap ? (-v / 2).toFixed(3) : (-cap).toFixed(3);
    return `<g data-series="${esc(s.key)}"><path class="trk" d="${d}" stroke-width="${sw}"/>` +
      (v > 0 ? `<path class="arc" data-arc="${esc(id)}:${esc(s.key)}" data-i="${i}" data-arc0="${(-cap).toFixed(3)}" d="${d}" stroke="${s.color}" stroke-width="${sw}" pathLength="100" stroke-dasharray="${da}" stroke-dashoffset="${off}"/>` : "") +
      `<path class="hit" d="${d}" stroke-width="${sw + gap}"/></g>`;
  }).join("");
  return `<div class="radial gauge" data-radial="${esc(id)}"><div class="rf" style="width:${w}px;height:${h}px">
    <svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${esc(label)}">${g}</svg>${centre(id, center)}</div>${legend(id, series)}</div>`;
}
/** Hover or focus a ring or legend entry: isolate it and morph the centre readout. */
function bindRadials(root) {
  root.querySelectorAll("[data-radial]").forEach(ch => {
    if (ch.dataset.bound) return;
    ch.dataset.bound = "1";
    const rc = ch.querySelector(".rc"), cv = rc.querySelector("b"), cl = rc.querySelector("span");
    const set = key => {
      if (ch.dataset.focus === (key || "")) return;
      ch.dataset.focus = key || "";
      ch.classList.toggle("iso", !!key);
      ch.querySelectorAll("[data-series]").forEach(e => e.classList.toggle("on", e.dataset.series === key));
      const li = key && ch.querySelector(`.rl-i[data-series="${CSS.escape(key)}"]`);
      morph(cv, li ? li.dataset.cv : rc.dataset.c0v, {num: true});
      morph(cl, li ? li.dataset.cl : rc.dataset.c0l);
    };
    ch.addEventListener("pointerover", e => { const s = e.target.closest("[data-series]"); if (s) set(s.dataset.series); });
    ch.addEventListener("pointerleave", () => set(null));
    ch.addEventListener("focusin", e => { const s = e.target.closest("[data-series]"); if (s) set(s.dataset.series); });
    ch.addEventListener("focusout", e => { if (!ch.contains(e.relatedTarget)) set(null); });
  });
}

/* ---------- slope chart ----------
   One line per item from a left to a right value, an optional shaded band, labels at the
   right end pushed apart so they never overlap. Hover traces the nearest line; click (or
   Enter) pins it and dims the rest; arrow keys walk the lines; an inspector below says
   what the highlighted line means. Re-measures on resize. */
function slope(host, cfg) {
  if (!host) return;
  host._sl = cfg;
  host.classList.add("sl");
  if (!host._ro && typeof ResizeObserver === "function") {
    host._ro = new ResizeObserver(() => requestAnimationFrame(() => {
      if (!host.isConnected) { host._ro.disconnect(); return; }
      if (host.clientWidth !== host._w) drawSlope(host, false);
    }));
    host._ro.observe(host);
  }
  const first = !MEM.has("slope:" + cfg.key);
  MEM.set("slope:" + cfg.key, 1);
  drawSlope(host, first && !still());
  if (!host._bound) bindSlope(host);
}
function drawSlope(host, animate) {
  const cfg = host._sl, items = cfg.items, W = host.clientWidth;
  host._w = W;
  if (!W) return;
  const narrow = W < 560, H = cfg.height || 280;
  const M = {t: 26, r: narrow ? 20 : Math.min(230, Math.round(W * 0.34)), b: 26, l: 46};
  const xL = M.l + (narrow ? 10 : 28), xR = W - M.r, [lo, hi] = cfg.domain;
  const y = v => M.t + (hi - clamp(v, lo, hi)) / (hi - lo) * (H - M.t - M.b);
  host._geo = {xL, xR, y};
  const ticks = cfg.ticks || [lo, 0, hi];
  let s = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cfg.label)}">`;
  if (cfg.band) s += `<rect class="sl-band" x="${xL}" y="${y(cfg.band[1])}" width="${xR - xL}" height="${y(cfg.band[0]) - y(cfg.band[1])}"/><text class="sl-bl" x="${xR - 6}" y="${y(cfg.band[1]) + 13}" text-anchor="end">${esc(cfg.bandLabel || "")}</text>`;
  for (const t of ticks) s += `<line class="sl-grid${t === 0 ? " z" : ""}" x1="${xL - 6}" x2="${xR}" y1="${y(t)}" y2="${y(t)}"/><text class="sl-tick" x="${xL - 12}" y="${y(t) + 4}" text-anchor="end">${esc(cfg.fmtTick ? cfg.fmtTick(t) : t)}</text>`;
  s += `<line class="sl-axis" x1="${xL}" x2="${xL}" y1="${M.t - 8}" y2="${H - M.b + 4}"/><line class="sl-axis" x1="${xR}" x2="${xR}" y1="${M.t - 8}" y2="${H - M.b + 4}"/>`;
  s += `<text class="sl-head" x="${xL}" y="${M.t - 12}" text-anchor="middle">${esc(cfg.leftLabel)}</text><text class="sl-head" x="${xR}" y="${M.t - 12}" text-anchor="middle">${esc(cfg.rightLabel)}</text>`;
  // Right-end labels: sort by y and relax so neighbours sit at least 15px apart.
  const lab = items.map(it => ({it, y: y(it.right)})).sort((a, b) => a.y - b.y);
  const gapY = 15, top = M.t - 4, bot = H - M.b + 4;
  for (let pass = 0; pass < 40; pass++) {
    let moved = false;
    for (let i = 1; i < lab.length; i++) if (lab[i].y - lab[i - 1].y < gapY) { const d = (gapY - (lab[i].y - lab[i - 1].y)) / 2; lab[i - 1].y -= d; lab[i].y += d; moved = true; }
    if (lab.length) { if (lab[0].y < top) { lab[0].y = top; moved = true; } if (lab[lab.length - 1].y > bot) { lab[lab.length - 1].y = bot; moved = true; } }
    if (!moved) break;
  }
  const maxCh = Math.max(4, Math.floor((M.r - 22) / 6.4));
  items.forEach((it, i) => {
    const y1 = y(it.left), y2 = y(it.right), clipped = it.right > hi || it.right < lo;
    s += `<g class="sl-it" data-id="${esc(it.id)}" style="--c:${it.color}">
      <path class="sl-ln" d="M${xL} ${y1.toFixed(1)}L${xR} ${y2.toFixed(1)}" pathLength="1"${animate ? ` style="--i:${i}" data-draw` : ""}/>
      <circle class="sl-dot" cx="${xL}" cy="${y1.toFixed(1)}" r="3"/><circle class="sl-dot" cx="${xR}" cy="${y2.toFixed(1)}" r="${clipped ? 4 : 3.5}"${clipped ? ' data-clip' : ""}/>`;
    if (!narrow) { const L = lab.find(l => l.it === it), t = it.label.length > maxCh ? it.label.slice(0, maxCh - 1) + "…" : it.label;
      s += `<text class="sl-lab" x="${xR + 10}" y="${(L.y + 4).toFixed(1)}">${esc(t)}</text>`; }
    s += `</g>`;
  });
  s += `</svg>`;
  host.innerHTML = s + `<div class="sl-insp" aria-live="polite"></div>`;
  host.querySelectorAll("[data-draw]").forEach(p => quiet(p.animate([{strokeDashoffset: 1}, {strokeDashoffset: 0}],
    {duration: 900, delay: 60 + (+p.style.getPropertyValue("--i") || 0) * 45, easing: OUT, fill: "backwards"}).finished));
  applySlope(host);
}
function applySlope(host) {
  const cfg = host._sl, id = cfg.pinned || cfg.hover;
  const svg = host.querySelector("svg");
  if (!svg) return;
  svg.classList.toggle("iso", !!id);
  svg.querySelectorAll(".sl-it").forEach(g => { g.classList.toggle("on", g.dataset.id === id); g.classList.toggle("pin", g.dataset.id === cfg.pinned); });
  const on = id && svg.querySelector(`.sl-it[data-id="${CSS.escape(id)}"]`);
  if (on) on.parentNode.appendChild(on);  // draw the highlighted line on top
  const insp = host.querySelector(".sl-insp"), it = cfg.items.find(x => x.id === id);
  if (insp) insp.innerHTML = it ? cfg.inspect(it, it.id === cfg.pinned) : `<span class="t3">${esc(cfg.hint || "")}</span>`;
}
function bindSlope(host) {
  host._bound = true;
  host.tabIndex = 0;
  host.setAttribute("role", "group");
  const set = (k, v) => { const cfg = host._sl; if (cfg[k] === v) return; cfg[k] = v; if (k === "pinned") cfg.onPin?.(v); applySlope(host); };
  const nearest = e => {
    const g = host._geo, svg = host.querySelector("svg");
    if (!g || !svg) return null;
    const lab = e.target.closest?.(".sl-it");
    if (lab && e.target.classList.contains("sl-lab")) return lab.dataset.id;
    const r = svg.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
    if (px < g.xL - 24 || px > g.xR + 24) return null;
    const t = clamp((px - g.xL) / (g.xR - g.xL), 0, 1);
    let best = null, bd = 14;
    for (const it of host._sl.items) { const d = Math.abs(g.y(it.left) + (g.y(it.right) - g.y(it.left)) * t - py); if (d < bd) { bd = d; best = it.id; } }
    return best;
  };
  host.addEventListener("pointermove", e => set("hover", nearest(e)));
  host.addEventListener("pointerleave", () => set("hover", null));
  host.addEventListener("click", e => {
    if (e.target.closest(".sl-insp")) return;
    const id = nearest(e);
    set("pinned", id && id !== host._sl.pinned ? id : null);
  });
  host.addEventListener("keydown", e => {
    const cfg = host._sl, order = [...cfg.items].sort((a, b) => b.right - a.right).map(x => x.id);
    if (!order.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const i = order.indexOf(cfg.hover ?? cfg.pinned);
      set("hover", order[clamp(i < 0 ? 0 : i + (e.key === "ArrowDown" ? 1 : -1), 0, order.length - 1)]);
    } else if (e.key === "Enter" || e.key === " ") { if (e.target !== host) return; e.preventDefault(); set("pinned", cfg.hover && cfg.hover !== cfg.pinned ? cfg.hover : null); }
    else if (e.key === "Escape" && cfg.pinned) { e.stopPropagation(); set("pinned", null); }
  });
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

window.Kit = Object.freeze({still, SPRING, skel, paint, skeleton, reveal, swap, morph, hydrate, rings, gauge, bindRadials, slope, transition, copyText, flash, csv, download});
})();
