/* Experiment data in the app: tables with charts (line, scatter, bar, histogram, heatmap,
   volcano, enrichment), protein and small-molecule structures in 2D and 3D, networks and
   pathways in 2D and 3D, and each experiment's workflow.

   Every byte shown here was written by an experiment, so it is treated as untrusted: text is
   escaped, molecule drawings go through <img> data URLs (no inline SVG from a library), and
   structure files are only ever parsed, never executed. 3Dmol.js and OpenChemLib are vendored
   (same origin) and loaded on first use. Viewers live in persistent elements, so the app's
   string re-renders (live polling) never tear down a WebGL context or reset a layout. */
"use strict";
(() => {
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const sig = v => { if (v == null || !Number.isFinite(v)) return "–"; const a = Math.abs(v); return a !== 0 && (a < 1e-3 || a >= 1e6) ? v.toExponential(2) : String(+v.toPrecision(4)); };
const bytes = n => n == null ? "" : n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(n < 10240 ? 1 : 0) + " KB" : (n / 1048576).toFixed(1) + " MB";
const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const still = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const ico = (d, w = 14) => `<svg width="${w}" height="${w}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

/* ---------- file kinds ---------- */
const ext = n => (String(n || "").toLowerCase().match(/\.([a-z0-9]+)$/) || [])[1] || "";
const KIND = {
  figure: { l: "Figure", c: "--purple", d: '<rect x="2.5" y="2.5" width="11" height="11" rx="2"/><path d="m4.5 10.5 2.5-3 2 2 2.5-3.5"/>' },
  table: { l: "Table", c: "--blue", d: '<rect x="2.5" y="3" width="11" height="10" rx="1.5"/><path d="M2.5 6.5h11M2.5 9.5h11M6.5 6.5v6.5"/>' },
  protein: { l: "Protein structure", c: "--green", d: '<path d="M3 11c2-6 3 2 5-3s3 3 5-2"/><path d="M3 5.5c2 2 3-1 5 1"/>' },
  molecule: { l: "Molecule", c: "--orange", d: '<path d="m8 2.5 4.5 2.6v5.3L8 13l-4.5-2.6V5.1z"/><path d="M8 5.5v5"/>' },
  network: { l: "Network", c: "--indigo", d: '<circle cx="4" cy="4.5" r="1.6"/><circle cx="12" cy="5" r="1.6"/><circle cx="7.5" cy="12" r="1.6"/><path d="M5.5 5 10.4 5M5 6l1.9 4.5M11.3 6.4 8.6 10.6"/>' },
  pdf: { l: "PDF", c: "--red", d: '<path d="M4 2.5h5l3 3v8H4z"/><path d="M9 2.5v3h3"/>' },
  text: { l: "Text", c: "--gray", d: '<path d="M4 2.5h5l3 3v8H4z"/><path d="M6 8h4M6 10.5h4"/>' },
};
function kindOf(f) {
  if (f.artifact_type === "plot_png") return "figure";
  const e = ext(f.file_name);
  if (e === "csv" || e === "tsv") return "table";
  if (e === "pdb" || e === "cif" || e === "mmcif") return "protein";
  if (e === "sdf" || e === "mol" || e === "mol2" || e === "xyz") return "molecule";
  if (e === "sif" || e === "graphml") return "network";
  if (e === "pdf") return "pdf";
  if (e === "json") return JSON_KIND.get(f.id) || "table";   // refined once parsed: table | network | text
  return "text";
}
const JSON_KIND = new Map();   // file id -> what its JSON turned out to hold
const kindIcon = k => `<span class="dv-ki" style="color:var(${KIND[k]?.c || "--gray"})">${ico(KIND[k]?.d || KIND.text.d)}</span>`;
const FILTERS = [["all", "All"], ["figure", "Figures"], ["table", "Tables"], ["structure", "Structures"], ["network", "Networks"], ["other", "Other"]];
const inFilter = (k, f) => f === "all" || k === f || (f === "structure" && (k === "protein" || k === "molecule")) || (f === "other" && (k === "pdf" || k === "text"));

/* ---------- fetching (immutable by checksum, so cached for the session) ---------- */
const CACHE = new Map();
function fetchFile(f, as = "text") {
  const key = f.id + ":" + as;
  if (!CACHE.has(key)) {
    const p = fetch("/api/evidence/" + encodeURIComponent(f.id)).then(async r => {
      if (!r.ok) { let m = `Could not load the file (${r.status})`; try { m = (await r.json()).error || m; } catch {} throw new Error(m); }
      return as === "blob" ? r.blob() : r.text();
    });
    p.catch(() => CACHE.delete(key));
    if (CACHE.size > 80) CACHE.delete(CACHE.keys().next().value);
    CACHE.set(key, p);
  }
  return CACHE.get(key);
}

/* ---------- tables ---------- */
const MISSING = new Set(["", "na", "nan", "null", "none", "-", "n/a", "inf?"]);
function parseDelimited(text, delim) {
  const rows = []; let row = [], cell = "", q = false, i = 0;
  const n = text.length;
  for (; i < n; i++) {
    const ch = text[i];
    if (q) { if (ch === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += ch; continue; }
    if (ch === '"' && cell === "") { q = true; continue; }
    if (ch === delim) { row.push(cell); cell = ""; continue; }
    if (ch === "\n" || ch === "\r") { if (ch === "\r" && text[i + 1] === "\n") i++; row.push(cell); cell = ""; rows.push(row); row = []; if (rows.length > 200000) break; continue; }
    cell += ch;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows.filter(r => r.length > 1 || r[0] !== "");
}
function toNum(s) {
  if (typeof s === "number") return Number.isFinite(s) ? s : null;
  if (s == null) return null;
  const t = String(s).trim(); if (MISSING.has(t.toLowerCase())) return null;
  const v = Number(t); return Number.isFinite(v) ? v : null;
}
/* {cols:[{name, num, vals}], n} with columns typed: numeric when ≥90% of present values parse. */
function makeTable(header, body) {
  const cols = header.map((h, j) => {
    const raw = body.map(r => r[j] ?? "");
    let present = 0, ok = 0;
    for (const v of raw) { const t = String(v).trim(); if (MISSING.has(t.toLowerCase())) continue; present++; if (toNum(v) != null) ok++; }
    const num = present > 0 && ok / present >= 0.9;
    return { name: String(h || `column ${j + 1}`), num, vals: num ? raw.map(toNum) : raw.map(v => v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v)) };
  });
  return { cols, n: body.length };
}
function tableFromText(text, name) {
  const e = ext(name);
  if (e === "json") {
    const j = JSON.parse(text);
    let recs = Array.isArray(j) ? j : Array.isArray(j?.data) && Array.isArray(j?.columns) ? j.data.map(r => Object.fromEntries(j.columns.map((c, i) => [c, r[i]]))) : null;
    if (!recs && j && typeof j === "object") {   // a flat object of values: key/value table
      const flat = Object.entries(j).filter(([, v]) => v == null || typeof v !== "object");
      if (flat.length) recs = flat.map(([k, v]) => ({ key: k, value: v }));
    }
    if (!recs || !recs.length || typeof recs[0] !== "object" || Array.isArray(recs[0])) return null;
    const header = [...new Set(recs.slice(0, 500).flatMap(r => Object.keys(r || {})))].slice(0, 200);
    return makeTable(header, recs.map(r => header.map(h => r?.[h])));
  }
  const delim = e === "tsv" ? "\t" : e === "csv" ? "," : (text.split("\n", 1)[0].includes("\t") ? "\t" : ",");
  const rows = parseDelimited(text.replace(/^﻿/, ""), delim);
  if (!rows.length) return null;
  const width = Math.max(...rows.slice(0, 50).map(r => r.length));
  const header = rows[0].length === width ? rows[0] : Array.from({ length: width }, (_, i) => rows[0][i] ?? `column ${i + 1}`);
  return makeTable(header.slice(0, 200), rows.slice(1).map(r => r.slice(0, 200)));
}
const norm = s => String(s).toLowerCase().replace(/[^a-z0-9]/g, "");
function findCol(t, tests, num) {
  for (const test of tests) for (const c of t.cols) { if (num != null && c.num !== num) continue; if (typeof test === "string" ? norm(c.name) === test : test.test(norm(c.name))) return c; }
  return null;
}
/* Semantic columns: the shapes of differential-abundance and enrichment results. */
function roles(t) {
  const fc = findCol(t, ["log2fc", "logfc", "log2foldchange", "log2ratio", "lfc", /^log2fc/, /log2fold/, /^log2.*(ratio|fc|change)/, /(^|_)lfc$/], true);
  const padj = findCol(t, ["padj", "padjust", "adjpval", "adjpvalue", "fdr", "qvalue", "qval", "bh", /adj.*p/, /^p.*adj/, /fdr/], true);
  const p = findCol(t, ["pvalue", "pval", "p", "pvalues", /^p.?val/], true) || padj;
  const term = findCol(t, ["description", "term", "termname", "pathway", "pathwayname", "name"], false);
  const count = findCol(t, ["count", "overlap", "genecount", "size", "setsize"], true);
  const genes = findCol(t, ["geneid", "genes", "core_enrichment", "coreenrichment", "leadingedge", "overlapgenes", /genes$/], false);
  const label = findCol(t, ["gene", "symbol", "genename", "genesymbol", "protein", "proteinid", "name", "id", /gene/, /protein/], false) || t.cols.find(c => !c.num) || null;
  const src = findCol(t, ["source", "from", "node1", "gene1", "protein1", "interactora", "a"], false);
  const tgt = findCol(t, ["target", "to", "node2", "gene2", "protein2", "interactorb", "b"], false);
  const smiles = findCol(t, ["smiles", "canonicalsmiles", "isomericsmiles", /smiles$/], false);
  return { fc, p, padj, term, count, genes, label, src, tgt, smiles };
}
function chartTypes(t, r) {
  const nums = t.cols.filter(c => c.num), out = [];
  if (r.fc && r.p) out.push(["volcano", "Volcano"]);
  if (r.term && (r.padj || r.p)) out.push(["enrichment", "Enrichment"]);
  if (nums.length >= 2) out.push(["scatter", "Scatter"], ["line", "Line"]);
  if (nums.length >= 1 && t.cols.some(c => !c.num)) out.push(["bar", "Bar"]);
  if (nums.length >= 1) out.push(["histogram", "Histogram"]);
  if (nums.length >= 3 && t.n >= 2 && t.n <= 400) out.push(["heatmap", "Heatmap"]);
  return out;
}

/* ---------- SVG charts ---------- */
function niceStep(span, n) { const raw = span / Math.max(1, n), p = 10 ** Math.floor(Math.log10(raw)), f = raw / p; return (f >= 7.5 ? 10 : f >= 3.5 ? 5 : f >= 1.5 ? 2 : 1) * p; }
function ticks(lo, hi, n) {
  if (!(hi > lo)) { const d = Math.abs(lo) * 0.1 || 1; lo -= d; hi += d; }
  // the domain snaps out to whole steps, so the axis always starts and ends on a labelled tick
  const s = niceStep(hi - lo, n), a = Math.floor(lo / s + 1e-9) * s, b = Math.ceil(hi / s - 1e-9) * s, out = [];
  for (let v = a; v <= b + s * 1e-9 && out.length < 60; v += s) out.push(+v.toPrecision(12));
  return { lo: a, hi: b, ticks: out, step: s };
}
function extent(vals) { let lo = Infinity, hi = -Infinity; for (const v of vals) if (v != null && Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } return lo === Infinity ? [0, 1] : [lo, hi]; }
const tickFmt = step => v => { const a = Math.abs(v); if (a !== 0 && (a >= 1e5 || a < 1e-3)) return v.toExponential(1); const d = Math.max(0, Math.min(6, -Math.floor(Math.log10(step) + 1e-9))); return v.toFixed(d); };
const SERIES = ["--accent", "--orange", "--green", "--purple", "--red", "--yellow", "--indigo", "--blue"];
const DIV = { neg: [78, 167, 252], mid: [123, 127, 135], pos: [235, 87, 87] };
function diverge(v, m) { if (v == null || !Number.isFinite(v)) return "var(--text-3)"; const t = clamp(v / (m || 1), -1, 1), a = DIV.mid, b = t < 0 ? DIV.neg : DIV.pos, k = Math.abs(t); return `rgb(${a.map((x, i) => Math.round(x + (b[i] - x) * k)).join(",")})`; }
const SEQ = [[23, 23, 23], [18, 60, 110], [0, 147, 255], [140, 210, 255]];
function seqColor(t) { t = clamp(t, 0, 1) * (SEQ.length - 1); const i = Math.min(SEQ.length - 2, Math.floor(t)), k = t - i; return `rgb(${SEQ[i].map((x, j) => Math.round(x + (SEQ[i + 1][j] - x) * k)).join(",")})`; }

/* Axes frame shared by the xy charts. Returns the svg prefix, scale functions and plot box. */
function frame(W, H, xs, ys, o = {}) {
  const L = o.left ?? 56, R = 16, T = 12, B = o.bottom ?? 40, pw = Math.max(40, W - L - R), ph = Math.max(40, H - T - B);
  const xt = o.xcat ? null : ticks(xs[0], xs[1], Math.max(2, Math.round(pw / 90))), yt = ticks(ys[0], ys[1], Math.max(2, Math.round(ph / 48)));
  const x0 = xt ? Math.min(xt.lo, xs[0]) : 0, x1 = xt ? Math.max(xt.hi, xs[1]) : 1, y0 = Math.min(yt.lo, ys[0]), y1 = Math.max(yt.hi, ys[1]);
  const sx = v => L + (v - x0) / (x1 - x0 || 1) * pw, sy = v => T + ph - (v - y0) / (y1 - y0 || 1) * ph;
  const fy = tickFmt(yt.step);
  let g = `<g class="dv-grid">${yt.ticks.map(v => `<line x1="${L}" x2="${L + pw}" y1="${sy(v).toFixed(1)}" y2="${sy(v).toFixed(1)}"/>`).join("")}</g>`;
  g += `<g class="dv-ax">${yt.ticks.map(v => `<text x="${L - 8}" y="${(sy(v) + 3.5).toFixed(1)}" text-anchor="end">${esc(fy(v))}</text>`).join("")}`;
  if (xt) { const fx = tickFmt(xt.step); g += xt.ticks.map(v => `<line class="tk" x1="${sx(v).toFixed(1)}" x2="${sx(v).toFixed(1)}" y1="${T + ph}" y2="${T + ph + 4}"/><text x="${sx(v).toFixed(1)}" y="${T + ph + 16}" text-anchor="middle">${esc(fx(v))}</text>`).join(""); }
  g += `<line class="base" x1="${L}" x2="${L + pw}" y1="${T + ph}" y2="${T + ph}"/></g>`;
  if (o.xl) g += `<text class="dv-al" x="${L + pw / 2}" y="${H - 6}" text-anchor="middle">${esc(o.xl)}</text>`;
  if (o.yl) g += `<text class="dv-al" transform="translate(13 ${T + ph / 2}) rotate(-90)" text-anchor="middle">${esc(o.yl)}</text>`;
  return { g, sx, sy, L, T, pw, ph };
}
const svgOpen = (W, H, label) => `<svg class="dv-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">`;
const MAXPTS = 20000;
function sampleIdx(n) { if (n <= MAXPTS) return null; const s = n / MAXPTS, out = []; for (let i = 0; i < MAXPTS; i++) out.push(Math.floor(i * s)); return out; }

/* Each chart returns {svg, pts:[{x,y,html}]} — pts drive the hover tooltip. */
function chartXY(t, cfg, W, H) {
  const xc = t.cols[cfg.x], ycs = cfg.ys.map(i => t.cols[i]).filter(Boolean);
  if (!xc || !ycs.length) return { svg: "", pts: [] };
  const idx = sampleIdx(t.n) || [...Array(t.n).keys()];
  const xs = extent(idx.map(i => xc.vals[i])), ys = extent(ycs.flatMap(c => idx.map(i => c.vals[i])));
  const f = frame(W, H, xs, ys, { xl: xc.name, yl: ycs.length === 1 ? ycs[0].name : "" });
  let body = "", pts = [];
  ycs.forEach((c, si) => {
    const col = `var(${SERIES[si % SERIES.length]})`;
    let p = idx.filter(i => xc.vals[i] != null && c.vals[i] != null).map(i => [xc.vals[i], c.vals[i], i]);
    if (cfg.type === "line") {
      p.sort((a, b) => a[0] - b[0]);
      body += `<path class="dv-line" d="${p.map(([x, y], k) => (k ? "L" : "M") + f.sx(x).toFixed(1) + " " + f.sy(y).toFixed(1)).join("")}" style="stroke:${col}"/>`;
      if (p.length <= 60) body += p.map(([x, y]) => `<circle cx="${f.sx(x).toFixed(1)}" cy="${f.sy(y).toFixed(1)}" r="2.2" style="fill:${col}"/>`).join("");
    } else {
      const r = p.length > 3000 ? 1.6 : p.length > 500 ? 2.2 : 3;
      body += `<g style="fill:${col}" fill-opacity="${p.length > 3000 ? .45 : .75}">${p.map(([x, y]) => `<circle cx="${f.sx(x).toFixed(1)}" cy="${f.sy(y).toFixed(1)}" r="${r}"/>`).join("")}</g>`;
    }
    const lab = cfg.label != null ? t.cols[cfg.label] : null;
    pts.push(...p.map(([x, y, i]) => ({ x: f.sx(x), y: f.sy(y), html: `${lab ? `<b>${esc(lab.vals[i])}</b><br>` : ""}${esc(xc.name)} ${esc(sig(x))}<br>${esc(c.name)} ${esc(sig(y))}` })));
  });
  const legend = ycs.length > 1 ? `<div class="dv-legend">${ycs.map((c, i) => `<span><i style="background:var(${SERIES[i % SERIES.length]})"></i>${esc(c.name)}</span>`).join("")}</div>` : "";
  return { svg: legend + svgOpen(W, H, `${cfg.type} chart of ${ycs.map(c => c.name).join(", ")} against ${xc.name}`) + f.g + body + "</svg>", pts };
}
/* Horizontal bars: value axis along x, one labelled row per category. */
function hframe(W, n, labels, lo, hi, xl) {
  const lw = Math.min(300, Math.max(60, ...labels.map(l => Math.min(46, l.length) * 6.2))), L = lw + 14, R = 40, T = 6, rh = 22, ph = n * rh, H = T + ph + 40, pw = Math.max(60, W - L - R);
  const xt = ticks(Math.min(0, lo), Math.max(0, hi), Math.max(2, Math.round(pw / 90))), x0 = xt.lo, x1 = xt.hi, fx = tickFmt(xt.step);
  const sx = v => L + (v - x0) / (x1 - x0 || 1) * pw, row = k => T + k * rh + 3, bh = rh - 6;
  let g = `<g class="dv-grid">${xt.ticks.map(v => `<line x1="${sx(v).toFixed(1)}" x2="${sx(v).toFixed(1)}" y1="${T}" y2="${T + ph}"/>`).join("")}</g><g class="dv-ax">` +
    xt.ticks.map(v => `<text x="${sx(v).toFixed(1)}" y="${T + ph + 16}" text-anchor="middle">${esc(fx(v))}</text>`).join("") + `<line class="base" x1="${sx(0).toFixed(1)}" x2="${sx(0).toFixed(1)}" y1="${T}" y2="${T + ph}"/></g>` +
    labels.map((l, k) => `<text class="dv-cat" x="${L - 8}" y="${(row(k) + bh / 2 + 4).toFixed(1)}" text-anchor="end">${esc(l.length > 46 ? l.slice(0, 45) + "…" : l)}</text>`).join("");
  if (xl) g += `<text class="dv-al" x="${L + pw / 2}" y="${H - 6}" text-anchor="middle">${esc(xl)}</text>`;
  return { g, sx, row, bh, H };
}
function chartBar(t, cfg, W) {
  const cat = t.cols[cfg.x], yc = t.cols[cfg.ys[0]];
  if (!cat || !yc) return { svg: "", pts: [] };
  let rows = [...Array(t.n).keys()].filter(i => yc.vals[i] != null).map(i => [String(cat.vals[i]), yc.vals[i]]);
  const capped = rows.length > 40; if (capped) rows = rows.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 40);
  const [lo, hi] = extent(rows.map(r => r[1])), f = hframe(W, rows.length, rows.map(r => r[0]), lo, hi, yc.name);
  const body = rows.map(([, v], i) => { const a = f.sx(0), b = f.sx(v);
    return `<rect x="${Math.min(a, b).toFixed(1)}" y="${f.row(i).toFixed(1)}" width="${Math.max(1, Math.abs(b - a)).toFixed(1)}" height="${f.bh}" rx="2" style="fill:var(${v < 0 ? "--orange" : "--accent"})"/>`; }).join("");
  const pts = rows.map(([k, v], i) => ({ x: f.sx(v), y: f.row(i) + f.bh / 2, html: `<b>${esc(k)}</b><br>${esc(yc.name)} ${esc(sig(v))}` }));
  return { svg: (capped ? `<p class="dv-note">Showing the 40 largest of ${t.n} rows by |${esc(yc.name)}|.</p>` : "") + svgOpen(W, f.H, `Bar chart of ${yc.name} by ${cat.name}`) + f.g + body + "</svg>", pts };
}
function chartHist(t, cfg, W, H) {
  const c = t.cols[cfg.ys[0] ?? cfg.x]; if (!c) return { svg: "", pts: [] };
  const v = c.vals.filter(x => x != null); if (!v.length) return { svg: "", pts: [] };
  const [lo, hi] = extent(v), n = v.length, q = [...v].sort((a, b) => a - b), iqr = q[Math.floor(n * .75)] - q[Math.floor(n * .25)];
  const fd = iqr > 0 ? 2 * iqr / Math.cbrt(n) : 0, k = clamp(fd > 0 ? Math.ceil((hi - lo) / fd) : Math.ceil(Math.log2(n) + 1), 1, 60), w = (hi - lo) / k || 1;
  const bins = Array(k).fill(0); for (const x of v) bins[Math.min(k - 1, Math.floor((x - lo) / w))]++;
  const f = frame(W, H, [lo, lo + w * k], [0, Math.max(...bins)], { xl: c.name, yl: "Count" });
  const body = bins.map((b, i) => `<rect x="${(f.sx(lo + i * w) + .5).toFixed(1)}" y="${f.sy(b).toFixed(1)}" width="${Math.max(1, f.sx(lo + (i + 1) * w) - f.sx(lo + i * w) - 1).toFixed(1)}" height="${(f.sy(0) - f.sy(b)).toFixed(1)}" style="fill:var(--accent)" fill-opacity=".8"/>`).join("");
  const pts = bins.map((b, i) => ({ x: f.sx(lo + (i + .5) * w), y: f.sy(b), html: `${esc(sig(lo + i * w))} to ${esc(sig(lo + (i + 1) * w))}<br>${b} rows` }));
  return { svg: svgOpen(W, H, `Histogram of ${c.name}`) + f.g + body + "</svg>", pts };
}
function chartVolcano(t, r, cfg, W, H) {
  const fc = r.fc, p = r.p, sigc = r.padj || r.p, lab = r.label, fcT = cfg.fcT ?? 1, pT = cfg.pT ?? 0.05;
  const rows = [...Array(t.n).keys()].filter(i => fc.vals[i] != null && p.vals[i] != null && p.vals[i] > 0);
  const yv = i => -Math.log10(p.vals[i]);
  const f = frame(W, H, extent(rows.map(i => fc.vals[i])), [0, Math.max(1, ...rows.map(yv))], { xl: fc.name, yl: `−log10 ${p.name}` });
  const cls = i => sigc.vals[i] != null && sigc.vals[i] < pT && Math.abs(fc.vals[i]) > fcT ? (fc.vals[i] > 0 ? "up" : "down") : "ns";
  const groups = { ns: [], down: [], up: [] }; rows.forEach(i => groups[cls(i)].push(i));
  const col = { ns: "var(--text-3)", down: "var(--blue)", up: "var(--red)" };
  let body = Object.entries(groups).map(([g, l]) => `<g style="fill:${col[g]}" fill-opacity="${g === "ns" ? .45 : .9}">${l.map(i => `<circle cx="${f.sx(fc.vals[i]).toFixed(1)}" cy="${f.sy(yv(i)).toFixed(1)}" r="${g === "ns" ? 1.8 : 3}"/>`).join("")}</g>`).join("");
  // thresholds: ±|log2FC| and the significance line (drawn at the largest raw p that passes, or pT when p is the adjusted column)
  const passP = rows.filter(i => sigc.vals[i] != null && sigc.vals[i] < pT).map(i => p.vals[i]);
  const yLine = passP.length ? -Math.log10(Math.max(...passP)) : -Math.log10(pT);
  body += `<g class="dv-thr"><line x1="${f.sx(-fcT)}" x2="${f.sx(-fcT)}" y1="${f.T}" y2="${f.T + f.ph}"/><line x1="${f.sx(fcT)}" x2="${f.sx(fcT)}" y1="${f.T}" y2="${f.T + f.ph}"/><line x1="${f.L}" x2="${f.L + f.pw}" y1="${f.sy(yLine)}" y2="${f.sy(yLine)}"/></g>`;
  const top = [...groups.up, ...groups.down].sort((a, b) => p.vals[a] - p.vals[b]).slice(0, 12);
  // labels sit right of their point, or left of it near the right edge so they never clip
  if (lab) body += top.map(i => { const x = f.sx(fc.vals[i]), right = x > f.L + f.pw - 70;
    return `<text class="dv-lab" x="${(x + (right ? -5 : 5)).toFixed(1)}" y="${(f.sy(yv(i)) - 4).toFixed(1)}"${right ? ' text-anchor="end"' : ""}>${esc(String(lab.vals[i]).slice(0, 18))}</text>`; }).join("");
  const pts = rows.map(i => ({ x: f.sx(fc.vals[i]), y: f.sy(yv(i)), html: `${lab ? `<b>${esc(lab.vals[i])}</b><br>` : ""}${esc(fc.name)} ${esc(sig(fc.vals[i]))}<br>${esc(p.name)} ${esc(sig(p.vals[i]))}${sigc !== p ? `<br>${esc(sigc.name)} ${esc(sig(sigc.vals[i]))}` : ""}` }));
  const legend = `<div class="dv-legend"><span><i style="background:var(--red)"></i>Up ${groups.up.length}</span><span><i style="background:var(--blue)"></i>Down ${groups.down.length}</span><span><i style="background:var(--text-3)"></i>Not significant ${groups.ns.length}</span><span class="t3">${esc(sigc.name)} &lt; ${pT}, |${esc(fc.name)}| &gt; ${fcT}</span></div>`;
  return { svg: legend + svgOpen(W, H, `Volcano plot: ${groups.up.length} up, ${groups.down.length} down of ${rows.length}`) + f.g + body + "</svg>", pts };
}
function chartEnrich(t, r, W) {
  const pc = r.padj || r.p, term = r.term, cnt = r.count;
  const rows = [...Array(t.n).keys()].filter(i => pc.vals[i] != null && pc.vals[i] > 0).sort((a, b) => pc.vals[a] - pc.vals[b]).slice(0, 20);
  const xv = i => -Math.log10(pc.vals[i]), cmax = cnt ? Math.max(...rows.map(i => cnt.vals[i] || 0)) : 0;
  const f = hframe(W, rows.length, rows.map(i => String(term.vals[i])), 0, Math.max(...rows.map(xv)), `−log10 ${pc.name}`);
  const body = rows.map((i, k) => `<rect x="${f.sx(0).toFixed(1)}" y="${f.row(k).toFixed(1)}" width="${Math.max(1, f.sx(xv(i)) - f.sx(0)).toFixed(1)}" height="${f.bh}" rx="2" style="fill:${cnt ? seqColor(.35 + .65 * (cnt.vals[i] || 0) / (cmax || 1)) : "var(--accent)"}"/>` +
    (cnt ? `<text class="dv-val" x="${(f.sx(xv(i)) + 5).toFixed(1)}" y="${(f.row(k) + f.bh / 2 + 4).toFixed(1)}">${esc(cnt.vals[i])}</text>` : "")).join("");
  const pts = rows.map((i, k) => ({ x: f.sx(xv(i)), y: f.row(k) + f.bh / 2, html: `<b>${esc(term.vals[i])}</b><br>${esc(pc.name)} ${esc(sig(pc.vals[i]))}${cnt ? `<br>${esc(cnt.name)} ${esc(cnt.vals[i])}` : ""}` }));
  const legend = `<div class="dv-legend"><span class="t3">Top ${rows.length} terms by ${esc(pc.name)}${cnt ? `; shade and label show ${esc(cnt.name)}` : ""}</span></div>`;
  return { svg: legend + svgOpen(W, f.H, `Enrichment: top ${rows.length} terms`) + f.g + body + "</svg>", pts };
}
function chartHeat(t, cfg, W, H) {
  const lab = t.cols.find(c => !c.num), nums = t.cols.filter(c => c.num).slice(0, 60), n = Math.min(t.n, 400);
  const z = cfg.zscore;
  const M = [...Array(n).keys()].map(i => { const row = nums.map(c => c.vals[i]); if (!z) return row;
    const v = row.filter(x => x != null), m = v.reduce((a, b) => a + b, 0) / (v.length || 1), sd = Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(1, v.length - 1)) || 1;
    return row.map(x => x == null ? null : (x - m) / sd); });
  const all = M.flat().filter(x => x != null), [lo, hi] = extent(all), m = Math.max(Math.abs(lo), Math.abs(hi));
  const L = lab ? Math.min(180, Math.max(50, ...[...Array(n).keys()].map(i => String(lab.vals[i]).length * 6))) + 10 : 12, T = 90, cw = Math.max(6, Math.min(40, (W - L - 20) / nums.length)), ch = Math.max(3, Math.min(18, 540 / n));
  const h = T + ch * n + 20, w = L + cw * nums.length + 20;
  const color = v => v == null ? "var(--elev-2)" : z || lo < 0 ? diverge(v, m) : seqColor((v - lo) / (hi - lo || 1));
  let body = M.map((row, i) => row.map((v, j) => `<rect x="${(L + j * cw).toFixed(1)}" y="${(T + i * ch).toFixed(1)}" width="${(cw - .5).toFixed(1)}" height="${(ch - .5).toFixed(1)}" fill="${color(v)}"/>`).join("")).join("");
  body += nums.map((c, j) => `<text class="dv-cat" transform="translate(${(L + j * cw + cw / 2 + 3).toFixed(1)} ${T - 6}) rotate(-55)">${esc(c.name.length > 16 ? c.name.slice(0, 15) + "…" : c.name)}</text>`).join("");
  if (lab && ch >= 9) body += [...Array(n).keys()].map(i => `<text class="dv-cat" x="${L - 6}" y="${(T + i * ch + ch / 2 + 3.5).toFixed(1)}" text-anchor="end">${esc(String(lab.vals[i]).slice(0, 28))}</text>`).join("");
  const pts = []; M.forEach((row, i) => row.forEach((v, j) => pts.push({ x: L + j * cw + cw / 2, y: T + i * ch + ch / 2, html: `${lab ? `<b>${esc(lab.vals[i])}</b><br>` : ""}${esc(nums[j].name)} ${esc(sig(nums[j].vals[i]))}${z ? `<br>z ${esc(sig(v))}` : ""}` })));
  const legend = `<div class="dv-legend"><span class="t3">${n} rows × ${nums.length} numeric columns${t.n > n ? ` (first ${n} of ${t.n})` : ""}${z ? ", z-scored per row" : ""}</span></div>`;
  return { svg: legend + `<svg class="dv-svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="Heatmap">` + body + "</svg>", pts, h, w };
}
function drawChart(host, t, r, cfg) {
  const W = Math.max(280, Math.floor(host.clientWidth || 640)), H = clamp(Math.round(W * .5), 260, 420);
  const out = cfg.type === "volcano" ? chartVolcano(t, r, cfg, W, H) : cfg.type === "enrichment" ? chartEnrich(t, r, W) : cfg.type === "bar" ? chartBar(t, cfg, W)
    : cfg.type === "histogram" ? chartHist(t, cfg, W, H) : cfg.type === "heatmap" ? chartHeat(t, cfg, W, H) : chartXY(t, cfg, W, H);
  host.innerHTML = `<div class="dv-plot">${out.svg}<div class="dv-tip" hidden></div></div>`;
  const plot = host.firstChild, svg = plot.querySelector("svg.dv-svg"), tip = plot.querySelector(".dv-tip"), pts = out.pts;
  if (!svg || !pts.length) return;
  let raf = 0;
  svg.onmousemove = e => { if (raf) return; raf = requestAnimationFrame(() => { raf = 0;
    const b = svg.getBoundingClientRect(), sx = svg.viewBox.baseVal.width / b.width || 1, x = (e.clientX - b.left) * sx, y = (e.clientY - b.top) * sx;
    let best = null, bd = 18 * 18; for (const p of pts) { const d = (p.x - x) ** 2 + (p.y - y) ** 2; if (d < bd) { bd = d; best = p; } }
    if (!best) { tip.hidden = true; return; }
    tip.innerHTML = best.html; tip.hidden = false;
    const pb = plot.getBoundingClientRect(), px = e.clientX - pb.left, py = e.clientY - pb.top;
    tip.style.left = Math.min(px + 14, pb.width - tip.offsetWidth - 4) + "px"; tip.style.top = Math.max(0, py - tip.offsetHeight - 10) + "px"; }); };
  svg.onmouseleave = () => { tip.hidden = true; };
}

/* ---------- table grid ---------- */
function gridHtml(t, st) {
  const q = st.q.trim().toLowerCase();
  let idx = [...Array(t.n).keys()];
  if (q) idx = idx.filter(i => t.cols.some(c => String(c.vals[i] ?? "").toLowerCase().includes(q)));
  if (st.sort) { const c = t.cols[st.sort.k], d = st.sort.d; idx.sort((a, b) => { const x = c.vals[a], y = c.vals[b]; if (x == null || x === "") return 1; if (y == null || y === "") return -1; return (c.num ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true })) * d; }); }
  const size = 50, pages = Math.max(1, Math.ceil(idx.length / size)); st.page = clamp(st.page, 0, pages - 1);
  const page = idx.slice(st.page * size, st.page * size + size);
  const cell = (c, i) => { const v = c.vals[i]; if (c.num) return `<td class="num"><span class="mono">${v == null ? '<span class="t3">–</span>' : esc(sig(v))}</span></td>`;
    const s = String(v ?? ""); return `<td title="${esc(s.length > 60 ? s : "")}">${esc(s.length > 80 ? s.slice(0, 79) + "…" : s)}</td>`; };
  return `<div class="gwrap dv-gw" tabindex="0" aria-label="Data table"><table class="dg dense"><thead><tr>${t.cols.map((c, k) => `<th scope="col" class="${c.num ? "num" : ""}" aria-sort="${st.sort?.k === k ? (st.sort.d === 1 ? "ascending" : "descending") : "none"}"><button type="button" data-dsort="${k}">${esc(c.name)}<span class="sarr${st.sort?.k === k ? " on" : ""}" aria-hidden="true">${st.sort?.k === k && st.sort.d === -1 ? "↓" : "↑"}</span></button></th>`).join("")}</tr></thead>
    <tbody>${page.map(i => `<tr>${t.cols.map(c => cell(c, i)).join("")}</tr>`).join("") || `<tr><td colspan="${t.cols.length}" class="gempty">No rows match.</td></tr>`}</tbody></table></div>
    <div class="gfoot"><span>${idx.length ? `${st.page * size + 1}–${Math.min(idx.length, st.page * size + size)} of ${idx.length}` : "No rows"}${q ? ` (filtered from ${t.n})` : ""}</span><span class="pg"><button type="button" class="icon-btn" data-dpage="-1" aria-label="Previous page"${st.page <= 0 ? " disabled" : ""}>${ico('<path d="M10 3 5 8l5 5"/>')}</button><span>Page ${st.page + 1} of ${pages}</span><button type="button" class="icon-btn" data-dpage="1" aria-label="Next page"${st.page >= pages - 1 ? " disabled" : ""}>${ico('<path d="m6 3 5 5-5 5"/>')}</button></span></div>`;
}

