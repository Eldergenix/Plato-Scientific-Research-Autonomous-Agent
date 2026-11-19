#!/usr/bin/env python3
"""Check that every "Get started" example on the agent home can actually run.

Each example card (``cloudflare/plato-scientist/public/app/agent.js``, ``EXAMPLES``) asks a
question whose answer needs public data and tools on the ``plato-lab`` template. This script
runs the core pipeline of each example the way the scientist records an experiment
(``setup.sh`` with the network on, then ``experiment.py`` offline, through
:func:`plato.scientist.workspace.runtime.run_recipe`) and checks a known answer, so a card
never promises something the sandbox cannot do. It is a smoke test of data sources, tools
and run time, not a substitute for the campaign itself.

    E2B_API_KEY=... python scripts/e2b_example_checks.py --out example-checks
    python scripts/e2b_example_checks.py --only solubility,statistics --local   # host run

Recipes (one per card, same keys as ``EXAMPLES[].key``):

* ``variants``: E. coli K-12 (NC_000913.3) from NCBI, wgsim reads with known SNPs and
  indels, BWA-MEM2 alignment, GATK HaplotypeCaller and bcftools calls scored against truth.
* ``hemoglobin``: deoxy (4HHB) and oxy (1HHO, biological assembly) haemoglobin from RCSB,
  superimposed on the alpha1-beta1 dimer with Biopython; per-residue displacement.
* ``expression``: the airway RNA-seq dataset (Himes et al. 2014) with DESeq2 and
  clusterProfiler GO enrichment of the dexamethasone-responsive genes.
* ``solubility``: the Delaney (ESOL) set with RDKit descriptors; held-out R^2 of logP alone
  against Delaney's four descriptors.
* ``supernovae``: Pantheon+ distances with astropy; flat LCDM and wCDM fits.
* ``statistics``: OLS slope interval coverage under heteroskedastic errors, classical vs HC3.

Needs only ``pip install e2b==2.64.0`` (the workspace runtime is loaded without the
scientist service's dependencies).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _samples():
    """The viz-samples script: shares its runtime loader and metrics marker."""
    spec = importlib.util.spec_from_file_location("e2b_viz_samples", HERE / "e2b_viz_samples.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RECIPES: dict[str, dict[str, object]] = {}


def recipe(name: str, setup: str, code: str, expect) -> None:
    """``expect(metrics) -> str | None``: None when the known answer holds, else why not."""
    RECIPES[name] = {"setup": setup, "code": code, "expect": expect}


# ---------------------------------------------------------------------------- variants
recipe(
    "variants",
    r"""set -euo pipefail
curl -fsSL --retry 5 --retry-all-errors \
  "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id=NC_000913.3&rettype=fasta&retmode=text" \
  -o ecoli.fa
test "$(grep -c '>' ecoli.fa)" = 1
""",
    r"""import csv, json, os, subprocess, time

def sh(cmd):
    t = time.monotonic()
    subprocess.run(["bash", "-o", "pipefail", "-c", cmd], check=True)
    print(f"{time.monotonic() - t:7.1f}s  {cmd[:90]}", flush=True)

seed = int(open("plato_seed.txt").read().strip() or 1)
threads = os.cpu_count() or 2
# Haploid genome: wgsim -h puts every mutation on the one haplotype. 300k pairs x 2 x 150 bp
# is about 19x over 4.64 Mb.
sh(f"wgsim -h -N 300000 -1 150 -2 150 -r 0.001 -R 0.15 -X 0.3 -e 0.002 -S {seed} ecoli.fa r1.fq r2.fq > truth.txt")
sh("samtools faidx ecoli.fa && bwa-mem2 index ecoli.fa 2>/dev/null")
sh(f"bwa-mem2 mem -t {threads} -R '@RG\\tID:sim\\tSM:sim\\tPL:ILLUMINA' ecoli.fa r1.fq r2.fq 2>/dev/null"
   f" | samtools sort -@ {threads} -o sim.bam - && samtools index sim.bam")
sh("bcftools mpileup -Ou -f ecoli.fa sim.bam 2>/dev/null | bcftools call --ploidy 1 -mv -Oz -o bcftools.vcf.gz 2>/dev/null")
sh("gatk CreateSequenceDictionary -R ecoli.fa -O ecoli.dict >/dev/null 2>&1")
sh(f"gatk --java-options -Xmx4g HaplotypeCaller -R ecoli.fa -I sim.bam -O gatk.vcf.gz -ploidy 1 "
   f"--native-pair-hmm-threads {threads} >/dev/null 2>&1")

