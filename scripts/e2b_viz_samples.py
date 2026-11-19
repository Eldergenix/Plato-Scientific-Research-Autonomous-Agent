#!/usr/bin/env python3
"""Produce real experiment outputs for the in-app data viewers on the ``plato-lab`` template.

Each recipe is a real analysis on public data, run exactly the way the scientist records
an experiment: ``setup.sh`` with the network on, then ``experiment.py`` offline, through
:func:`plato.scientist.workspace.runtime.run_recipe` (the production collector decides
which files come back). Outputs land in ``--out/<recipe>/`` with a ``manifest.json``.

    E2B_API_KEY=... python scripts/e2b_viz_samples.py --out viz-samples
    python scripts/e2b_viz_samples.py --only structures --local   # host run, for development

Recipes:

* ``structures``: ubiquitin (PDB 1UBQ) and haemoglobin (PDB 4HHB) from RCSB, cleaned and
  re-written with Biopython; radius of gyration and a Calpha contact table.
* ``ligands``: aspirin, ibuprofen and caffeine embedded in 3D and MMFF-optimised with RDKit
  (SDF + MOL), with a descriptor table.
* ``proteomics``: label-free quantification of ubiquitin interactors (DEP's UbiLength
  data, Zhang et al.), Welch t-tests with Benjamini-Hochberg control, volcano table + plot.
* ``pathways``: clusterProfiler GO enrichment of DOSE's breast-cancer gene list, and the
  KEGG cell-cycle pathway (hsa04110) as a SIF network and a JSON graph coloured by fold change.

Needs only ``pip install e2b==2.64.0`` (the workspace modules are loaded without the
scientist service's dependencies).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _runtime():
    """Import the workspace runtime without executing ``plato/__init__`` (heavy deps)."""
    for name, path in (
        ("plato", ROOT / "plato"),
        ("plato.scientist", ROOT / "plato" / "scientist"),
        ("plato.scientist.workspace", ROOT / "plato" / "scientist" / "workspace"),
        ("plato.scientist.guard", ROOT / "plato" / "scientist" / "guard"),
    ):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = [str(path)]
            sys.modules[name] = mod
    import importlib

    return importlib.import_module("plato.scientist.workspace.runtime")


METRICS = "PLATO_METRICS"

RECIPES: dict[str, dict[str, str]] = {}


def recipe(name: str, setup: str, code: str) -> None:
    RECIPES[name] = {"setup": setup, "code": code}


recipe(
    "structures",
    r"""set -euo pipefail
for id in 1UBQ 4HHB; do
  curl -fsSL --retry 5 --retry-all-errors "https://files.rcsb.org/download/${id}.pdb" -o "src_${id}.pdb"
done
grep -c '^ATOM' src_1UBQ.pdb
""",
    r'''import csv, json, math
from Bio.PDB import PDBParser, PDBIO, MMCIFIO, Select

class Protein(Select):
    def accept_residue(self, r):  # drop waters; keep ligands such as haem
        return r.get_resname() != "HOH"

parser = PDBParser(QUIET=True)
ubq = parser.get_structure("1UBQ", "src_1UBQ.pdb")
hb = parser.get_structure("4HHB", "src_4HHB.pdb")
io = PDBIO(); io.set_structure(ubq); io.save("ubiquitin_1ubq.pdb", Protein())
cif = MMCIFIO(); cif.set_structure(hb); cif.save("hemoglobin_4hhb.cif", Protein())

ca = [r["CA"] for r in ubq[0]["A"] if "CA" in r]
xyz = [a.coord for a in ca]
cx = [sum(p[i] for p in xyz) / len(xyz) for i in range(3)]
rg = math.sqrt(sum(sum((p[i] - cx[i]) ** 2 for i in range(3)) for p in xyz) / len(xyz))
rows, n = [], 0
for i, a in enumerate(ca):
    for j in range(i + 3, len(ca)):
        d = a - ca[j]
        if d < 8.0:
            n += 1
            rows.append([a.get_parent().id[1], ca[j].get_parent().id[1], round(float(d), 3)])
with open("ubiquitin_contacts.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["residue_i", "residue_j", "distance_A"]); w.writerows(rows)
print(f"1UBQ: {len(ca)} residues, Rg {rg:.2f} A, {n} Calpha contacts under 8 A")
print("PLATO_METRICS " + json.dumps({"radius_of_gyration": round(rg, 4), "contacts": n}))
''',
)

recipe(
    "ligands",
    r"""set -euo pipefail