/* ---------- networks ---------- */
const NET_MAX = 600;
function graphFrom(nodes, edges, name) {
  const byId = new Map();
  const add = (id, attrs = {}) => { id = String(id); if (!byId.has(id)) byId.set(id, { id, label: String(attrs.label ?? attrs.name ?? id), attrs: {} }); const n = byId.get(id); for (const [k, v] of Object.entries(attrs)) if (v != null && typeof v !== "object" && k !== "id") n.attrs[k] = v; return n; };
  nodes.forEach(n => add(n.id, n));
  const E = []; const seen = new Set();
  for (const e of edges) { if (e.source == null || e.target == null || String(e.source) === String(e.target)) continue; const s = add(e.source).id, t = add(e.target).id, k = String(e.interaction ?? e.type ?? e.label ?? "");
    const key = s + "\u0000" + t + "\u0000" + k; if (seen.has(key)) continue; seen.add(key); E.push({ s, t, k }); }
  let N = [...byId.values()];
  const deg = new Map(N.map(n => [n.id, 0])); E.forEach(e => { deg.set(e.s, deg.get(e.s) + 1); deg.set(e.t, deg.get(e.t) + 1); });
  let trimmed = 0;
  if (N.length > NET_MAX) { const keep = new Set([...N].sort((a, b) => deg.get(b.id) - deg.get(a.id)).slice(0, NET_MAX).map(n => n.id)); trimmed = N.length - NET_MAX; N = N.filter(n => keep.has(n.id)); }
  const ids = new Set(N.map(n => n.id)), EE = E.filter(e => ids.has(e.s) && ids.has(e.t)).slice(0, 6000);
  N.forEach(n => { n.deg = deg.get(n.id) || 0; });
  // colour: a numeric attribute that looks like a fold change, else a categorical "type"
  const numAttr = ["log2FC", "logFC", "log2FoldChange", "fc", "score", "value", "weight"].find(k => N.some(n => typeof n.attrs[k] === "number" || toNum(n.attrs[k]) != null && n.attrs[k] !== ""));
  const catAttr = ["type", "group", "kind", "class", "category"].find(k => N.some(n => n.attrs[k] != null));
  return { name, nodes: N, edges: EE, trimmed, numAttr, catAttr };
}
function parseNetwork(text, name, j) {
  const e = ext(name);
  if (e === "sif") {
    const edges = [], nodes = [];
    for (const line of text.split(/\r?\n/)) { const p = line.trim().split(/\t| +/).filter(Boolean); if (!p.length || line.startsWith("#")) continue;
      if (p.length === 1) nodes.push({ id: p[0] }); else for (const t of p.slice(2)) edges.push({ source: p[0], interaction: p[1], target: t }); }
    return graphFrom(nodes, edges, name);
  }
  if (e === "graphml") {
    const doc = new DOMParser().parseFromString(text, "application/xml"); if (doc.querySelector("parsererror")) throw new Error("This GraphML file is not valid XML.");
    const keys = Object.fromEntries([...doc.getElementsByTagName("key")].map(k => [k.getAttribute("id"), k.getAttribute("attr.name") || k.getAttribute("id")]));
    const data = el => Object.fromEntries([...el.children].filter(c => c.localName === "data").map(d => { const v = d.textContent; return [keys[d.getAttribute("key")] || d.getAttribute("key"), toNum(v) ?? v]; }));
    return graphFrom([...doc.getElementsByTagName("node")].map(n => ({ id: n.getAttribute("id"), ...data(n) })), [...doc.getElementsByTagName("edge")].map(x => ({ source: x.getAttribute("source"), target: x.getAttribute("target"), ...data(x) })), name);
  }
  j = j ?? JSON.parse(text);
  if (Array.isArray(j?.elements) || Array.isArray(j?.elements?.nodes)) {   // Cytoscape.js
    const els = Array.isArray(j.elements) ? j.elements : [...(j.elements.nodes || []), ...(j.elements.edges || [])];
    return graphFrom(els.filter(x => x.data && x.data.source == null).map(x => x.data), els.filter(x => x.data && x.data.source != null).map(x => x.data), name);
  }
  return graphFrom(j.nodes || [], j.edges || j.links || [], name);
}
const isNetworkJson = j => j && typeof j === "object" && !Array.isArray(j) && (Array.isArray(j.edges) || Array.isArray(j.links) || Array.isArray(j.elements) || Array.isArray(j.elements?.edges)) && (Array.isArray(j.nodes) || j.elements);
function networkFromTable(t, r) {
  if (r.src && r.tgt) { const kind = findCol(t, ["interaction", "type", "relation", "edgetype"], false);
    return graphFrom([], [...Array(t.n).keys()].map(i => ({ source: r.src.vals[i], target: r.tgt.vals[i], interaction: kind ? kind.vals[i] : "" })), "table"); }
  if (r.term && r.genes) {   // enrichment: term–gene bipartite network (the cnetplot view)
    const pc = r.padj || r.p, rows = [...Array(t.n).keys()].filter(i => r.genes.vals[i]).sort((a, b) => (pc?.vals[a] ?? 1) - (pc?.vals[b] ?? 1)).slice(0, 8);
    const nodes = [], edges = [];
    rows.forEach(i => { const term = String(r.term.vals[i]); nodes.push({ id: "term:" + term, label: term, type: "term" });
      String(r.genes.vals[i]).split(/[\/,;| ]+/).filter(Boolean).slice(0, 60).forEach(g => { nodes.push({ id: g, type: "gene" }); edges.push({ source: "term:" + term, target: g, interaction: "member" }); }); });
    return graphFrom(nodes, edges, "enrichment");
  }
  return null;
}
/* Deterministic force layout (Fruchterman–Reingold with cooling) of n nodes joined by E (index pairs), centred at 0. */
function force(n, E, dim) {
  const P = new Float64Array(n * dim), D = new Float64Array(n * dim);
  let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < n * dim; i++) P[i] = rnd() * 2 - 1;
  // ideal edge length: the radius-1 ball (or disc) shared evenly between the nodes
  const k = dim === 3 ? Math.cbrt(8 / Math.max(1, n)) : Math.sqrt(4 / Math.max(1, n)), iters = n > 300 ? 160 : 260;
  let temp = .25;
  for (let it = 0; it < iters; it++) {
    D.fill(0);
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      let d2 = 0; const dv = []; for (let a = 0; a < dim; a++) { const v = P[i * dim + a] - P[j * dim + a]; dv.push(v); d2 += v * v; }
      d2 = Math.max(d2, 1e-6); const f = k * k / d2;
      for (let a = 0; a < dim; a++) { D[i * dim + a] += dv[a] * f; D[j * dim + a] -= dv[a] * f; }
    }
    for (const [i, j] of E) { let d2 = 0; const dv = []; for (let a = 0; a < dim; a++) { const v = P[i * dim + a] - P[j * dim + a]; dv.push(v); d2 += v * v; }
      const d = Math.sqrt(d2) || 1e-3, f = d / k; for (let a = 0; a < dim; a++) { D[i * dim + a] -= dv[a] * f; D[j * dim + a] += dv[a] * f; } }
    for (let i = 0; i < n; i++) { let m = 0; for (let a = 0; a < dim; a++) m += D[i * dim + a] ** 2; m = Math.sqrt(m) || 1; const s = Math.min(m, temp) / m;
      for (let a = 0; a < dim; a++) P[i * dim + a] = P[i * dim + a] + D[i * dim + a] * s - P[i * dim + a] * .01; }   // light gravity keeps components together
    temp *= .975;
  }
  const c = Array(dim).fill(0); for (let i = 0; i < n; i++) for (let a = 0; a < dim; a++) c[a] += P[i * dim + a] / n;
  for (let i = 0; i < n; i++) for (let a = 0; a < dim; a++) P[i * dim + a] -= c[a];
  return P;
}
/* Node positions in [-1, 1]. 3D: one layout normalised to the unit ball, so it orbits without changing size.
   2D: each connected component is laid out on its own and the components are packed in rows, largest first,
   so a pathway with many small islands does not squeeze its main component into the middle of the drawing. */
