// Reproducible vendor build: `npm ci && npm run build` (pinned versions in package-lock.json).
import { build } from "esbuild";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";

const version = JSON.parse(readFileSync("node_modules/liveline/package.json", "utf8")).version;

// Small, asserted source patches to Liveline. Each must match exactly once, so a version
// bump that moves the code fails the build instead of shipping silently unpatched.
const PATCHES = [
  {
    why: "Multi-series end labels: series that end at the same value drew their labels on top of each other. Stack them 12px apart, kept inside the plot.",
    find: `    for (const entry of allPts) {
      if (entry.alpha < 0.01) continue;
      const lastPt = entry.pts[entry.pts.length - 1];`,
    replace: `    const labelled = allPts.filter((e) => e.label && e.alpha >= 0.01).map((e) => ({ e, y: e.pts[e.pts.length - 1][1] })).sort((a, b) => a.y - b.y);
    for (let i = 1; i < labelled.length; i++) labelled[i].y = Math.max(labelled[i].y, labelled[i - 1].y + 12);
    for (let i = labelled.length - 1, lim = layout.h - layout.pad.bottom - 4; i >= 0; lim = labelled[i].y - 12, i--) labelled[i].y = Math.min(labelled[i].y, lim);
    for (const l of labelled) l.e.labelY = l.y;
    for (const entry of allPts) {
      if (entry.alpha < 0.01) continue;
      const lastPt = entry.pts[entry.pts.length - 1];`,
  },
  {
    why: "Draw each end label at its de-overlapped position.",
    find: `ctx.fillText(entry.label, lastPt[0] + 6, lastPt[1] + 3.5);`,
    replace: `ctx.fillText(entry.label, lastPt[0] + 6, (entry.labelY ?? lastPt[1]) + 3.5);`,
  },
];
const patchLiveline = {
  name: "patch-liveline",
  setup(b) {
    b.onLoad({ filter: /[\\/]liveline[\\/]dist[\\/]index\.js$/ }, (args) => {
      let src = readFileSync(args.path, "utf8");
      for (const p of PATCHES) {
        const n = src.split(p.find).length - 1;
        if (n !== 1) throw new Error(`liveline patch matched ${n} times: ${p.why}`);
        src = src.replace(p.find, () => p.replace);
      }
      return { contents: src, loader: "js" };
    });
  },
};
const out = `../../public/vendor/liveline-${version}`;
mkdirSync(out, { recursive: true });
await build({
  entryPoints: ["entry.js"],
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2020"],
  define: { "process.env.NODE_ENV": '"production"' },
  legalComments: "none",
  outfile: `${out}/liveline.js`,
  plugins: [patchLiveline],
});
const lic = (p) => readFileSync(p, "utf8").trim();
writeFileSync(`${out}/LICENSE`, [
  "liveline (MIT), with the patches listed in vendor-src/liveline/build.mjs\n\n" + lic("node_modules/liveline/LICENSE"),
  "react (MIT)\n\n" + lic("node_modules/react/LICENSE"),
  "react-dom (MIT)\n\n" + lic("node_modules/react-dom/LICENSE"),
  "scheduler (MIT)\n\n" + lic("node_modules/scheduler/LICENSE"),
].join("\n\n----------------------------------------\n\n") + "\n");
console.log(`built ${out}/liveline.js`);