python -m pip install -q rdkit==2025.3.6
python -c 'import rdkit; print(rdkit.__version__)'
""",
    r'''import csv, json
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, Crippen, rdMolDescriptors

seed = int(open("plato_seed.txt").read().strip() or 1)
smiles = {
    "aspirin": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "ibuprofen": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
    "caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
}
w = Chem.SDWriter("ligands.sdf")
rows = []
for name, smi in smiles.items():
    mol = Chem.AddHs(Chem.MolFromSmiles(smi))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    mol.SetProp("_Name", name)
    w.write(mol)
    if name == "caffeine":
        Chem.MolToMolFile(mol, "caffeine.mol")
    heavy = Chem.RemoveHs(mol)
    rows.append([name, smi, round(Descriptors.MolWt(heavy), 3), round(Crippen.MolLogP(heavy), 3),
                 round(rdMolDescriptors.CalcTPSA(heavy), 2), rdMolDescriptors.CalcNumHBD(heavy),
                 rdMolDescriptors.CalcNumHBA(heavy), rdMolDescriptors.CalcNumRotatableBonds(heavy)])
w.close()
with open("ligand_descriptors.csv", "w", newline="") as f:
    c = csv.writer(f); c.writerow(["name", "smiles", "mol_weight", "logP", "tpsa", "hbd", "hba", "rotatable_bonds"]); c.writerows(rows)
print("PLATO_METRICS " + json.dumps({"mean_mol_weight": round(sum(r[2] for r in rows) / len(rows), 3)}))
''',
)

recipe(
    "proteomics",
    r"""set -euo pipefail
curl -fsSL --retry 5 --retry-all-errors https://raw.githubusercontent.com/arnesmits/DEP/master/data/UbiLength.rda -o UbiLength.rda
Rscript -e 'load("UbiLength.rda"); write.csv(UbiLength, "ubilength_raw.csv", row.names = FALSE); cat(nrow(UbiLength), "proteins\n")'
""",
    r'''import json
import numpy as np, pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests
import matplotlib.pyplot as plt

raw = pd.read_csv("ubilength_raw.csv")
raw = raw[(raw.get("Reverse", "") != "+") & (raw.get("Potential.contaminant", "") != "+")]
ubi = [c for c in raw.columns if c.startswith("LFQ.intensity.Ubi4")]
ctrl = [c for c in raw.columns if c.startswith("LFQ.intensity.Ctrl")]
lfq = np.log2(raw[ubi + ctrl].replace(0, np.nan))
keep = lfq[ubi].notna().sum(axis=1).ge(2) & lfq[ctrl].notna().sum(axis=1).ge(2)
lfq, meta = lfq[keep], raw.loc[keep, ["Protein.IDs", "Gene.names"]]
t, p = stats.ttest_ind(lfq[ubi], lfq[ctrl], axis=1, equal_var=False, nan_policy="omit")
fc = lfq[ubi].mean(axis=1) - lfq[ctrl].mean(axis=1)
padj = multipletests(np.asarray(p), method="fdr_bh")[1]
out = pd.DataFrame({"protein": meta["Protein.IDs"].str.split(";").str[0], "gene": meta["Gene.names"].fillna("").str.split(";").str[0],
                    "log2FC": fc.round(4), "t": np.round(t, 4), "pvalue": p, "padj": padj,
                    "mean_log2_ubi4": lfq[ubi].mean(axis=1).round(3), "mean_log2_ctrl": lfq[ctrl].mean(axis=1).round(3)})
out = out.sort_values("pvalue")
out.to_csv("ubi4_vs_ctrl_differential.csv", index=False)
sig = (out.padj < 0.05) & (out.log2FC.abs() > 1)
fig, ax = plt.subplots(figsize=(6, 4.5), dpi=150)
ax.scatter(out.log2FC, -np.log10(out.pvalue), s=6, c=np.where(sig, "#d62728", "#999999"))
ax.set_xlabel("log2 fold change (Ubi4 / Ctrl)"); ax.set_ylabel("-log10 p"); ax.set_title("UbiLength: Ubi4 vs control")
fig.tight_layout(); fig.savefig("volcano.png")
print(f"{len(out)} proteins tested, {int(sig.sum())} significant (FDR 5%, |log2FC| > 1)")
print("PLATO_METRICS " + json.dumps({"n_significant": int(sig.sum()), "n_tested": int(len(out))}))
''',
)

recipe(
    "pathways",
    r"""set -euo pipefail