function layout(g, dim) {
  const n = g.nodes.length, idx = new Map(g.nodes.map((x, i) => [x.id, i])), E = g.edges.map(e => [idx.get(e.s), idx.get(e.t)]);
  if (dim === 3) { const P = force(n, E, 3); let r = 0; for (let i = 0; i < n; i++) r = Math.max(r, Math.hypot(P[i * 3], P[i * 3 + 1], P[i * 3 + 2]));
    for (let i = 0; i < n * 3; i++) P[i] /= r || 1; return P; }
  const up = [...Array(n).keys()], find = i => { while (up[i] !== i) i = up[i] = up[up[i]]; return i; };
  for (const [i, j] of E) up[find(i)] = find(j);
  const groups = new Map(); for (let i = 0; i < n; i++) { const r = find(i); if (!groups.has(r)) groups.set(r, []); groups.get(r).push(i); }
  const comps = [...groups.values()].sort((a, b) => b.length - a.length || a[0] - b[0]).map(ids => {
    const local = new Map(ids.map((v, i) => [v, i])), p = ids.length > 1 ? force(ids.length, E.filter(([i]) => local.has(i)).map(([i, j]) => [local.get(i), local.get(j)]), 2) : new Float64Array(2);
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity; for (let i = 0; i < ids.length; i++) { x0 = Math.min(x0, p[i * 2]); x1 = Math.max(x1, p[i * 2]); y0 = Math.min(y0, p[i * 2 + 1]); y1 = Math.max(y1, p[i * 2 + 1]); }
    // a component's box grows with the square root of its size, so every node gets about the same room
    const side = Math.sqrt(ids.length), sc = side / Math.max(x1 - x0, y1 - y0, 1e-9), w = ids.length > 1 ? (x1 - x0) * sc : 0, h = ids.length > 1 ? (y1 - y0) * sc : 0;
    return { ids, p, x0, y0, sc, w, h };
  });
  const gap = .9, area = comps.reduce((a, c) => a + (c.w + gap) * (c.h + gap), 0), rowW = Math.max(comps[0].w + gap, Math.sqrt(area * 1.6));
  const P = new Float64Array(n * 2); let x = 0, y = 0, rowH = 0;
  for (const c of comps) { if (x > 0 && x + c.w > rowW) { x = 0; y += rowH + gap; rowH = 0; }
    for (let i = 0; i < c.ids.length; i++) { const v = c.ids[i]; P[v * 2] = x + (c.ids.length > 1 ? (c.p[i * 2] - c.x0) * c.sc : 0); P[v * 2 + 1] = y + (c.ids.length > 1 ? (c.p[i * 2 + 1] - c.y0) * c.sc : 0); }
    x += c.w + gap; rowH = Math.max(rowH, c.h); }
  for (let a = 0; a < 2; a++) { let lo = Infinity, hi = -Infinity; for (let i = 0; i < n; i++) { lo = Math.min(lo, P[i * 2 + a]); hi = Math.max(hi, P[i * 2 + a]); }
    const span = hi - lo; for (let i = 0; i < n; i++) P[i * 2 + a] = span > 0 ? (P[i * 2 + a] - lo) / span * 2 - 1 : 0; }
  return P;
}
const EDGE_KIND = k => { k = String(k || "").toLowerCase();
  if (/inhibit|repress|suppress|dephosph|ubiquit|degrad/.test(k)) return "inh";
  if (/activat|express|induc|stimul|phosph|positive|catalys/.test(k)) return "act";
  if (/bind|assoc|complex|interact|member|ppi|pp\b/.test(k)) return "bind";
  return "other"; };