# wgsim truth: chrom, pos, ref, alt, haplotype flag; '-' marks the empty side of an indel.
truth = {"snp": set(), "indel": set()}
for line in open("truth.txt"):
    c, pos, ref, alt = line.split("\t")[:4]
    kind = "snp" if ref != "-" and alt != "-" and len(ref) == len(alt) == 1 else "indel"
    truth[kind].add(int(pos))

def calls(path):
    out = {"snp": set(), "indel": set()}
    txt = subprocess.run(["bcftools", "view", "-H", path], capture_output=True, text=True, check=True).stdout
    for line in txt.splitlines():
        f = line.split("\t")
        ref, alts = f[3], f[4].split(",")
        kind = "snp" if len(ref) == 1 and all(len(a) == 1 for a in alts) else "indel"
        out[kind].add(int(f[1]))
    return out

def score(called, true, window):
    # Indel positions differ by convention (VCF anchors on the base before), so they match
    # within a small window; SNPs must match exactly.
    near = lambda p, s: any((p + d) in s for d in range(-window, window + 1))
    tp_c = sum(1 for p in called if near(p, true))
    tp_t = sum(1 for q in true if near(q, called))
    precision = tp_c / len(called) if called else 0.0
    recall = tp_t / len(true) if true else 0.0
    return precision, recall