curl -fsSL --retry 5 --retry-all-errors https://rest.kegg.jp/get/hsa04110/kgml -o hsa04110.xml
Rscript -e 'suppressMessages({library(clusterProfiler); library(org.Hs.eg.db); library(DOSE)})
data(geneList, package = "DOSE")
write.csv(data.frame(entrez = names(geneList), logFC = as.numeric(geneList)), "genelist.csv", row.names = FALSE)
ids <- bitr(names(geneList), fromType = "ENTREZID", toType = "SYMBOL", OrgDb = org.Hs.eg.db)
write.csv(ids, "entrez_symbol.csv", row.names = FALSE)
cat(length(geneList), "genes\n")'
""",
    r'''import csv, json, subprocess, xml.etree.ElementTree as ET

# 1. GO enrichment (clusterProfiler, offline with org.Hs.eg.db)
r = subprocess.run(["Rscript", "-e", """
suppressMessages({library(clusterProfiler); library(org.Hs.eg.db); library(DOSE)})
data(geneList, package = "DOSE")
de <- names(geneList)[abs(geneList) > 2]
ego <- enrichGO(de, OrgDb = org.Hs.eg.db, ont = "BP", pvalueCutoff = 0.01, qvalueCutoff = 0.05, readable = TRUE)
res <- as.data.frame(ego)
write.csv(head(res[order(res$p.adjust), ], 40), "go_enrichment.csv", row.names = FALSE)
cat(nrow(res), "terms\n")
"""], capture_output=True, text=True, timeout=1200)
print(r.stdout.strip(), r.stderr.strip()[-500:])
r.check_returncode()

# 2. KEGG cell cycle as a network, nodes coloured by DOSE's log fold change
sym = {row["ENTREZID"]: row["SYMBOL"] for row in csv.DictReader(open("entrez_symbol.csv"))}
fc = {row["entrez"]: float(row["logFC"]) for row in csv.DictReader(open("genelist.csv"))}
root = ET.parse("hsa04110.xml").getroot()
entries = {}
for e in root.findall("entry"):
    if e.get("type") not in ("gene", "compound"):
        continue
    ids = [x.split(":")[1] for x in e.get("name").split() if ":" in x]
    g = e.find("graphics")
    label = (g.get("name") if g is not None else ids[0]).split(",")[0].rstrip(".")
    vals = [fc[i] for i in ids if i in fc]
    entries[e.get("id")] = {"id": label, "type": e.get("type"), "entrez": ids[:6],
                            "log2FC": round(sum(vals) / len(vals), 4) if vals else None}
edges, seen = [], set()
for rel in root.findall("relation"):
    a, b = entries.get(rel.get("entry1")), entries.get(rel.get("entry2"))
    if not a or not b or a["id"] == b["id"]:
        continue
    kinds = [s.get("name") for s in rel.findall("subtype")] or [rel.get("type")]
    kind = kinds[0].replace(" ", "_")
    key = (a["id"], kind, b["id"])
    if key not in seen:
        seen.add(key); edges.append({"source": a["id"], "target": b["id"], "interaction": kind})
nodes = {}
for e in entries.values():
    nodes.setdefault(e["id"], e)
used = {x for e in edges for x in (e["source"], e["target"])}
graph = {"name": root.get("title"), "source": "KEGG hsa04110",
         "nodes": [n for k, n in nodes.items() if k in used], "edges": edges}
json.dump(graph, open("kegg_cell_cycle.json", "w"), indent=1)
with open("kegg_cell_cycle.sif", "w") as f:
    for e in edges:
        f.write(f"{e['source']}\t{e['interaction']}\t{e['target']}\n")
terms = sum(1 for _ in csv.DictReader(open("go_enrichment.csv")))
print(f"KEGG {root.get('title')}: {len(graph['nodes'])} nodes, {len(edges)} edges; {terms} GO terms kept")
print("PLATO_METRICS " + json.dumps({"go_terms": terms, "pathway_edges": len(edges)}))
''',
)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="viz-samples")
    ap.add_argument("--only", default="", help="comma-separated recipe names")
    ap.add_argument("--local", action="store_true", help="run on this host (no isolation)")
    args = ap.parse_args()
    if args.local:
        os.environ["PLATO_WORKSPACE_BACKEND"] = "local"
    elif not os.environ.get("E2B_API_KEY"):
        raise SystemExit("set E2B_API_KEY (or pass --local)")
    rt = _runtime()
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
            metadata={"purpose": "viz-samples", "recipe": name},
        )
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        for fname, data in res.files.items():
            (d / fname).write_bytes(data)
        metrics = next((l[len(METRICS) + 1:] for l in res.stdout.splitlines()[::-1] if l.startswith(METRICS)), None)
        info = {
            "recipe": name,
            "ok": res.ok and metrics is not None,
            "exit_code": res.exit_code,
            "network_isolated": res.network_isolated,
            "seconds": round(time.monotonic() - started, 1),
            "metrics": json.loads(metrics) if metrics else None,
            "files": {f: len(b) for f, b in sorted(res.files.items())},
            "stdout_tail": res.stdout[-1500:],
            "stderr_tail": res.stderr[-1500:],
        }
        (d / "manifest.json").write_text(json.dumps(info, indent=2))
        print(f"{'PASS' if info['ok'] else 'FAIL'} {name} in {info['seconds']}s: {info['files']}", flush=True)
        return info

    results = await asyncio.gather(*(one(n) for n in names), return_exceptions=True)
    failed = 0
    for n, r in zip(names, results):
        if isinstance(r, BaseException):
            failed += 1
            print(f"FAIL {n}: {type(r).__name__}: {r}", flush=True)
        elif not r["ok"]:
            failed += 1
            print(f"  {n} stderr: {r['stderr_tail'][-600:]}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