const EDGE_COLOR = { act: "--green", inh: "--red", bind: "--text-3", other: "--text-3" };
function nodeColor(g, n) {
  if (g.numAttr) { const m = Math.max(...g.nodes.map(x => Math.abs(toNum(x.attrs[g.numAttr]) ?? 0))) || 1; const v = toNum(n.attrs[g.numAttr]); return v == null ? cssv("--text-3") : diverge(v, m); }
  if (g.catAttr) { const cats = [...new Set(g.nodes.map(x => String(x.attrs[g.catAttr] ?? "")))]; return cssv(SERIES[cats.indexOf(String(n.attrs[g.catAttr] ?? "")) % SERIES.length]); }
  return cssv("--accent");
}
function netLegend(g) {
  const kinds = [...new Set(g.edges.map(e => EDGE_KIND(e.k)))], lab = { act: "activation / expression", inh: "inhibition", bind: "binding / membership", other: "other relation" };
  let s = kinds.map(k => `<span><svg width="18" height="6" aria-hidden="true"><path d="M0 3h18" style="stroke:var(${EDGE_COLOR[k]})" stroke-width="1.6"${k === "other" ? ' stroke-dasharray="3 2"' : ""}/></svg>${lab[k]}</span>`).join("");
  if (g.numAttr) { const m = Math.max(...g.nodes.map(x => Math.abs(toNum(x.attrs[g.numAttr]) ?? 0))) || 1; s += `<span class="dv-ramp"><b>${esc(sig(-m))}</b><i></i><b>${esc(sig(m))}</b> ${esc(g.numAttr)}</span>`; }
  else if (g.catAttr) { const cats = [...new Set(g.nodes.map(x => String(x.attrs[g.catAttr] ?? "")))].slice(0, 8); s += cats.map((c, i) => `<span><i class="dot" style="background:var(${SERIES[i % SERIES.length]})"></i>${esc(c || "(none)")}</span>`).join(""); }
  return `<div class="dv-legend">${s}<span class="t3">${g.nodes.length} nodes · ${g.edges.length} edges${g.trimmed ? ` · ${g.trimmed} lowest-degree nodes hidden` : ""}</span></div>`;
}
function nodeTip(g, n) { const a = Object.entries(n.attrs).filter(([k]) => !["label", "name"].includes(k)).slice(0, 6); return `<b>${esc(n.label)}</b><br>degree ${n.deg}${a.map(([k, v]) => `<br>${esc(k)} ${esc(typeof v === "number" ? sig(v) : String(v).slice(0, 60))}`).join("")}`; }