rows, metrics = [], {}
for caller, path in (("gatk", "gatk.vcf.gz"), ("bcftools", "bcftools.vcf.gz")):
    c = calls(path)
    for kind, window in (("snp", 0), ("indel", 5)):
        p, r = score(c[kind], truth[kind], window)
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        rows.append({"caller": caller, "type": kind, "truth": len(truth[kind]), "called": len(c[kind]),
                     "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)})
        metrics[f"{caller}_{kind}_f1"] = round(f1, 4)
with open("caller_accuracy.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
for r in rows:
    print(r)
metrics["truth_snps"] = len(truth["snp"]); metrics["truth_indels"] = len(truth["indel"])
print("PLATO_METRICS " + json.dumps(metrics))
""",
    lambda m: None
    if m["truth_snps"] > 2000
    and m["gatk_snp_f1"] > 0.95
    and m["bcftools_snp_f1"] > 0.95
    and m["gatk_indel_f1"] > 0.5
    else "a caller missed most simulated variants",
)

# ---------------------------------------------------------------------------- hemoglobin
recipe(
    "hemoglobin",
    r"""set -euo pipefail
curl -fsSL --retry 5 --retry-all-errors https://files.rcsb.org/download/4HHB.cif -o deoxy_4hhb.cif
curl -fsSL --retry 5 --retry-all-errors https://files.rcsb.org/download/1HHO-assembly1.cif -o oxy_1hho_assembly1.cif
""",
    r"""import csv, json
import numpy as np
from scipy import stats
from Bio.PDB import MMCIFParser, Superimposer, PDBIO, NeighborSearch
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

parser = MMCIFParser(QUIET=True)
deoxy = parser.get_structure("deoxy", "deoxy_4hhb.cif")[0]
oxy = parser.get_structure("oxy", "oxy_1hho_assembly1.cif")[0]

def chains_by_entity(path, model):
    # Polymer chains grouped by entity (alpha, beta), in file order: first copy is the
    # alpha1/beta1 dimer, the second alpha2/beta2.
    d = MMCIF2Dict(path)
    auth = d["_atom_site.auth_asym_id"]; ent = d["_atom_site.label_entity_id"]; grp = d["_atom_site.group_PDB"]
    seen, out = set(), {}
    for a, e, g in zip(auth, ent, grp):
        if g == "ATOM" and a not in seen:
            seen.add(a); out.setdefault(e, []).append(a)
    ids = [c.id for c in model]
    return {e: [c for c in cs if c in ids] for e, cs in out.items()}

def subunits(path, model):
    ents = chains_by_entity(path, model)
    (ea, a), (eb, b) = sorted(ents.items())[:2]   # entity 1 = alpha, 2 = beta in both entries
    assert len(a) == 2 and len(b) == 2, ents
    return {"alpha1": model[a[0]], "beta1": model[b[0]], "alpha2": model[a[1]], "beta2": model[b[1]]}

D, O = subunits("deoxy_4hhb.cif", deoxy), subunits("oxy_1hho_assembly1.cif", oxy)
print({k: v.id for k, v in D.items()}, {k: v.id for k, v in O.items()})

def ca(chain):
    return {r.id[1]: r["CA"] for r in chain if "CA" in r and r.id[0] == " "}

pairs = {k: (ca(D[k]), ca(O[k])) for k in D}
# Superimpose the oxy tetramer on deoxy using the alpha1-beta1 dimer only (the classic frame).
fixed, moving = [], []
for k in ("alpha1", "beta1"):
    d, o = pairs[k]
    for n in sorted(set(d) & set(o)):
        fixed.append(d[n]); moving.append(o[n])
sup = Superimposer(); sup.set_atoms(fixed, moving); sup.apply(list(oxy.get_atoms()))
print(f"alpha1beta1 core RMSD {sup.rms:.2f} A over {len(fixed)} CA")

# Quaternary rotation of alpha2beta2 after that superposition.
f2, m2 = [], []
for k in ("alpha2", "beta2"):
    d, o = pairs[k]
    for n in sorted(set(d) & set(o)):
        f2.append(d[n]); m2.append(o[n])
s2 = Superimposer(); s2.set_atoms(f2, m2)
rot = s2.rotran[0]
angle = float(np.degrees(np.arccos(np.clip((np.trace(rot) - 1) / 2, -1, 1))))

# alpha1 residues within 5 A of beta2 in deoxy: the alpha1beta2 interface.
ns = NeighborSearch([a for a in D["beta2"].get_atoms()])
iface = {r.id[1] for r in D["alpha1"] if r.id[0] == " " and any(ns.search(a.coord, 5.0) for a in r)}
rows = []
for k in D:
    d, o = pairs[k]
    for n in sorted(set(d) & set(o)):
        rows.append({"subunit": k, "residue": n, "resname": d[n].get_parent().get_resname(),
                     "displacement_A": round(float(np.linalg.norm(d[n].coord - o[n].coord)), 3),
                     "alpha1beta2_interface": k == "alpha1" and n in iface})
with open("residue_displacement.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
a1 = [r for r in rows if r["subunit"] == "alpha1"]
x = [r["displacement_A"] for r in a1 if r["alpha1beta2_interface"]]
y = [r["displacement_A"] for r in a1 if not r["alpha1beta2_interface"]]
u = stats.mannwhitneyu(x, y, alternative="greater")
io = PDBIO(); io.set_structure(oxy); io.save("oxy_superposed.pdb")
io.set_structure(deoxy); io.save("deoxy_reference.pdb")
m = {"core_rmsd_A": round(float(sup.rms), 3), "alpha2beta2_rotation_deg": round(angle, 2),
     "interface_residues": len(x), "alpha1_interface_median_A": round(float(np.median(x)), 3),
     "alpha1_other_median_A": round(float(np.median(y)), 3), "mannwhitney_p": float(u.pvalue)}
print("PLATO_METRICS " + json.dumps(m))
""",
    # Baldwin & Chothia (1979): alpha2beta2 turns ~12-15 degrees relative to alpha1beta1.
    lambda m: None
    if 9 <= m["alpha2beta2_rotation_deg"] <= 18 and m["interface_residues"] >= 10
    else f"quaternary rotation {m['alpha2beta2_rotation_deg']} deg outside 9-18",
)

# ---------------------------------------------------------------------------- expression
recipe(
    "expression",
    r"""set -euo pipefail
# DESeq2 from bioconda into the R env (binary, no compiler); airway is a pure data package.
micromamba install -y -n r -c conda-forge -c bioconda --channel-priority strict bioconductor-deseq2 >/dev/null
Rscript -e 'options(repos=BiocManager::repositories()); BiocManager::install("airway", ask=FALSE, update=FALSE)'
Rscript -e 'suppressMessages({library(DESeq2); library(airway)}); data(airway); cat(dim(airway), "\n")'
""",
    r'''import json, subprocess
r = r"""
suppressMessages({library(airway); library(DESeq2); library(clusterProfiler); library(org.Hs.eg.db)})
set.seed(as.integer(readLines("plato_seed.txt")))
data(airway)
dds <- DESeqDataSet(airway, design = ~ cell + dex)
dds$dex <- relevel(dds$dex, ref = "untrt")
dds <- DESeq(dds, quiet = TRUE)
res <- as.data.frame(results(dds, contrast = c("dex", "trt", "untrt"), alpha = 0.05))
res$gene_id <- rownames(res)
res$symbol <- mapIds(org.Hs.eg.db, res$gene_id, "SYMBOL", "ENSEMBL", multiVals = "first")
res <- res[!is.na(res$padj), c("gene_id", "symbol", "baseMean", "log2FoldChange", "lfcSE", "pvalue", "padj")]
write.csv(res[order(res$padj), ], "dex_differential_expression.csv", row.names = FALSE)
sig <- res$gene_id[res$padj < 0.05 & abs(res$log2FoldChange) > 1]
ego <- enrichGO(sig, OrgDb = org.Hs.eg.db, keyType = "ENSEMBL", ont = "BP", universe = res$gene_id, readable = TRUE)
eg <- as.data.frame(ego)
write.csv(eg, "go_enrichment.csv", row.names = FALSE)
known <- c("FKBP5", "TSC22D3", "PER1", "DUSP1", "KLF15", "ZBTB16")
up <- res$symbol[res$padj < 0.05 & res$log2FoldChange > 1]
cat(sprintf("PLATO_METRICS {\"tested\": %d, \"significant\": %d, \"known_up\": %d, \"go_terms\": %d}\n",
            nrow(res), length(sig), sum(known %in% up), nrow(eg)))
"""
open("deseq.R", "w").write(r)
out = subprocess.run(["Rscript", "deseq.R"], capture_output=True, text=True)
print(out.stdout); print(out.stderr[-3000:])
out.check_returncode()
''',
    # Himes et al. (2014): FKBP5, TSC22D3, PER1, DUSP1, KLF15 and ZBTB16 rise with dexamethasone.
    lambda m: None
    if m["known_up"] >= 5 and m["significant"] > 300 and m["go_terms"] > 0
    else "known glucocorticoid-response genes not recovered",
)

# ---------------------------------------------------------------------------- solubility
recipe(
    "solubility",
    r"""set -euo pipefail
python -m pip install -q rdkit==2025.3.6
curl -fsSL --retry 5 --retry-all-errors \
  https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/delaney-processed.csv -o delaney.csv
""",
    r"""import json
import numpy as np, pandas as pd
from rdkit import Chem, RDLogger
from rdkit.Chem import Crippen, Descriptors, AllChem
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.model_selection import train_test_split
RDLogger.DisableLog("rdApp.*")

seed = int(open("plato_seed.txt").read().strip() or 1)
df = pd.read_csv("delaney.csv")
y_col = "measured log solubility in mols per litre"
rows = []
for name, smi, y in zip(df["Compound ID"], df["smiles"], df[y_col]):
    m = Chem.MolFromSmiles(smi.strip())
    if m is None:
        continue
    heavy = m.GetNumHeavyAtoms()
    rows.append({"name": name, "smiles": smi.strip(), "logS": y, "logP": Crippen.MolLogP(m),
                 "MW": Descriptors.MolWt(m), "RB": Descriptors.NumRotatableBonds(m),
                 "AP": sum(a.GetIsAromatic() for a in m.GetAtoms()) / heavy})
d = pd.DataFrame(rows)
tr, te = train_test_split(d, test_size=0.2, random_state=seed)
out = {}
for label, cols in (("logP_only", ["logP"]), ("esol_4", ["logP", "MW", "RB", "AP"])):
    lr = LinearRegression().fit(tr[cols], tr["logS"])
    pred = lr.predict(te[cols])
    out[label] = {"r2": r2_score(te["logS"], pred), "rmse": mean_squared_error(te["logS"], pred) ** 0.5}
    te = te.assign(**{f"pred_{label}": pred})
# Paired bootstrap of the held-out R^2 gain.
rng = np.random.default_rng(seed)
gain = []
for _ in range(2000):
    i = rng.integers(0, len(te), len(te)); s = te.iloc[i]
    gain.append(r2_score(s["logS"], s["pred_esol_4"]) - r2_score(s["logS"], s["pred_logP_only"]))
lo, hi = np.percentile(gain, [2.5, 97.5])
te = te.assign(abs_error=(te["logS"] - te["pred_esol_4"]).abs()).sort_values("abs_error", ascending=False)
te.to_csv("heldout_predictions.csv", index=False)
w = Chem.SDWriter("largest_errors.sdf")
for _, r in te.head(8).iterrows():
    m = Chem.AddHs(Chem.MolFromSmiles(r["smiles"]))
    AllChem.EmbedMolecule(m, randomSeed=seed)
    m.SetProp("_Name", str(r["name"])); m.SetProp("abs_error", f"{r['abs_error']:.2f}")
    w.write(m)
w.close()
m = {"n": len(d), "r2_logP_only": round(out["logP_only"]["r2"], 3), "r2_esol_4": round(out["esol_4"]["r2"], 3),
     "rmse_esol_4": round(out["esol_4"]["rmse"], 3), "r2_gain_ci": [round(lo, 3), round(hi, 3)]}
print("PLATO_METRICS " + json.dumps(m))
""",
    # Delaney (2004): the four-descriptor model reaches R^2 ~0.7-0.8; logP alone is weaker.
    lambda m: None
    if m["n"] > 1000 and m["r2_esol_4"] > 0.65 and m["r2_esol_4"] > m["r2_logP_only"]
    else "ESOL descriptors did not beat logP alone",
)

# ---------------------------------------------------------------------------- supernovae
recipe(
    "supernovae",
    r"""set -euo pipefail
python -m pip install -q astropy
curl -fsSL --retry 5 --retry-all-errors \
  "https://raw.githubusercontent.com/PantheonPlusSH0ES/DataRelease/main/Pantheon%2B_Data/4_DISTANCES_AND_COVAR/Pantheon%2BSH0ES.dat" \
  -o pantheon_plus.dat
""",
    r"""import json
import numpy as np, pandas as pd
from scipy.optimize import minimize
from astropy.cosmology import FlatwCDM

d = pd.read_csv("pantheon_plus.dat", sep=r"\s+")
# Hubble-flow SNe only (calibrators excluded); diagonal errors, so the w interval is wider
# than the paper's full-covariance result.
d = d[(d["zHD"] > 0.01) & (d["IS_CALIBRATOR"] == 0)]
z, mu, err = d["zHD"].to_numpy(), d["MU_SH0ES"].to_numpy(), d["MU_SH0ES_ERR_DIAG"].to_numpy()

def chi2(p, z, mu, err):
    om, w = p
    if not (0.01 < om < 0.99 and -3 < w < 0):
        return 1e12
    model = FlatwCDM(H0=70, Om0=om, w0=w).distmod(z).value
    r = mu - model
    wt = 1 / err**2
    off = np.sum(r * wt) / np.sum(wt)      # absolute magnitude / H0 offset, marginalised analytically
    return float(np.sum(((r - off) / err) ** 2))

def fit(mask):
    res = minimize(chi2, [0.3, -1.0], args=(z[mask], mu[mask], err[mask]), method="Nelder-Mead")
    om, w = res.x
    # 1D profile for w: chi2 within +1 of the minimum.
    grid = np.linspace(w - 0.8, w + 0.8, 81)
    prof = [minimize(lambda o: chi2([o[0], g], z[mask], mu[mask], err[mask]), [om], method="Nelder-Mead").fun for g in grid]
    ok = grid[np.array(prof) <= res.fun + 1]
    return {"Om0": round(float(om), 3), "w": round(float(w), 3), "w_lo": round(float(ok.min()), 3),
            "w_hi": round(float(ok.max()), 3), "n": int(mask.sum()), "chi2_dof": round(res.fun / (mask.sum() - 3), 3)}

zmed = np.median(z)
out = {"all": fit(np.ones_like(z, bool)), "low_z": fit(z <= zmed), "high_z": fit(z > zmed)}
pd.DataFrame(out).T.to_csv("wcdm_fits.csv")
print(out)
m = {"n": out["all"]["n"], "w": out["all"]["w"], "w_interval": [out["all"]["w_lo"], out["all"]["w_hi"]],
     "Om0": out["all"]["Om0"], "chi2_dof": out["all"]["chi2_dof"]}
print("PLATO_METRICS " + json.dumps(m))
""",
    # Brout et al. (2022), SN only: w = -0.90 +0.14 -0.12 and Om0 ~ 0.4 with full covariance.
    lambda m: None
    if m["n"] > 1400 and -1.4 < m["w"] < -0.5 and m["w_interval"][0] < -0.8
    else f"w = {m['w']} implausible for Pantheon+",
)

# ---------------------------------------------------------------------------- statistics
recipe(
    "statistics",
    "",
    r"""import csv, json
import numpy as np
import statsmodels.api as sm

seed = int(open("plato_seed.txt").read().strip() or 1)
rng = np.random.default_rng(seed)
rows = []
for n in (20, 50, 100, 500):
    hit = {"classical": 0, "HC3": 0}
    reps = 1000
    for _ in range(reps):
        x = rng.uniform(0, 1, n)
        e = rng.normal(0, 0.2 + 2 * x**2)       # error spread grows with x
        y = 1 + 2 * x + e
        X = sm.add_constant(x)
        for kind, cov in (("classical", "nonrobust"), ("HC3", "HC3")):
            lo, hi = sm.OLS(y, X).fit(cov_type=cov).conf_int()[1]
            hit[kind] += lo <= 2 <= hi
    for kind, h in hit.items():
        p = h / reps
        rows.append({"n": n, "interval": kind, "coverage": p, "mc_se": round((p * (1 - p) / reps) ** 0.5, 4)})
with open("coverage.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
cov = {f"{r['interval']}_{r['n']}": r["coverage"] for r in rows}
print(rows)
print("PLATO_METRICS " + json.dumps(cov))
""",
    # Classical intervals under-cover under this heteroskedasticity; HC3 is close to nominal.
    lambda m: None
    if m["classical_500"] < 0.93 and m["HC3_500"] > 0.93
    else "classical vs HC3 coverage not separated",
)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default="example-checks")
    ap.add_argument("--only", help="comma-separated recipe names")
    ap.add_argument("--local", action="store_true", help="run on this host (PLATO_WORKSPACE_BACKEND=local)")
    args = ap.parse_args()
    if args.local:
        os.environ["PLATO_WORKSPACE_BACKEND"] = "local"
    elif not os.environ.get("E2B_API_KEY"):
        raise SystemExit("set E2B_API_KEY (or pass --local)")
    samples = _samples()
    rt, marker = samples._runtime(), samples.METRICS
    names = [n for n in (args.only.split(",") if args.only else RECIPES) if n in RECIPES]
    out = Path(args.out)

    async def one(name: str) -> dict:
        r = RECIPES[name]
        started = time.monotonic()
        res = await rt.run_recipe(
            rt.default_backend_factory(),
            code=r["code"],
            setup=r["setup"],
            inputs={"plato_seed.txt": b"1"},
            setup_seconds=1800,
            run_seconds=1800,
            metadata={"purpose": "example-checks", "recipe": name},
        )
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        for fname, data in res.files.items():
            (d / fname).write_bytes(data)
        line = next((l for l in res.stdout.splitlines()[::-1] if l.startswith(marker)), None)
        metrics = json.loads(line[len(marker) + 1 :]) if line else None
        why = "no metrics" if metrics is None else r["expect"](metrics)
        info = {
            "recipe": name,
            "ok": res.ok and why is None,
            "why": why,
            "exit_code": res.exit_code,
            "network_isolated": res.network_isolated,
            "seconds": round(time.monotonic() - started, 1),
            "run_seconds": getattr(res, "duration_seconds", None),
            "metrics": metrics,
            "files": {f: len(b) for f, b in sorted(res.files.items())},
            "stdout_tail": res.stdout[-2000:],
            "stderr_tail": res.stderr[-2000:],
        }
        (d / "manifest.json").write_text(json.dumps(info, indent=2))
        print(f"{'PASS' if info['ok'] else 'FAIL'} {name} in {info['seconds']}s: {metrics}", flush=True)
        return info

    results = await asyncio.gather(*(one(n) for n in names), return_exceptions=True)
    failed = 0
    for n, r in zip(names, results):
        if isinstance(r, BaseException):
            failed += 1
            print(f"FAIL {n}: {type(r).__name__}: {r}", flush=True)
        elif not r["ok"]:
            failed += 1
            print(f"  {n}: {r['why']}\n  stderr: {r['stderr_tail'][-800:]}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