/* 2D: SVG with pan/zoom; hover highlights a node's neighbours. */
function network2D(host, g) {
  const P = g._p2 ||= layout(g, 2), W = Math.max(320, host.clientWidth || 640), H = clamp(Math.round(W * .62), 320, 560), pad = 40;
  const padR = 90, X = i => pad + (P[i * 2] + 1) / 2 * (W - pad - padR), Y = i => pad + (P[i * 2 + 1] + 1) / 2 * (H - pad * 2), idx = new Map(g.nodes.map((n, i) => [n.id, i]));
  const showLab = n => g.nodes.length <= 90 || n.deg >= [...g.nodes].map(x => x.deg).sort((a, b) => b - a)[Math.min(29, g.nodes.length - 1)];
  const rad = n => 3.5 + Math.min(6, Math.sqrt(n.deg) * 1.4);
  const edges = g.edges.map((e, k) => { const a = idx.get(e.s), b = idx.get(e.t), x1 = X(a), y1 = Y(a), x2 = X(b), y2 = Y(b), kind = EDGE_KIND(e.k), d = Math.hypot(x2 - x1, y2 - y1) || 1, r = rad(g.nodes[b]) + 2;
    const ex = x2 - (x2 - x1) / d * r, ey = y2 - (y2 - y1) / d * r;
    return `<line data-e="${k}" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${ex.toFixed(1)}" y2="${ey.toFixed(1)}" style="stroke:var(${EDGE_COLOR[kind]})"${kind === "act" ? ' marker-end="url(#dvA)"' : kind === "inh" ? ' marker-end="url(#dvT)"' : ""}${kind === "other" ? ' stroke-dasharray="3 2"' : ""}/>`; }).join("");
  const nodes = g.nodes.map((n, i) => `<g data-n="${i}" transform="translate(${X(i).toFixed(1)} ${Y(i).toFixed(1)})"><circle class="hit" r="${Math.max(rad(n) + 4, 9).toFixed(1)}"/><circle r="${rad(n).toFixed(1)}" fill="${nodeColor(g, n)}"/>${showLab(n) ? `<text x="${(rad(n) + 3).toFixed(1)}" y="3.5">${esc(n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label)}</text>` : ""}</g>`).join("");
  host.innerHTML = netLegend(g) + `<div class="dv-plot dv-net"><svg class="dv-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Network of ${g.nodes.length} nodes and ${g.edges.length} edges">
    <defs><marker id="dvA" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 8 4 0 8z" style="fill:var(--green)"/></marker><marker id="dvT" viewBox="0 0 4 10" refX="3" refY="5" markerWidth="4" markerHeight="10" orient="auto"><path d="M2 0v10" style="stroke:var(--red)" stroke-width="2"/></marker></defs>
    <g class="dv-zoom"><g class="dv-edges">${edges}</g><g class="dv-nodes">${nodes}</g></g></svg><div class="dv-tip" hidden></div><div class="dv-hint">Scroll to zoom · drag to pan</div></div>`;
  const svg = host.querySelector("svg.dv-svg"), zg = svg.querySelector(".dv-zoom"), tip = host.querySelector(".dv-tip"), plot = host.querySelector(".dv-plot");
  const adj = g.nodes.map(() => new Set()); g.edges.forEach((e, k) => { adj[idx.get(e.s)].add(k); adj[idx.get(e.t)].add(k); });
  let s = 1, tx = 0, ty = 0, drag = null; const apply = () => zg.setAttribute("transform", `translate(${tx} ${ty}) scale(${s})`);
  svg.addEventListener("wheel", e => { e.preventDefault(); const b = svg.getBoundingClientRect(), mx = (e.clientX - b.left) * W / b.width, my = (e.clientY - b.top) * H / b.height, f = Math.exp(-e.deltaY * .0015), ns = clamp(s * f, .4, 8);
    tx = mx - (mx - tx) * ns / s; ty = my - (my - ty) * ns / s; s = ns; apply(); }, { passive: false });
  svg.addEventListener("pointerdown", e => { drag = [e.clientX, e.clientY, tx, ty]; svg.setPointerCapture(e.pointerId); });
  svg.addEventListener("pointermove", e => { if (drag) { const b = svg.getBoundingClientRect(); tx = drag[2] + (e.clientX - drag[0]) * W / b.width; ty = drag[3] + (e.clientY - drag[1]) * H / b.height; apply(); } });
  svg.addEventListener("pointerup", () => { drag = null; });
  svg.addEventListener("mouseover", e => { const el = e.target.closest("[data-n]"); if (!el) return; const i = +el.dataset.n, n = g.nodes[i];
    svg.classList.add("dv-focus"); el.classList.add("on"); adj[i].forEach(k => { svg.querySelector(`[data-e="${k}"]`)?.classList.add("on"); const ed = g.edges[k]; svg.querySelector(`[data-n="${idx.get(ed.s === n.id ? ed.t : ed.s)}"]`)?.classList.add("nb"); });
    tip.innerHTML = nodeTip(g, n); tip.hidden = false; const pb = plot.getBoundingClientRect(), r = el.getBoundingClientRect();
    tip.style.left = Math.min(r.right - pb.left + 8, pb.width - tip.offsetWidth - 4) + "px"; tip.style.top = Math.max(0, r.top - pb.top - tip.offsetHeight - 4) + "px"; });
  svg.addEventListener("mouseout", e => { if (!e.target.closest("[data-n]")) return; svg.classList.remove("dv-focus"); svg.querySelectorAll(".on,.nb").forEach(x => x.classList.remove("on", "nb")); tip.hidden = true; });
}
/* 3D: perspective canvas with drag-to-orbit, wheel zoom, depth-sorted nodes and hover labels. */
function network3D(host, g) {
  const P = g._p3 ||= layout(g, 3), W = Math.max(320, host.clientWidth || 640), H = clamp(Math.round(W * .62), 320, 560), dpr = devicePixelRatio || 1;
  host.innerHTML = netLegend(g) + `<div class="dv-plot dv-net"><canvas width="${W * dpr}" height="${H * dpr}" style="width:${W}px;height:${H}px" role="img" aria-label="3D network of ${g.nodes.length} nodes"></canvas><div class="dv-tip" hidden></div><div class="dv-hint">Drag to rotate · scroll to zoom</div></div>`;
  const cv = host.querySelector("canvas"), ctx = cv.getContext("2d"), tip = host.querySelector(".dv-tip"), idx = new Map(g.nodes.map((n, i) => [n.id, i]));
  const st = { yaw: .6, pitch: -.35, zoom: 1, auto: !still(), hover: -1, raf: 0, drag: null, proj: [] };
  const colors = () => ({ n: g.nodes.map(n => nodeColor(g, n)), e: Object.fromEntries(Object.entries(EDGE_COLOR).map(([k, v]) => [k, cssv(v)])), t: cssv("--text"), t3: cssv("--text-3") });
  let col = colors();
  const draw = () => {
    const cy = Math.cos(st.yaw), sy = Math.sin(st.yaw), cp = Math.cos(st.pitch), sp = Math.sin(st.pitch), R = Math.min(W, H) * .42 * st.zoom, cam = 3.2;
    const pr = g.nodes.map((n, i) => { const x = P[i * 3], y = P[i * 3 + 1], z = P[i * 3 + 2], x1 = x * cy + z * sy, z1 = -x * sy + z * cy, y1 = y * cp - z1 * sp, z2 = y * sp + z1 * cp, f = cam / (cam - z2);
      return { x: W / 2 + x1 * R * f, y: H / 2 + y1 * R * f, z: z2, f, i }; });
    st.proj = pr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H); ctx.lineWidth = 1;
    const hov = st.hover, nb = new Set();
    if (hov >= 0) g.edges.forEach(e => { const a = idx.get(e.s), b = idx.get(e.t); if (a === hov) nb.add(b); if (b === hov) nb.add(a); });
    for (const e of g.edges) { const a = pr[idx.get(e.s)], b = pr[idx.get(e.t)], on = hov >= 0 && (a.i === hov || b.i === hov);
      ctx.globalAlpha = hov >= 0 ? (on ? .95 : .08) : clamp(.25 + (a.z + b.z + 2) * .18, .15, .8); ctx.strokeStyle = col.e[EDGE_KIND(e.k)];
      ctx.setLineDash(EDGE_KIND(e.k) === "other" ? [3, 2] : []); ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
    ctx.setLineDash([]);
    const order = [...pr].sort((a, b) => a.z - b.z);
    for (const p of order) { const n = g.nodes[p.i], r = (2.5 + Math.min(5, Math.sqrt(n.deg) * 1.2)) * p.f; ctx.globalAlpha = hov >= 0 && p.i !== hov && !nb.has(p.i) ? .18 : clamp(.55 + (p.z + 1) * .25, .45, 1);
      ctx.fillStyle = col.n[p.i]; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill(); }
    ctx.globalAlpha = 1; ctx.font = "11px Inter, system-ui, sans-serif"; ctx.fillStyle = col.t;
    const lab = hov >= 0 ? [hov, ...nb] : g.nodes.length <= 40 ? g.nodes.map((_, i) => i) : [...g.nodes.keys()].sort((a, b) => g.nodes[b].deg - g.nodes[a].deg).slice(0, 15);
    for (const i of lab) { const p = pr[i]; ctx.fillText(g.nodes[i].label.slice(0, 22), p.x + 7, p.y + 3.5); }
  };
  const loop = () => { st.raf = 0; if (!cv.isConnected) return; if (st.auto && !st.drag && st.hover < 0) { st.yaw += .0035; draw(); st.raf = requestAnimationFrame(loop); } };
  const kick = () => { if (!st.raf) st.raf = requestAnimationFrame(loop); };
  cv.addEventListener("pointerdown", e => { st.drag = [e.clientX, e.clientY, st.yaw, st.pitch]; st.auto = false; cv.setPointerCapture(e.pointerId); });
  cv.addEventListener("pointermove", e => {
    if (st.drag) { st.yaw = st.drag[2] + (e.clientX - st.drag[0]) * .01; st.pitch = clamp(st.drag[3] + (e.clientY - st.drag[1]) * .01, -1.5, 1.5); draw(); return; }
    const b = cv.getBoundingClientRect(), x = e.clientX - b.left, y = e.clientY - b.top; let best = -1, bd = 12 * 12;
    for (const p of st.proj) { const d = (p.x - x) ** 2 + (p.y - y) ** 2; if (d < bd) { bd = d; best = p.i; } }
    if (best !== st.hover) { st.hover = best; draw(); kick(); }
    if (best >= 0) { tip.innerHTML = nodeTip(g, g.nodes[best]); tip.hidden = false; tip.style.left = Math.min(x + 14, W - tip.offsetWidth - 4) + "px"; tip.style.top = Math.max(0, y - tip.offsetHeight - 10) + "px"; } else tip.hidden = true;
  });
  cv.addEventListener("pointerup", () => { st.drag = null; });
  cv.addEventListener("pointerleave", () => { st.hover = -1; tip.hidden = true; draw(); kick(); });
  cv.addEventListener("wheel", e => { e.preventDefault(); st.zoom = clamp(st.zoom * Math.exp(-e.deltaY * .0015), .4, 5); draw(); }, { passive: false });
  draw(); kick();
  return { retheme() { col = colors(); draw(); }, dispose() { cancelAnimationFrame(st.raf); } };
}

/* ---------- structures ---------- */
let molP = null, oclP = null;
function load3Dmol() {
  if (window.$3Dmol) return Promise.resolve(window.$3Dmol);
  return molP ||= new Promise((res, rej) => { const s = document.createElement("script"); s.src = "/vendor/3dmol-2.5.5/3Dmol-min.js"; s.onload = () => res(window.$3Dmol); s.onerror = () => { molP = null; rej(new Error("The 3D viewer failed to load.")); }; document.head.append(s); });
}
const loadOCL = () => oclP ||= import("/vendor/openchemlib-9.25.2/openchemlib.js").catch(e => { oclP = null; throw e; });
const FMT = { pdb: "pdb", cif: "cif", mmcif: "cif", sdf: "sdf", mol: "sdf", mol2: "mol2", xyz: "xyz" };
/* Residues of a parsed macromolecule: one entry per (chain, residue) with Cα position and secondary structure. */
function residues(atoms) {
  const out = [], seen = new Map();
  for (const a of atoms) { if (a.hetflag) continue; const k = a.chain + ":" + a.resi + (a.icode || ""); let r = seen.get(k);
    if (!r) { r = { chain: a.chain, resi: a.resi, resn: a.resn, ss: a.ss || "c", ca: null }; seen.set(k, r); out.push(r); }
    if (a.atom === "CA" || (a.atom === "P" && !r.ca)) r.ca = [a.x, a.y, a.z]; if (a.ss === "h" || a.ss === "s") r.ss = a.ss; }
  return out.filter(r => r.ca);
}
const AA3 = { ALA: "A", ARG: "R", ASN: "N", ASP: "D", CYS: "C", GLN: "Q", GLU: "E", GLY: "G", HIS: "H", ILE: "I", LEU: "L", LYS: "K", MET: "M", PHE: "F", PRO: "P", SER: "S", THR: "T", TRP: "W", TYR: "Y", VAL: "V", SEC: "U", PYL: "O" };
function proteinSummary(atoms, res) {
  const chains = [...new Set(res.map(r => r.chain))], het = [...new Set(atoms.filter(a => a.hetflag && a.resn !== "HOH" && a.resn !== "WAT").map(a => a.resn))];
  const h = res.filter(r => r.ss === "h").length, s = res.filter(r => r.ss === "s").length;
  return `<div class="dv-facts"><span><b>${chains.length}</b> chain${chains.length === 1 ? "" : "s"} (${esc(chains.join(", "))})</span><span><b>${res.length}</b> residues</span><span><b>${atoms.length.toLocaleString()}</b> atoms</span>
    <span>Helix <b>${Math.round(100 * h / (res.length || 1))}%</b> · strand <b>${Math.round(100 * s / (res.length || 1))}%</b></span>${het.length ? `<span>Ligands ${het.slice(0, 8).map(x => `<span class="chip mono">${esc(x)}</span>`).join(" ")}</span>` : ""}</div>`;
}
/* 2D view of a protein: secondary structure and sequence per chain, and the Cα contact map. */
function protein2D(host, atoms) {
  const res = residues(atoms); if (!res.length) { host.innerHTML = '<p class="t3">No residues with Cα atoms were found in this file.</p>'; return {}; }
  const chains = [...new Set(res.map(r => r.chain))];
  const track = chains.map(ch => { const rs = res.filter(r => r.chain === ch);
    return `<div class="dv-chain"><div class="dv-ch-h"><b>Chain ${esc(ch)}</b><span class="t3">${rs.length} residues · ${esc(rs[0].resi)}–${esc(rs[rs.length - 1].resi)}</span></div>
      <div class="dv-ss" role="img" aria-label="Secondary structure of chain ${esc(ch)}">${rs.map(r => `<i class="ss-${r.ss}" title="${esc(r.resn + " " + r.resi + " · " + ({ h: "helix", s: "strand", c: "coil" })[r.ss])}"></i>`).join("")}</div>
      <div class="dv-seq mono">${rs.map(r => AA3[r.resn] || "X").join("").replace(/(.{10})/g, "$1 ")}</div></div>`; }).join("");
  const n = res.length, step = Math.max(1, Math.ceil(n / 700)), m = Math.ceil(n / step), S = Math.min(560, Math.max(240, (host.clientWidth || 600) - 120));
  host.innerHTML = proteinSummary(atoms, res) + `<div class="dv-legend"><span><i style="background:var(--red)"></i>Helix</span><span><i style="background:var(--yellow)"></i>Strand</span><span><i style="background:var(--text-3)"></i>Coil</span></div>${track}
    <div class="sec-h" style="margin-top:18px">Cα contact map <span class="t3" style="font-weight:400">distance between every residue pair${step > 1 ? `, every ${step}th residue` : ""}; contacts under 8 Å are darkest</span></div>
    <div class="dv-plot dv-cmap"><canvas width="${S * (devicePixelRatio || 1)}" height="${S * (devicePixelRatio || 1)}" style="width:${S}px;height:${S}px" role="img" aria-label="Contact map of ${n} residues"></canvas><div class="dv-tip" hidden></div></div>`;
  const cv = host.querySelector("canvas"), ctx = cv.getContext("2d"), tip = host.querySelector(".dv-tip"), sub = res.filter((_, i) => i % step === 0), cell = S / m;
  const draw = () => { const dpr = devicePixelRatio || 1; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.fillStyle = cssv("--bg"); ctx.fillRect(0, 0, S, S);
    const acc = cssv("--accent"); ctx.fillStyle = acc;
    for (let i = 0; i < m; i++) for (let j = 0; j <= i; j++) { const a = sub[i].ca, b = sub[j].ca, d = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]); if (d > 16) continue;
      ctx.globalAlpha = d < 8 ? .95 : .4 * (16 - d) / 8; ctx.fillRect(j * cell, i * cell, Math.max(1, cell), Math.max(1, cell)); ctx.fillRect(i * cell, j * cell, Math.max(1, cell), Math.max(1, cell)); }
    ctx.globalAlpha = .6; ctx.strokeStyle = cssv("--text-3"); let k = 0;   // chain boundaries
    for (const ch of chains) { k += sub.filter(r => r.chain === ch).length; if (k >= m) break; ctx.beginPath(); ctx.moveTo(k * cell, 0); ctx.lineTo(k * cell, S); ctx.moveTo(0, k * cell); ctx.lineTo(S, k * cell); ctx.stroke(); }
    ctx.globalAlpha = 1; };
  draw();
  cv.onmousemove = e => { const b = cv.getBoundingClientRect(), i = Math.floor((e.clientY - b.top) / cell), j = Math.floor((e.clientX - b.left) / cell); if (i < 0 || j < 0 || i >= m || j >= m) { tip.hidden = true; return; }
    const a = sub[i], c = sub[j], d = Math.hypot(a.ca[0] - c.ca[0], a.ca[1] - c.ca[1], a.ca[2] - c.ca[2]);
    tip.innerHTML = `${esc(a.chain)}:${esc(a.resn)}${esc(a.resi)} ↔ ${esc(c.chain)}:${esc(c.resn)}${esc(c.resi)}<br>${d.toFixed(1)} Å`; tip.hidden = false;
    tip.style.left = Math.min(e.clientX - b.left + 14, S - 10) + "px"; tip.style.top = Math.max(0, e.clientY - b.top - tip.offsetHeight - 10) + "px"; };
  cv.onmouseleave = () => { tip.hidden = true; };
  return { retheme: draw };
}
/* Small molecules: SDF/MOL records go straight to OpenChemLib; MOL2/XYZ are rebuilt from 3Dmol's parse. */
function molRecords(text, e) { if (e === "mol") return [text]; if (e === "sdf") return text.split(/^\$\$\$\$\s*$/m).map(s => s.replace(/^\s*\n/, "")).filter(s => /M\s+END/.test(s)).slice(0, 500); return null; }
async function molecules2D(host, text, e, st) {
  const OCL = await loadOCL();
  let mols = [];
  const recs = molRecords(text, e);
  if (recs) mols = recs.map(r => { const m = OCL.Molecule.fromMolfile(r); return { m, name: r.split("\n")[0].trim() }; });
  else { const $3D = await load3Dmol(), frames = $3D.Parsers[FMT[e]](text, { keepH: true, assignBonds: true }) || [];
    mols = (Array.isArray(frames[0]) ? frames : [frames]).slice(0, 200).map((atoms, k) => { const m = new OCL.Molecule(atoms.length, atoms.length * 2);
      atoms.forEach(a => { const z = OCL.Molecule.getAtomicNoFromLabel(String(a.elem || "C").replace(/^(.)(.*)$/, (_, x, y) => x.toUpperCase() + y.toLowerCase())); const i = m.addAtom(z || 6); m.setAtomX(i, a.x); m.setAtomY(i, a.y); m.setAtomZ(i, a.z); });
      atoms.forEach((a, i) => (a.bonds || []).forEach((j, b) => { if (j > i) m.addBond(i, j, a.bondOrder?.[b] || 1); }));
      m.ensureHelperArrays(OCL.Molecule.cHelperRings); return { m, name: atoms.title || `Molecule ${k + 1}` }; }); }
  const per = 24, pages = Math.max(1, Math.ceil(mols.length / per)); st.mpage = clamp(st.mpage || 0, 0, pages - 1);
  const card = ({ m, name }, i) => { let svg = "", formula = "", mw = "";
    try { const c = m.getCompactCopy(); c.stripSmallFragments?.(); c.removeExplicitHydrogens?.(); c.inventCoordinates(); svg = c.toSVG(220, 170, undefined, { autoCrop: true, autoCropMargin: 14, suppressChiralText: true, noImplicitAtomLabelColors: false });
      const f = m.getMolecularFormula(); formula = f.formula; mw = f.relativeWeight; } catch { /* unparsable record: shown without a drawing */ }
    return `<figure class="dv-mol"><div class="dv-mol-i">${svg ? `<img alt="2D structure of ${esc(name)}" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}">` : '<span class="t3">Could not draw this record</span>'}</div>
      <figcaption><b class="trunc" title="${esc(name)}">${esc(name || `Molecule ${i + 1}`)}</b><span class="mono t2">${esc(formula)}</span>${mw ? `<span class="t3">${(+mw).toFixed(2)} g/mol</span>` : ""}</figcaption></figure>`; };
  host.innerHTML = `<div class="dv-legend"><span class="t3">${mols.length} molecule${mols.length === 1 ? "" : "s"} · drawn in 2D from the file's connectivity (hydrogens implicit)</span></div><div class="dv-mols">${mols.slice(st.mpage * per, st.mpage * per + per).map((x, i) => card(x, st.mpage * per + i)).join("")}</div>` +
    (pages > 1 ? `<div class="gfoot"><span>Page ${st.mpage + 1} of ${pages}</span><span class="pg"><button type="button" class="icon-btn" data-mpage="-1" aria-label="Previous page"${st.mpage <= 0 ? " disabled" : ""}>${ico('<path d="M10 3 5 8l5 5"/>')}</button><button type="button" class="icon-btn" data-mpage="1" aria-label="Next page"${st.mpage >= pages - 1 ? " disabled" : ""}>${ico('<path d="m6 3 5 5-5 5"/>')}</button></span></div>` : "");
  return mols.length;
}
/* SMILES column in a table → 2D drawings. */
async function smiles2D(host, t, r) {
  const OCL = await loadOCL(), lab = r.label !== r.smiles ? r.label : null;
  const rows = [...Array(Math.min(t.n, 48)).keys()].filter(i => r.smiles.vals[i]);
  host.innerHTML = `<div class="dv-mols">${rows.map(i => { let svg = ""; try { const m = OCL.Molecule.fromSmiles(String(r.smiles.vals[i])); m.inventCoordinates(); svg = m.toSVG(220, 170, undefined, { autoCrop: true, autoCropMargin: 14, suppressChiralText: true }); } catch {}
    return `<figure class="dv-mol"><div class="dv-mol-i">${svg ? `<img alt="2D structure" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}">` : '<span class="t3">Invalid SMILES</span>'}</div><figcaption><b class="trunc">${esc(lab ? lab.vals[i] : `Row ${i + 1}`)}</b><span class="mono t3 trunc" title="${esc(r.smiles.vals[i])}">${esc(r.smiles.vals[i])}</span></figcaption></figure>`; }).join("")}</div>${t.n > 48 ? `<p class="dv-note">First 48 of ${t.n} rows.</p>` : ""}`;
}
/* 3D: 3Dmol.js. Proteins as cartoon (hetero groups as sticks), small molecules as ball-and-stick. */
async function structure3D(host, text, e, protein, st) {
  const $3D = await load3Dmol();
  host.innerHTML = `<div class="dv-3d" role="img" aria-label="Interactive 3D structure"></div><div class="dv-hint">Drag to rotate · scroll to zoom · right-drag to pan</div>`;
  const el = host.querySelector(".dv-3d"), bg = () => cssv("--bg") || "#171717";
  const v = $3D.createViewer(el, { backgroundColor: bg(), antialias: true, id: "dv3d" + Math.random().toString(36).slice(2) });
  const fmt = FMT[e];
  let models = [];
  if (protein) models = [v.addModel(text, fmt)];
  else { const recs = molRecords(text, e); models = recs ? recs.slice(0, 200).map(r => v.addModel(r, "sdf")) : [v.addModel(text, fmt)]; }
  const style = () => {
    v.setStyle({}, {});
    models.forEach((m, i) => { const show = protein || i === (st.mol || 0); if (!show) return;
      if (protein) {
        // N→C rainbow per chain; B-factor (or AlphaFold pLDDT) on red-white-blue between the file's own extremes
        const bs = st.atoms?.length ? extent(st.atoms.map(a => a.b)) : [0, 100];
        const color = st.color === "rainbow" ? { color: "spectrum" } : st.color === "bfactor" ? { colorscheme: { prop: "b", gradient: "rwb", min: bs[0], max: bs[1] } } : { colorscheme: "chain" };
        if (st.style === "sticks") m.setStyle({ hetflag: false }, { stick: { radius: .16, ...(st.color === "chain" ? { colorscheme: "chain" } : st.color === "bfactor" ? color : {}) } });
        else m.setStyle({ hetflag: false }, st.style === "line" ? { line: {} } : { cartoon: { ...color, arrows: true } });
        m.setStyle({ hetflag: true, not: { resn: ["HOH", "WAT"] } }, { stick: { radius: .2, colorscheme: "greenCarbon" } });
      } else m.setStyle({}, st.style === "sticks" ? { stick: { radius: .14 } } : st.style === "spheres" ? { sphere: { scale: .9 } } : { stick: { radius: .12 }, sphere: { scale: .28 } });
    });
    v.removeAllSurfaces();
    if (protein && st.surface) v.addSurface($3D.SurfaceType.VDW, { opacity: .55, color: cssv("--text-2") || "#999" }, { hetflag: false });
    v.zoomTo(protein ? {} : { model: models[st.mol || 0] }); v.render();
  };
  style();
  const ro = new ResizeObserver(() => { v.resize(); v.render(); }); ro.observe(el);
  return { restyle: style, retheme() { v.setBackgroundColor(bg()); v.render(); }, dispose() { ro.disconnect(); try { v.clear(); } catch {} }, count: models.length };
}

/* ---------- the viewer ----------
   One persistent element per file. Its toolbar holds the views the file supports
   (Chart/Table/Network/Molecules, or 2D/3D), and its state survives app re-renders. */
const LIVE = new Map();   // key -> {el, st, inst}
const T_ICONS = { chart: '<path d="M2.5 13.5h11"/><path d="M4.5 11V8M7.5 11V4.5M10.5 11V6.5"/>', table: KIND.table.d, network: KIND.network.d, mols: KIND.molecule.d };
async function buildView(el, f, st) {
  const k = kindOf(f), body = el.querySelector(".dv-body"), bar = el.querySelector(".dv-tools");
  const busy = () => { body.innerHTML = `<div class="dv-skel" data-sk-box></div>`; };
  try {
    if (k === "figure") { const b = await fetchFile(f, "blob"); st.url ||= URL.createObjectURL(b); bar.innerHTML = ""; body.innerHTML = `<img class="dv-img" alt="${esc(f.file_name || "Experiment figure")}" src="${st.url}">`; return; }
    if (k === "pdf") { bar.innerHTML = ""; body.innerHTML = `<div class="dv-empty">${kindIcon("pdf")}<p>PDF documents open in your browser's viewer.</p><a class="btn" href="/api/evidence/${encodeURIComponent(f.id)}" target="_blank" rel="noopener">Open PDF</a></div>`; return; }
    busy();
    const text = await fetchFile(f);
    if (!st.parsed) {
      const e = ext(f.file_name); let j;
      if (e === "json") { try { j = JSON.parse(text); } catch { j = undefined; } JSON_KIND.set(f.id, j === undefined ? "text" : isNetworkJson(j) ? "network" : "table"); if (JSON_KIND.get(f.id) !== "table") document.dispatchEvent(new CustomEvent("platodata:kind")); }
      const kk = kindOf(f);
      if (kk === "table") { const t = tableFromText(text, f.file_name); if (t && t.cols.length) { const r = roles(t); st.parsed = { t, r, types: chartTypes(t, r), net: null }; } else JSON_KIND.set(f.id, "text"); }
      if (kindOf(f) === "network") st.parsed = { g: parseNetwork(text, f.file_name, j) };
      if (kindOf(f) === "text") st.parsed = { text };
      if (kindOf(f) === "protein" || kindOf(f) === "molecule") st.parsed = { text };
      el.querySelector(".dv-h .dv-ki")?.replaceWith(Object.assign(document.createElement("span"), { innerHTML: kindIcon(kindOf(f)) }).firstChild);
    }
    await renderView(el, f, st);
  } catch (err) { body.innerHTML = `<div class="dv-empty">${kindIcon("text")}<p class="err">${esc(err.message || String(err))}</p></div>`; }
}
function seg(attr, cur, opts) { return `<div class="seg" role="group">${opts.map(([v, l, d]) => `<button type="button" data-${attr}="${v}" class="${cur === v ? "on" : ""}" aria-pressed="${cur === v}">${d ? ico(d, 13) : ""}${l}</button>`).join("")}</div>`; }
const sel = (attr, cur, opts, label) => `<label class="dv-sel"><span class="t3">${label}</span><select data-${attr} aria-label="${label}">${opts.map(([v, l]) => `<option value="${esc(v)}"${String(cur) === String(v) ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`;
async function renderView(el, f, st) {
  const k = kindOf(f), body = el.querySelector(".dv-body"), bar = el.querySelector(".dv-tools");
  st.inst?.dispose?.(); st.inst = null;
  if (k === "text") { bar.innerHTML = ""; const t = st.parsed.text; let s = t; if (ext(f.file_name) === "json") try { s = JSON.stringify(JSON.parse(t), null, 2); } catch {}
    body.innerHTML = `<pre class="src">${esc(s.length > 200000 ? s.slice(0, 200000) + "\n…" : s)}</pre>`; return; }
  if (k === "table") {
    const { t, r, types } = st.parsed, net = r.src && r.tgt || r.term && r.genes, mol = !!r.smiles;
    const views = [...(types.length ? [["chart", "Chart", T_ICONS.chart]] : []), ["table", "Table", T_ICONS.table], ...(net ? [["network", "Network", T_ICONS.network]] : []), ...(mol ? [["mols", "Molecules", T_ICONS.mols]] : [])];
    if (!views.some(v => v[0] === st.view)) st.view = views[0][0];
    if (st.view === "network") { st.dim ||= "2d"; st.net ||= networkFromTable(t, r); }
    if (st.view === "chart" && !st.chart) { const nums = t.cols.map((c, i) => c.num ? i : -1).filter(i => i >= 0), cats = t.cols.map((c, i) => c.num ? -1 : i).filter(i => i >= 0), type = types[0][0];
      st.chart = { type, x: type === "bar" ? cats[0] : nums[0], ys: [type === "bar" ? nums[0] : nums[1] ?? nums[0]], label: r.label ? t.cols.indexOf(r.label) : null, zscore: true }; }
    const c = st.chart, nums = t.cols.map((cc, i) => [i, cc]).filter(([, cc]) => cc.num), cats = t.cols.map((cc, i) => [i, cc]).filter(([, cc]) => !cc.num);
    let ctl = seg("dview", st.view, views);
    if (st.view === "chart") { ctl += sel("dtype", c.type, types, "Chart");
      if (["scatter", "line"].includes(c.type)) ctl += sel("dx", c.x, nums.map(([i, cc]) => [i, cc.name]), "X") + sel("dy", c.ys[0], nums.map(([i, cc]) => [i, cc.name]), "Y") + sel("dy2", c.ys[1] ?? "", [["", "None"], ...nums.map(([i, cc]) => [i, cc.name])], "Y₂");
      if (c.type === "bar") ctl += sel("dx", c.x, cats.map(([i, cc]) => [i, cc.name]), "Category") + sel("dy", c.ys[0], nums.map(([i, cc]) => [i, cc.name]), "Value");
      if (c.type === "histogram") ctl += sel("dy", c.ys[0], nums.map(([i, cc]) => [i, cc.name]), "Column");
      if (c.type === "heatmap") ctl += `<label class="dv-chk"><input type="checkbox" data-dz${c.zscore ? " checked" : ""}> Z-score rows</label>`;
      if (c.type === "volcano") ctl += sel("dfc", c.fcT ?? 1, [[.5, "|log2FC| > 0.5"], [1, "|log2FC| > 1"], [1.5, "|log2FC| > 1.5"], [2, "|log2FC| > 2"]], "Fold change") + sel("dpt", c.pT ?? .05, [[.01, "< 0.01"], [.05, "< 0.05"], [.1, "< 0.1"]], esc((r.padj || r.p).name));
    }
    if (st.view === "table") ctl += `<label class="gsearch dv-q">${ico('<circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/>', 13)}<input type="search" data-dq placeholder="Filter rows" value="${esc(st.q || "")}" aria-label="Filter rows" autocomplete="off"></label>`;
    if (st.view === "network") ctl += seg("ddim", st.dim, [["2d", "2D"], ["3d", "3D"]]);
    bar.innerHTML = ctl + `<span class="dv-meta t3">${t.n.toLocaleString()} rows × ${t.cols.length} columns</span>`;
    if (st.view === "chart") drawChart(body, t, r, c);
    else if (st.view === "table") { st.grid ||= { q: st.q || "", sort: null, page: 0 }; st.grid.q = st.q || ""; body.innerHTML = gridHtml(t, st.grid); }
    else if (st.view === "network") { if (!st.net) { body.innerHTML = '<p class="t3">No network in this table.</p>'; return; } body.innerHTML = ""; if (st.dim === "3d") st.inst = network3D(body, st.net); else network2D(body, st.net); }
    else if (st.view === "mols") { body.innerHTML = `<div class="dv-skel" data-sk-box></div>`; await smiles2D(body, t, r); }
    return;
  }
  if (k === "network") { st.dim ||= "2d"; const g = st.parsed.g; bar.innerHTML = seg("ddim", st.dim, [["2d", "2D"], ["3d", "3D"]]) + (g.name ? `<span class="dv-meta t3">${esc(g.name)}</span>` : "");
    body.innerHTML = ""; if (!g.nodes.length) { body.innerHTML = '<p class="t3">This network has no nodes.</p>'; return; } if (st.dim === "3d") st.inst = network3D(body, g); else network2D(body, g); return; }
  if (k === "protein" || k === "molecule") {
    const protein = k === "protein", e = ext(f.file_name); st.dim ||= "3d";
    if (protein) { st.style ||= "cartoon"; st.color ||= "chain"; } else st.style ||= "ballstick";
    let ctl = seg("ddim", st.dim, [["2d", "2D"], ["3d", "3D"]]);
    if (st.dim === "3d") ctl += protein ? seg("dstyle", st.style, [["cartoon", "Cartoon"], ["sticks", "Sticks"], ["line", "Lines"]]) + sel("dcolor", st.color, [["chain", "Chain"], ["rainbow", "N→C rainbow"], ["bfactor", "B-factor / pLDDT"]], "Colour") + `<label class="dv-chk"><input type="checkbox" data-dsurf${st.surface ? " checked" : ""}> Surface</label>`
      : seg("dstyle", st.style, [["ballstick", "Ball and stick"], ["sticks", "Sticks"], ["spheres", "Spheres"]]);
    bar.innerHTML = ctl;
    body.innerHTML = `<div class="dv-skel" data-sk-box></div>`;
    if (st.dim === "2d") {
      if (protein) { const $3D = await load3Dmol(); st.atoms ||= ($3D.Parsers[FMT[e]](st.parsed.text, {}) || [])[0] || []; body.innerHTML = ""; st.inst = protein2D(body, st.atoms); }
      else await molecules2D(body, st.parsed.text, e, st);
      return;
    }
    body.innerHTML = "";
    if (!protein) { const recs = molRecords(st.parsed.text, e); if (recs && recs.length > 1) { const names = recs.map((r, i) => r.split("\n")[0].trim() || `Molecule ${i + 1}`);
      bar.insertAdjacentHTML("beforeend", sel("dmol", st.mol || 0, names.map((nm, i) => [i, `${i + 1}. ${nm}`]), "Molecule")); } }
    const wrap = document.createElement("div"); body.append(wrap);
    if (protein) { const $3D = await load3Dmol(); st.atoms ||= ($3D.Parsers[FMT[e]](st.parsed.text, {}) || [])[0] || []; body.insertAdjacentHTML("afterbegin", proteinSummary(st.atoms, residues(st.atoms))); }
    st.inst = await structure3D(wrap, st.parsed.text, e, protein, st);
  }
}
function bindView(el, f, st) {
  const re = () => renderView(el, f, st).catch(err => { el.querySelector(".dv-body").innerHTML = `<p class="err">${esc(err.message)}</p>`; });
  el.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b || !el.contains(b)) return;
    const d = b.dataset;
    if (d.dview) { st.view = d.dview; re(); }
    else if (d.ddim) { st.dim = d.ddim; re(); }
    else if (d.dstyle) { st.style = d.dstyle; if (st.inst?.restyle) { el.querySelectorAll("[data-dstyle]").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); }); st.inst.restyle(); } else re(); }
    else if (d.dsort != null) { const k = +d.dsort, g = st.grid; g.sort = g.sort?.k === k ? (g.sort.d === 1 ? { k, d: -1 } : null) : { k, d: 1 }; g.page = 0; el.querySelector(".dv-body").innerHTML = gridHtml(st.parsed.t, g); }
    else if (d.dpage) { st.grid.page += +d.dpage; el.querySelector(".dv-body").innerHTML = gridHtml(st.parsed.t, st.grid); }
    else if (d.mpage) { st.mpage = (st.mpage || 0) + +d.mpage; re(); }
  });
  el.addEventListener("change", e => {
    const t = e.target, d = t.dataset, c = st.chart;
    if (d.dtype != null) { const tt = st.parsed.t, nums = tt.cols.map((cc, i) => cc.num ? i : -1).filter(i => i >= 0), cats = tt.cols.map((cc, i) => cc.num ? -1 : i).filter(i => i >= 0);
      c.type = t.value; if (c.type === "bar") { c.x = cats[0]; c.ys = [nums[0]]; } else if (["scatter", "line"].includes(c.type)) { if (!tt.cols[c.x]?.num) c.x = nums[0]; c.ys = [nums.find(i => i !== c.x) ?? nums[0]]; } else if (c.type === "histogram") c.ys = [nums[0]]; re(); }
    else if (d.dx != null) { c.x = +t.value; re(); }
    else if (d.dy != null) { c.ys[0] = +t.value; re(); }
    else if (d.dy2 != null) { c.ys = t.value === "" ? [c.ys[0]] : [c.ys[0], +t.value]; re(); }
    else if (d.dfc != null) { c.fcT = +t.value; re(); }
    else if (d.dpt != null) { c.pT = +t.value; re(); }
    else if (d.dz != null) { c.zscore = t.checked; re(); }
    else if (d.dcolor != null) { st.color = t.value; st.inst?.restyle ? st.inst.restyle() : re(); }
    else if (d.dsurf != null) { st.surface = t.checked; st.inst?.restyle ? st.inst.restyle() : re(); }
    else if (d.dmol != null) { st.mol = +t.value; st.inst?.restyle ? st.inst.restyle() : re(); }
  });
  let qt = 0;
  el.addEventListener("input", e => { if (e.target.dataset.dq == null) return; clearTimeout(qt); const v = e.target.value; qt = setTimeout(() => { st.q = v; st.grid.q = v; st.grid.page = 0; el.querySelector(".dv-body").innerHTML = gridHtml(st.parsed.t, st.grid); }, 120); });
}
/* The viewer element for a file: created once, then re-attached wherever its slot appears. */
function viewer(f, ctx = {}) {
  const key = f.id;
  let v = LIVE.get(key);
  if (!v) {
    const el = document.createElement("section"); el.className = "dv card"; el.dataset.file = f.id;
    const k = kindOf(f);
    el.innerHTML = `<div class="dv-h">${kindIcon(k)}<b class="trunc" title="${esc(f.file_name || "")}">${esc(f.file_name || KIND[k].l)}</b><span class="t3">${esc(bytes(f.size_bytes))}</span>${ctx.from ? `<span class="t3 trunc">· ${esc(ctx.from)}</span>` : ""}
      <span class="dv-act"><a class="btn ghost sm" href="/api/evidence/${encodeURIComponent(f.id)}" download="${esc(f.file_name || "")}" title="Download the file as the experiment wrote it">${ico('<path d="M8 2.5v8M4.5 7 8 10.5 11.5 7M3 13.5h10"/>', 13)}Download</a></span></div>
      <div class="dv-tools"></div><div class="dv-body"></div>`;
    v = { el, st: {}, f }; LIVE.set(key, v); bindView(el, f, v.st);
    // Build once it is in the document (charts size themselves to their container).
    requestAnimationFrame(() => buildView(el, f, v.st));
  }
  return v.el;
}
/* Drop viewers that are no longer in the document (navigated away). */
function sweep() { for (const [k, v] of LIVE) if (!v.el.isConnected) { v.st.inst?.dispose?.(); if (v.st.url) URL.revokeObjectURL(v.st.url); LIVE.delete(k); } }
/* Redraw size-dependent views when their container width changes, and recolour on theme change.
   A detached viewer reports width 0; it is skipped so re-attaching it after a re-render does not redraw. */
let lastW = new WeakMap();
const ro = new ResizeObserver(entries => { for (const en of entries) { const el = en.target, w = Math.round(en.contentRect.width), prev = lastW.get(el); if (!w || !el.isConnected) continue; lastW.set(el, w);
  if (prev == null || Math.abs(prev - w) < 24) continue; const v = LIVE.get(el.dataset.file); if (!v?.st.parsed) continue;
  const resizable = (kindOf(v.f) === "table" && ["chart", "network"].includes(v.st.view)) || kindOf(v.f) === "network" || (kindOf(v.f) === "protein" && v.st.dim === "2d");
  if (resizable) renderView(v.el, v.f, v.st).catch(() => {}); } });
function observed(f, ctx) { const el = viewer(f, ctx); ro.observe(el); return el; }
/* Swap every [data-dv] slot under root for its persistent viewer. */
function mount(root, files, ctx = {}) {
  root.querySelectorAll("[data-dv]").forEach(slot => { const f = files.find(x => x.id === slot.dataset.dv); if (f) slot.replaceWith(observed(f, ctx[f.id] || {})); });
}
new MutationObserver(() => { for (const v of LIVE.values()) { if (!v.el.isConnected || !v.st.parsed) continue;
  if (v.st.inst?.retheme) v.st.inst.retheme(); else if (kindOf(v.f) === "table" && v.st.view === "network" || kindOf(v.f) === "network") renderView(v.el, v.f, v.st).catch(() => {}); } })
  .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

/* ---------- file list ---------- */
function fileRow(f, on, ctx) {
  const k = kindOf(f);
  return `<a class="dv-row${on ? " on" : ""}" href="${ctx.href(f)}"${on ? ' aria-current="true"' : ""}>${kindIcon(k)}<span class="trunc">${esc(f.file_name || KIND[k].l)}</span><span class="t3">${esc(bytes(f.size_bytes))}</span></a>`;
}

/* ---------- experiment workflow ---------- */
const WF_STATUS = { done: "var(--green)", fail: "var(--red)", run: "var(--yellow)", todo: "var(--text-3)", skip: "var(--text-3)" };
function wfStep(s) {
  const icon = s.state === "done" ? `<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6.5" fill="var(--green)"/><path d="M4.3 7.2 6.2 9l3.5-3.8" fill="none" stroke="var(--bg)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`
    : s.state === "fail" ? `<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6.5" fill="var(--red)"/><path d="m4.9 4.9 4.2 4.2m0-4.2-4.2 4.2" stroke="var(--bg)" stroke-width="1.5" stroke-linecap="round"/></svg>`
    : `<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill="none" stroke="${WF_STATUS[s.state]}" stroke-width="1.5"${s.state === "todo" || s.state === "skip" ? ' stroke-dasharray="1.6 1.9"' : ""}/>${s.state === "run" ? `<circle cx="7" cy="7" r="2.6" fill="var(--yellow)"/>` : ""}</svg>`;
  return `<li class="wf-s wf-${s.state}"><div class="wf-h">${icon}<b>${esc(s.title)}</b></div>${s.lines.map(l => `<div class="wf-l">${l}</div>`).join("")}</li>`;
}
/* steps: [{title, state: done|fail|run|todo|skip, lines: [html]}] */
const workflowHtml = steps => `<ol class="wf" aria-label="Experiment workflow">${steps.map(wfStep).join("")}</ol>`;

window.PlatoData = Object.freeze({ kindOf, KIND, kindIcon, FILTERS, inFilter, bytes, fileRow, mount, sweep, workflowHtml, fetchFile, ext,
  // exposed for tests
  _t: { tableFromText, roles, chartTypes, parseNetwork, networkFromTable, ticks, parseDelimited } });
})();
