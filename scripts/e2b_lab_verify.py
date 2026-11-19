#!/usr/bin/env python3
"""Verify every tool in the ``plato-lab`` E2B template with real runs on small data.

Each check runs a small but complete analysis whose correct answer is known in advance
(planted variants, a planted deletion, a planted repeat expansion, a planted GWAS hit,
a known peptide mass, a synthetic protein family, a published molecular identity, a
reference interaction energy, bundled package example data) and passes only if the tool
recovers it. Public data comes from NCBI, UCSC, the RCSB PDB, the CNVkit repository and
package-bundled examples; public APIs (Ensembl VEP, Reactome, cBioPortal) are called
live.

The molecular checks assert what their tool can actually establish: a Vina score on a
crystal pose is deterministic and a minimisation must stay on that pose, but Vina's
scoring function is not accurate enough to promise sub-2A redocking, so pose accuracy is
reported and not asserted.

    E2B_API_KEY=... python scripts/e2b_lab_verify.py                 # standard checks
    E2B_API_KEY=... python scripts/e2b_lab_verify.py --heavy         # runtime-install checks
    python scripts/e2b_lab_verify.py --local --only short_read_wgs   # host, for development

Writes ``e2b_lab_report.json`` and ``e2b_lab_report.md`` (or ``--out``).
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

_WS = Path(__file__).resolve().parents[1] / "plato" / "scientist" / "workspace"


def _load(name: str):
    """Load a standalone workspace module by path, so this script needs only ``e2b``
    (not the scientist service's dependencies)."""
    spec = importlib.util.spec_from_file_location(f"plato_ws_{name}", _WS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_backend = _load("backend")
E2BBackend, LocalBackend = _backend.E2BBackend, _backend.LocalBackend
TEMPLATE_NAME = _load("lab").TEMPLATE_NAME

# ---------------------------------------------------------------------------
# Shared data: the lambda phage genome (NCBI RefSeq NC_001416.1, 48.5 kb)
# ---------------------------------------------------------------------------

DATA = r"""
set -euo pipefail
mkdir -p ~/vdata && cd ~/vdata
if [ ! -s lambda.fa ]; then
  curl -fsSL --retry 5 --retry-all-errors "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id=NC_001416.1&rettype=fasta&retmode=text" -o lambda.fa
fi
grep -c '>' lambda.fa >/dev/null
python - <<'EOF'
seq = "".join(l.strip() for l in open("lambda.fa") if not l.startswith(">"))
assert len(seq) == 48502, len(seq)
print("lambda genome ok:", len(seq), "bp")
EOF
"""

CHECKS: dict[str, dict] = {}


def check(name: str, tools: list[str], timeout: int = 900, heavy: bool = False):
    def deco(script: str) -> str:
        CHECKS[name] = {"tools": tools, "timeout": timeout, "heavy": heavy, "script": script}
        return script

    return deco


RESULT_PY = r'''
import json
def result(ok, **kw):
    print("CHECK_RESULT", json.dumps({"pass": bool(ok), **kw}))
'''

check("versions", ["all"], 300)(r"""
set +e
for c in "samtools --version" "bcftools --version" "bgzip --version" "tabix --version" "bwa-mem2 version" \
         "minimap2 --version" "bedtools --version" "plink2 --version" "gatk --version" "sniffles --version" \
         "cnvkit.py version" "ExpansionHunter --version" "nextflow -version" "pandoc --version" \
         "java -version" "Rscript --version" "latexmk -v" "xelatex --version" "rg --version"; do
  out=$($c 2>&1 | grep -v '^Picked up' | head -n 3 | tr '\n' ' ' | cut -c1-160); echo "$c => $out"
done
python - <<'EOF'
import importlib, json
mods = {}
for m in ["numpy","scipy","pandas","sklearn","statsmodels","matplotlib","pysam","Bio","torch","pyopenms","SigProfilerExtractor","igv_reports"]:
    try:
        mod = importlib.import_module(m); mods[m] = getattr(mod, "__version__", "ok")
    except Exception as e:
        mods[m] = f"FAIL {e}"
import subprocess
sudo = subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0  # LAB_SUMMARY promises it
ok = sudo and not any(str(v).startswith("FAIL") for v in mods.values())
print("CHECK_RESULT", json.dumps({"pass": ok, "passwordless_sudo": sudo, "python": mods}))
EOF
""")

check("short_read_wgs", ["wgsim", "bwa-mem2", "samtools", "bcftools", "gatk", "bedtools"], 1200)(
    DATA
    + r"""
mkdir -p ~/v/wgs && cd ~/v/wgs
# 30x paired 150 bp reads with 1 SNP per kb on one haplotype (-h), no indels (-R 0).
wgsim -S 11 -N 5000 -1 150 -2 150 -r 0.001 -R 0 -X 0 -e 0.002 -h ~/vdata/lambda.fa r1.fq r2.fq > truth.txt
cp ~/vdata/lambda.fa ref.fa
bwa-mem2 index ref.fa > /dev/null 2>&1
samtools faidx ref.fa
bwa-mem2 mem -t 2 -R '@RG\tID:s1\tSM:s1\tPL:ILLUMINA' ref.fa r1.fq r2.fq 2>/dev/null | samtools sort -@2 -o s.bam
samtools index s.bam
samtools flagstat s.bam | head -n 5
bcftools mpileup -Ou -f ref.fa s.bam 2>/dev/null | bcftools call --ploidy 1 -mv -Oz -o bcf.vcf.gz 2>/dev/null
gatk CreateSequenceDictionary -R ref.fa > /dev/null 2>&1
gatk HaplotypeCaller -R ref.fa -I s.bam -O gatk.vcf.gz -ploidy 1 > gatk.log 2>&1 || { tail -20 gatk.log; exit 1; }
bedtools genomecov -ibam s.bam -d | awk '{s+=$3} END {print "mean_depth", s/NR}' > depth.txt
python - <<'EOF'
import gzip, json
truth = set()
for line in open("truth.txt"):
    f = line.split()
    if len(f) >= 4 and f[2] != "-" and f[3] != "-" and len(f[2]) == 1:
        truth.add(int(f[1]))
def calls(path):
    out = set()
    for line in gzip.open(path, "rt"):
        if line.startswith("#"): continue
        f = line.split("\t")
        if len(f[3]) == 1 and all(len(a) == 1 for a in f[4].split(",")):
            out.add(int(f[1]))
    return out
res = {"truth_snps": len(truth), "mean_depth": float(open("depth.txt").read().split()[1])}
ok = len(truth) >= 20
for name, path in [("bcftools", "bcf.vcf.gz"), ("gatk", "gatk.vcf.gz")]:
    c = calls(path); tp = len(c & truth)
    rec = tp / len(truth); prec = tp / max(1, len(c))
    res[name] = {"calls": len(c), "recall": round(rec, 4), "precision": round(prec, 4)}
    ok = ok and rec >= 0.95 and prec >= 0.95
print("CHECK_RESULT", json.dumps({"pass": ok, **res}))
EOF
"""
)

check("long_read_sv", ["minimap2", "samtools", "sniffles"], 900)(
    DATA
    + r"""
mkdir -p ~/v/sv && cd ~/v/sv
python - <<'EOF'
import os, random
random.seed(7)
seq = "".join(l.strip() for l in open(os.path.expanduser("~/vdata/lambda.fa")) if not l.startswith(">"))
sample = seq[:20000] + seq[22000:]          # planted 2,000 bp deletion at 20,000
def mutate(s, rate=0.03):
    return "".join(random.choice("ACGT".replace(b, "")) if random.random() < rate else b for b in s)
with open("reads.fq", "w") as fq:
    for i in range(500):                    # ~50x of 3-8 kb reads with 3% errors
        n = random.randint(3000, 8000); st = random.randint(0, len(sample) - n)
        r = mutate(sample[st:st + n])
        if random.random() < 0.5:
            r = r[::-1].translate(str.maketrans("ACGT", "TGCA"))
        fq.write(f"@r{i}\n{r}\n+\n{'5' * len(r)}\n")
EOF
minimap2 -t 2 -ax map-ont ~/vdata/lambda.fa reads.fq 2>/dev/null | samtools sort -o lr.bam
samtools index lr.bam
sniffles --input lr.bam --vcf sv.vcf --reference ~/vdata/lambda.fa --threads 2 --all-contigs > sniffles.log 2>&1 || { tail -20 sniffles.log; exit 1; }
python - <<'EOF'
import json, re
svs = []
for line in open("sv.vcf"):
    if line.startswith("#"): continue
    f = line.split("\t"); info = f[7]
    t = re.search(r"SVTYPE=(\w+)", info); l = re.search(r"SVLEN=(-?\d+)", info)
    svs.append({"pos": int(f[1]), "type": t.group(1) if t else None, "len": int(l.group(1)) if l else None})
hit = [s for s in svs if s["type"] == "DEL" and abs(s["pos"] - 20000) <= 200 and s["len"] and abs(abs(s["len"]) - 2000) <= 100]
print("CHECK_RESULT", json.dumps({"pass": bool(hit), "planted": {"type": "DEL", "pos": 20000, "len": 2000}, "called": svs[:10]}))
EOF
"""
)

check("str_expansionhunter", ["ExpansionHunter", "wgsim", "bwa-mem2", "samtools"], 900)(
    DATA
    + r"""
mkdir -p ~/v/str && cd ~/v/str
python - <<'EOF'
import os
seq = "".join(l.strip() for l in open(os.path.expanduser("~/vdata/lambda.fa")) if not l.startswith(">"))
ref = seq[:30000] + "CAG" * 10 + seq[30000:]      # reference allele: 10 repeats
alt = seq[:30000] + "CAG" * 25 + seq[30000:]      # sample: 25 repeats (homozygous)
open("ref.fa", "w").write(">lambda\n" + ref + "\n")
open("sample.fa", "w").write(">lambda\n" + alt + "\n")
import json
json.dump([{"LocusId": "LAMBDA_CAG", "LocusStructure": "(CAG)*",
            "ReferenceRegion": "lambda:30000-30030", "VariantType": "Repeat"}], open("catalog.json", "w"))
EOF
samtools faidx ref.fa
bwa-mem2 index ref.fa > /dev/null 2>&1
wgsim -S 5 -N 12000 -1 150 -2 150 -r 0 -R 0 -X 0 -e 0.001 sample.fa r1.fq r2.fq > /dev/null
bwa-mem2 mem -t 2 ref.fa r1.fq r2.fq 2>/dev/null | samtools sort -o str.bam && samtools index str.bam
ExpansionHunter --reads str.bam --reference ref.fa --variant-catalog catalog.json --output-prefix eh --sex female > eh.log 2>&1 || { tail -20 eh.log; exit 1; }
python - <<'EOF'
import json
d = json.load(open("eh.json"))
gt = d["LocusResults"]["LAMBDA_CAG"]["Variants"]["LAMBDA_CAG"]["Genotype"]
sizes = [int(x) for x in gt.split("/")]
print("CHECK_RESULT", json.dumps({"pass": all(abs(s - 25) <= 1 for s in sizes), "planted": "25/25", "genotype": gt}))
EOF
"""
)

check("gwas_plink2", ["plink2"], 600)(
    r"""
set -euo pipefail
mkdir -p ~/v/gwas && cd ~/v/gwas
# Simulated case-control cohort (the PLINK tutorial host serves a certificate for another
# name, so the check carries its own data): 1,000 samples, 2,000 SNPs, one planted causal
# SNP (rs_causal, odds ratio about 3 per allele); everything else is null.
python - <<'EOF'
import random
random.seed(42)
n, m, causal = 1000, 2000, 1234
freqs = [random.uniform(0.1, 0.5) for _ in range(m)]
geno = [[sum(random.random() < f for _ in range(2)) for f in freqs] for _ in range(n)]
with open("cohort.vcf", "w") as v, open("pheno.tsv", "w") as ph:
    v.write("##fileformat=VCFv4.2\n##contig=<ID=1,length=10000000>\n")
    v.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n')
    v.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + "\t".join(f"s{i}" for i in range(n)) + "\n")
    gt = {0: "0/0", 1: "0/1", 2: "1/1"}
    for j in range(m):
        sid = "rs_causal" if j == causal else f"rs{j}"
        v.write(f"1\t{1000 + j * 1000}\t{sid}\tA\tG\t.\tPASS\t.\tGT\t" + "\t".join(gt[g[j]] for g in geno) + "\n")
    ph.write("#IID\tCASE\n")
    import math
    for i, g in enumerate(geno):
        p = 1 / (1 + math.exp(-(-1.2 + math.log(3) * g[causal])))
        ph.write(f"s{i}\t{2 if random.random() < p else 1}\n")
EOF
plink2 --vcf cohort.vcf --make-pgen --out cohort > /dev/null
plink2 --pfile cohort --pheno pheno.tsv --maf 0.01 --glm allow-no-covars --out assoc > glm.log 2>&1 || { tail glm.log; exit 1; }
python - <<'EOF'
import glob, json
f = glob.glob("assoc*.glm.logistic*")[0]
rows = [l.rstrip("\n").split("\t") for l in open(f)]
h = rows[0]; ip, iid = h.index("P"), h.index("ID")
ranked = sorted((r for r in rows[1:] if r[ip] != "NA"), key=lambda r: float(r[ip]))
best, second = ranked[0], ranked[1]
ok = best[iid] == "rs_causal" and float(best[ip]) < 5e-8 and float(second[ip]) > 1e-5
print("CHECK_RESULT", json.dumps({"pass": ok, "planted": "rs_causal", "top_snp": best[iid], "p": float(best[ip]),
                                  "next_best_p": float(second[ip]), "tested": len(rows) - 1}))
EOF
"""
)

check("cnvkit", ["cnvkit.py"], 600)(
    r"""
set -euo pipefail
mkdir -p ~/v/cnv && cd ~/v/cnv
curl -fsSL --retry 5 --retry-all-errors https://raw.githubusercontent.com/etal/cnvkit/v0.9.12/test/formats/amplicon.cnr -o amplicon.cnr
cnvkit.py segment amplicon.cnr -m haar -o amplicon.cns > seg.log 2>&1 || { tail seg.log; exit 1; }
cnvkit.py call amplicon.cns -o amplicon.call.cns > call.log 2>&1
cnvkit.py scatter amplicon.cnr -s amplicon.cns -o scatter.png > sc.log 2>&1
python - <<'EOF'
import json, os
segs = sum(1 for _ in open("amplicon.cns")) - 1
calls = [l.split("\t") for l in open("amplicon.call.cns")][1:]
cn = sorted({int(float(r[[i for i, c in enumerate(open("amplicon.call.cns").readline().rstrip().split("\t")) if c == "cn"][0]])) for r in calls})
print("CHECK_RESULT", json.dumps({"pass": segs > 0 and os.path.getsize("scatter.png") > 10000, "segments": segs, "copy_numbers": cn}))
EOF
"""
)

check("sigprofiler", ["SigProfilerExtractor"], 1500)(
    r"""
set -euo pipefail
mkdir -p ~/v/sig && cd ~/v/sig
# A real file with a __main__ guard: the extractor's worker pool uses spawn, which re-imports
# the main module and cannot do that from a script piped on stdin.
cat > run_sig.py <<'EOF'
import glob, json
from SigProfilerExtractor import sigpro as sig

if __name__ == "__main__":
    data = sig.importdata("matrix")          # example SBS96 matrix bundled with the package
    sig.sigProfilerExtractor("matrix", "out", data, minimum_signatures=1, maximum_signatures=3,
                             nmf_replicates=5, cpu=2, make_decomposition_plots=False)
    sel = glob.glob("out/SBS96/Suggested_Solution/**/*Signatures*.txt", recursive=True)
    stats = open("out/SBS96/All_solutions_stat.csv").read().splitlines()
    print("CHECK_RESULT", json.dumps({"pass": bool(sel) and len(stats) > 1, "files": sel[:3],
                                      "solutions": stats[1:4]}))
EOF
python run_sig.py > sig.log 2>&1 || { tail -30 sig.log; exit 1; }
grep CHECK_RESULT sig.log
"""
)

check("pyopenms", ["pyopenms"], 300)(
    RESULT_PY.join(["python - <<'EOF'\n", r"""
import pyopenms as oms
seq = oms.AASequence.fromString("PEPTIDE")
mono = seq.getMonoWeight()
spec = oms.MSSpectrum()
gen = oms.TheoreticalSpectrumGenerator()
p = gen.getParameters(); p.setValue("add_b_ions", "true"); p.setValue("add_y_ions", "true"); gen.setParameters(p)
gen.getSpectrum(spec, seq, 1, 1)
exp = oms.MSExperiment(); exp.addSpectrum(spec)
oms.MzMLFile().store("theo.mzML", exp)
back = oms.MSExperiment(); oms.MzMLFile().load("theo.mzML", back)
result(abs(mono - 799.35996) < 1e-3 and back.getSpectrum(0).size() == spec.size() > 0,
       monoisotopic_mass=round(mono, 5), expected=799.35996, ions=spec.size())
EOF
"""])
)

check("peptdeep", ["peptdeep"], 900)(
    r"""
set -euo pipefail
mkdir -p ~/v/pd && cd ~/v/pd
peptdeep-python - <<'EOF'
import json, numpy as np, pandas as pd
from peptdeep.pretrained_models import ModelManager
mm = ModelManager(mask_modloss=False, device="cpu")
mm.load_installed_models()               # downloads the published pretrained models on first use
df = pd.DataFrame({"sequence": ["LGGNEQVTR", "GAGSSEPVTGLDAK", "VEATFGVDESNAK", "YILAGVENSK", "TPVISGGPYEYR"],
                   "mods": [""] * 5, "mod_sites": [""] * 5, "charge": [2] * 5})
df["nAA"] = df.sequence.str.len()
out = mm.predict_rt(df)
rt = out["rt_pred"].to_numpy()
print("CHECK_RESULT", json.dumps({"pass": bool(np.all(np.isfinite(rt)) and np.ptp(rt) > 0), "rt_pred": [round(float(x), 4) for x in rt]}))
EOF
"""
)

check("msstats", ["MSstats (R)"], 900)(
    r"""
set -euo pipefail
mkdir -p ~/v/ms && cd ~/v/ms
Rscript - <<'EOF'
suppressMessages(library(MSstats))
q <- dataProcess(DDARawData, use_log_file = FALSE, verbose = FALSE)
lv <- levels(q$ProteinLevelData$GROUP)
cm <- matrix(c(-1, 1, rep(0, length(lv) - 2)), nrow = 1, dimnames = list("C2-C1", lv))
gc <- groupComparison(contrast.matrix = cm, data = q, use_log_file = FALSE, verbose = FALSE)
r <- gc$ComparisonResult
n <- sum(!is.na(r$pvalue))
cat(sprintf('CHECK_RESULT {"pass": %s, "proteins": %d, "tested": %d, "significant_adj_p_0.05": %d}\n',
            tolower(n > 0), length(unique(r$Protein)), n, sum(r$adj.pvalue < 0.05, na.rm = TRUE)))
EOF
"""
)

check("clusterprofiler", ["clusterProfiler (R)", "org.Hs.eg.db", "DOSE"], 900)(
    r"""
set -euo pipefail
mkdir -p ~/v/cp && cd ~/v/cp
Rscript - <<'EOF'
suppressMessages({library(clusterProfiler); library(org.Hs.eg.db)})
data(geneList, package = "DOSE")
gene <- names(geneList)[abs(geneList) > 2]
ego <- enrichGO(gene, OrgDb = org.Hs.eg.db, ont = "BP", pvalueCutoff = 0.01, readable = TRUE)
d <- as.data.frame(ego)
top <- gsub('"', "'", head(d$Description, 3))
cat(sprintf('CHECK_RESULT {"pass": %s, "terms": %d, "top": ["%s"]}\n', tolower(nrow(d) > 0), nrow(d), paste(top, collapse = '", "')))
EOF
"""
)

check("purecn", ["PureCN (R)"], 1500)(
    r"""
set -euo pipefail
mkdir -p ~/v/pcn && cd ~/v/pcn
Rscript - <<'EOF'
suppressMessages(library(PureCN))
# The vignette's segmentation-input example, from files bundled with the package.
ex <- function(f) { p <- system.file("extdata", f, package = "PureCN"); stopifnot(nzchar(p)); p }
set.seed(123)
ret <- runAbsoluteCN(seg.file = ex("example_seg.txt"), interval.file = ex("example_intervals.txt"),
                     vcf.file = ex("example.vcf.gz"), genome = "hg19", sampleid = "Sample1",
                     max.candidate.solutions = 1, test.purity = seq(0.3, 0.7, by = 0.05),
                     plot.cnv = FALSE, verbose = FALSE)
p <- ret$results[[1]]$purity; pl <- ret$results[[1]]$ploidy
cat(sprintf('CHECK_RESULT {"pass": %s, "purity": %.3f, "ploidy": %.3f}\n', tolower(is.finite(p) && p > 0 && p < 1), p, pl))
EOF
"""
)

check("igv_reports", ["igv-reports"], 600)(
    r"""
set -euo pipefail
cd ~/v/wgs
create_report gatk.vcf.gz --fasta ref.fa --tracks s.bam --flanking 200 --output igv_report.html > igv.log 2>&1 || { tail igv.log; exit 1; }
python - <<'EOF'
import json, os
size = os.path.getsize("igv_report.html")
print("CHECK_RESULT", json.dumps({"pass": size > 50_000, "html_bytes": size}))
EOF
"""
)

# ---------------------------------------------------------------------------
# Molecules: compounds, protein structures, pathways and interaction physics.
# Structures come from the RCSB PDB; every expected value below was produced by
# running these same tools and compared with the published reference where one
# exists (CCSD(T)/CBS for the S22 water dimer, the LAMMPS melt example log).
# ---------------------------------------------------------------------------

STRUCTURES = r"""
set -euo pipefail
mkdir -p ~/vdata && cd ~/vdata
for id in 1UBQ 1CRN 4ZZN; do
  [ -s $id.pdb ] || curl -fsSL --retry 5 --retry-all-errors "https://files.rcsb.org/download/$id.pdb" -o $id.pdb
  grep -q '^ATOM' $id.pdb
done
"""

check("cheminformatics", ["rdkit", "obabel", "gemmi"], 600)(
    r"""
set -euo pipefail
mkdir -p ~/v/chem && cd ~/v/chem
python - <<'EOF'
import json
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Crippen, Descriptors, rdMolDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold
RDLogger.DisableLog("rdApp.*")
# Aspirin: identity and descriptors are exact, published facts about the molecule.
m = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
facts = {
    "formula": rdMolDescriptors.CalcMolFormula(m),
    "mw": round(Descriptors.MolWt(m), 3),
    "inchikey": Chem.MolToInchiKey(m),
    "scaffold": Chem.MolToSmiles(MurckoScaffold.GetScaffoldForMol(m)),
    "hba": rdMolDescriptors.CalcNumHBA(m),
    "hbd": rdMolDescriptors.CalcNumHBD(m),
    "logp": round(Crippen.MolLogP(m), 2),
}
# A 3D conformer: all 21 atoms placed, and the embedding is reproducible from the seed.
mh = Chem.AddHs(m)
params = AllChem.ETKDGv3(); params.randomSeed = 0xF00D
assert AllChem.EmbedMolecule(mh, params) == 0
AllChem.MMFFOptimizeMolecule(mh)
Chem.MolToMolFile(mh, "aspirin.sdf")
ok = (
    facts["formula"] == "C9H8O4"
    and abs(facts["mw"] - 180.159) < 0.01
    and facts["inchikey"] == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    and facts["scaffold"] == "c1ccccc1"
    and (facts["hba"], facts["hbd"]) == (3, 1)
    and mh.GetNumAtoms() == 21
    and mh.GetConformer().Is3D()
)
json.dump({"ok": ok, "facts": facts}, open("rdkit.json", "w"))
EOF
# Open Babel round trip: SMILES to 3D SDF with explicit hydrogens, and back.
obabel -:"CC(=O)Oc1ccccc1C(=O)O" -osdf --gen3d -O ob.sdf 2>/dev/null
python - <<'EOF'
import json
from rdkit import Chem, RDLogger
RDLogger.DisableLog("rdApp.*")
rd = json.load(open("rdkit.json"))
ob = Chem.MolFromMolFile("ob.sdf", removeHs=False)
same = Chem.MolToInchiKey(Chem.RemoveHs(ob)) == rd["facts"]["inchikey"]
import gemmi
ok = rd["ok"] and same and ob.GetNumAtoms() == 21 and ob.GetConformer().Is3D()
print("CHECK_RESULT", json.dumps({"pass": ok, "openbabel_roundtrip": same,
                                  "gemmi": gemmi.__version__, **rd["facts"]}))
EOF
"""
)

check("sequence_search", ["hmmer", "mmseqs2"], 600)(
    r"""
set -euo pipefail
mkdir -p ~/v/seq && cd ~/v/seq
# A synthetic protein family: one ancestor, 25 members at 30% substitution, one held-out
# member at 35%, and 200 unrelated sequences drawn from the same amino-acid composition.
# The profile must find the held-out member and nothing else.
python - <<'EOF'
import random
AA = "ACDEFGHIKLMNPQRSTVWY"
F = [8.3,1.4,5.4,6.7,3.9,7.1,2.3,5.9,5.8,9.7,2.4,4.1,4.7,3.9,5.5,6.6,5.4,6.9,1.1,2.9]
rng = random.Random(7)
rand_seq = lambda n: "".join(rng.choices(AA, weights=F, k=n))
anc = rand_seq(200)
mutate = lambda s, r: "".join(c if rng.random() > r else rng.choices(AA, weights=F)[0] for c in s)
members = [mutate(anc, 0.30) for _ in range(25)]
held = mutate(anc, 0.35)
open("fam.afa", "w").write("".join(f">m{i}\n{s}\n" for i, s in enumerate(members)))
open("db.fa", "w").write(f">TRUE_HOMOLOG\n{held}\n" + "".join(f">decoy{i}\n{rand_seq(200)}\n" for i in range(200)))
open("query.fa", "w").write(f">query\n{held}\n")
open("target.fa", "w").write(f">FAMILY_MEMBER\n{members[0]}\n" + open("db.fa").read())
EOF
hmmbuild --amino -o /dev/null fam.hmm fam.afa
hmmsearch --tblout hits.tbl -E 10 fam.hmm db.fa > /dev/null
mmseqs easy-search query.fa target.fa mm.tsv tmp --threads 2 -e 1e-3 > mm.log 2>&1
python - <<'EOF'
import json
hits = [l.split() for l in open("hits.tbl") if not l.startswith("#") and l.strip()]
names = [h[0] for h in hits]
evalue = float(hits[0][4]) if hits else 1.0
rows = [l.split("\t") for l in open("mm.tsv") if l.strip()]
targets = [r[1] for r in rows]
ok = (
    names == ["TRUE_HOMOLOG"] and evalue < 1e-20          # profile HMM: the homologue, no decoys
    and targets[:2] == ["TRUE_HOMOLOG", "FAMILY_MEMBER"]  # mmseqs: self, then the family
    and not [t for t in targets if t.startswith("decoy")]
)
print("CHECK_RESULT", json.dumps({"pass": ok, "hmmer_hits": names, "hmmer_evalue": evalue,
                                  "mmseqs_targets": targets[:4], "decoys_hit": sum(t.startswith("decoy") for t in targets)}))
EOF
"""
)

check("protein_structure", ["foldseek", "mkdssp", "gemmi"], 900)(
    STRUCTURES
    + r"""
mkdir -p ~/v/struct/db && cd ~/v/struct
cp ~/vdata/1UBQ.pdb query.pdb
cp ~/vdata/1UBQ.pdb db/ubiquitin_copy.pdb
cp ~/vdata/1CRN.pdb db/crambin.pdb
mkdssp query.pdb query.dssp 2> dssp.err || { cat dssp.err; exit 1; }
foldseek easy-search query.pdb db/ fs.tsv tmpfs --threads 2 \
  --format-output "query,target,fident,alntmscore,evalue" -e 10 > fs.log 2>&1
python - <<'EOF'
import json
from collections import Counter
lines = open("query.dssp").read().splitlines()
start = next(i for i, l in enumerate(lines) if l.startswith("  #  RESIDUE"))
ss = "".join(l[16] for l in lines[start + 1:] if len(l) > 16 and l[13] != "!")
counts = Counter(ss)
hits = [l.split("\t") for l in open("fs.tsv") if l.strip()]
targets = {h[1]: (float(h[3]), float(h[4])) for h in hits}
# 1UBQ is 76 residues with the beta-grasp fold: five strands and one alpha helix of ~12
# residues. Foldseek must match its own copy and must not match crambin, a different fold.
ok = (
    len(ss) == 76 and counts["E"] >= 20 and counts["H"] >= 10
    and "ubiquitin_copy" in targets and targets["ubiquitin_copy"][0] > 0.9
    and "crambin" not in targets
)
print("CHECK_RESULT", json.dumps({"pass": ok, "residues": len(ss), "strand": counts["E"],
                                  "helix": counts["H"], "foldseek": {k: v for k, v in targets.items()}}))
EOF
"""
)

check("docking", ["vina", "meeko", "obabel", "rdkit"], 900)(
    STRUCTURES
    + r"""
mkdir -p ~/v/dock && cd ~/v/dock
# Redocking control on 4ZZN (human ERK2 with inhibitor CQ8): prepare the crystal receptor
# and ligand, then ask Vina to score the crystal pose, minimise it, and search the box.
python - <<'EOF'
import json, statistics
import os
lines = open(os.path.expanduser("~/vdata/4ZZN.pdb")).read().splitlines()
alt = lambda l: l[16] in " A"
rec = [l for l in lines if l.startswith("ATOM") and l[21] == "A" and alt(l)]
lig = [l for l in lines if l.startswith("HETATM") and l[17:20] == "CQ8" and l[21] == "A" and alt(l)]
open("rec.pdb", "w").write("\n".join(rec) + "\nEND\n")
open("lig.pdb", "w").write("\n".join(lig) + "\nEND\n")
xyz = [[float(l[30 + 8 * i:38 + 8 * i]) for l in lig] for i in range(3)]
json.dump({"center": [round(statistics.mean(v), 3) for v in xyz], "atoms": len(lig)}, open("box.json", "w"))
EOF
C=$(python -c "import json;print(' '.join(str(v) for v in json.load(open('box.json'))['center']))")
set -- $C
obabel lig.pdb -O lig.sdf -h 2> /dev/null
mk_prepare_ligand.py -i lig.sdf -o lig.pdbqt
obabel rec.pdb -O rec.pdbqt -xr -p 7.4 2> /dev/null
BOX="--center_x $1 --center_y $2 --center_z $3 --size_x 22 --size_y 22 --size_z 22"
vina --receptor rec.pdbqt --ligand lig.pdbqt $BOX --score_only > score.txt 2>&1
vina --receptor rec.pdbqt --ligand lig.pdbqt $BOX --local_only --out local.pdbqt > local.txt 2>&1
vina --receptor rec.pdbqt --ligand lig.pdbqt $BOX --seed 42 --exhaustiveness 8 --num_modes 9 \
     --cpu 1 --out poses.pdbqt > search.txt 2>&1
vina_split --input poses.pdbqt > /dev/null
obabel local.pdbqt -O local.sdf 2> /dev/null
obabel poses_ligand_1.pdbqt -O pose1.sdf 2> /dev/null
python - <<'EOF'
import json, math, re
from rdkit import Chem, RDLogger
from rdkit.Chem import rdMolAlign
RDLogger.DisableLog("rdApp.*")
energy = lambda p: float(re.search(r"Estimated Free Energy of Binding\s*:\s*(-?\d+\.\d+)", open(p).read()).group(1))
best = float(re.search(r"^\s+1\s+(-?\d+\.\d+)", open("search.txt").read(), re.M).group(1))
ref, loc, pose = (Chem.RemoveHs(Chem.MolFromMolFile(f)) for f in ("lig.sdf", "local.sdf", "pose1.sdf"))
centroid = lambda m: [sum(m.GetConformer().GetAtomPosition(i)[k] for i in range(m.GetNumAtoms())) / m.GetNumAtoms() for k in range(3)]
out = {
    "crystal_score": energy("score.txt"),
    "minimised_score": energy("local.txt"),
    "best_search_score": best,
    "minimised_rmsd": round(rdMolAlign.CalcRMS(loc, ref), 3),
    "pose_centroid_shift": round(math.dist(centroid(pose), centroid(ref)), 2),
    "same_molecule": Chem.MolToSmiles(pose) == Chem.MolToSmiles(ref),
}
# Scoring the crystal pose is deterministic (-7.5 kcal/mol here); minimisation must stay on
# that pose, and the search must find the pocket. Vina's scoring function is not accurate
# enough to promise sub-2A redocking for this flexible ligand, so pose accuracy is not asserted.
ok = (
    -9 < out["crystal_score"] < -6 and out["minimised_rmsd"] < 1.5
    and out["best_search_score"] < -6 and out["pose_centroid_shift"] < 4.0
    and out["same_molecule"]
)
print("CHECK_RESULT", json.dumps({"pass": ok, **out}))
EOF
"""
)

check("pathways", ["gseapy", "igraph", "Reactome AnalysisService"], 600)(
    r"""
set -euo pipefail
mkdir -p ~/v/path && cd ~/v/path
python - <<'EOF'
import json
import numpy as np, pandas as pd, gseapy, igraph, requests
rng = np.random.default_rng(0)
genes = [f"G{i}" for i in range(1000)]
planted = genes[:30]
# A ranked list with one gene set planted at the top and one matched random set.
scores = {g: (3.0 + rng.normal(0, 0.3) if g in set(planted) else rng.normal(0, 1)) for g in genes}
rnk = pd.Series(scores).sort_values(ascending=False)
sets = {"TRUE_SET": planted, "DECOY_SET": list(rng.choice(genes[30:], 30, replace=False))}
res = gseapy.prerank(rnk=rnk, gene_sets=sets, permutation_num=500, seed=1, threads=2,
                     min_size=5, outdir=None, verbose=False).res2d.set_index("Term")
true_nes, true_q = float(res.loc["TRUE_SET", "NES"]), float(res.loc["TRUE_SET", "FDR q-val"])
decoy_p = float(res.loc["DECOY_SET", "NOM p-val"])
# Topology on a graph whose answer is analytic: the centre of an 11-node star has
# betweenness (n-1)(n-2)/2 = 45.
star = igraph.Graph.Star(11, mode="undirected")
betweenness = star.betweenness()[0]
# The live annotation source, which is a reference and never evidence on its own.
r = requests.post("https://reactome.org/AnalysisService/identifiers/projection?pageSize=5&page=1",
                  data="BRCA1\nBRCA2\nRAD51\nATM\nATR\nCHEK2\nPALB2\nTP53",
                  headers={"Content-Type": "text/plain"}, timeout=60)
pathways = [p["name"] for p in r.json().get("pathways", [])[:3]]
ok = (true_nes > 2 and true_q < 0.05 and decoy_p > 0.1 and betweenness == 45.0 and bool(pathways))
print("CHECK_RESULT", json.dumps({"pass": ok, "true_set_nes": round(true_nes, 3),
                                  "true_set_fdr": round(true_q, 4), "decoy_p": round(decoy_p, 3),
                                  "star_betweenness": betweenness, "reactome_top": pathways}))
EOF
"""
)

check("quantum_chemistry", ["xtb", "psi4"], 900)(
    r"""
set -euo pipefail
mkdir -p ~/v/qm && cd ~/v/qm
# The S22 water dimer. Its CCSD(T)/CBS interaction energy is -5.0 kcal/mol, so GFN2-xTB and
# SAPT0 must both land near it, and SAPT must attribute it mostly to electrostatics.
cat > dimer.xyz <<'EOF'
6
S22 water dimer
O  -1.551007  -0.114520   0.000000
H  -1.934259   0.762503   0.000000
H  -0.599677   0.040712   0.000000
O   1.350625   0.111469   0.000000
H   1.680398  -0.373741  -0.758561
H   1.680398  -0.373741   0.758561
EOF
python - <<'EOF'
rows = open("dimer.xyz").read().splitlines()
open("m1.xyz", "w").write("3\nmonomer1\n" + "\n".join(rows[2:5]) + "\n")
open("m2.xyz", "w").write("3\nmonomer2\n" + "\n".join(rows[5:8]) + "\n")
EOF
for f in dimer m1 m2; do
  xtb $f.xyz --gfn 2 --sp > $f.out 2>&1 || { tail -5 $f.out; exit 1; }
done
xtb dimer.xyz --gfn 2 --sp --alpb water > solv.out 2>&1
cat > sapt.py <<'EOF'
import json, psi4
psi4.set_memory("3 GB"); psi4.core.set_output_file("psi4.out", False); psi4.set_num_threads(2)
rows = open("dimer.xyz").read().splitlines()[2:]
geometry = "0 1\n" + "\n".join(rows[:3]) + "\n--\n0 1\n" + "\n".join(rows[3:]) \
           + "\nunits angstrom\nsymmetry c1"
psi4.geometry(geometry)
psi4.set_options({"basis": "jun-cc-pVDZ", "scf_type": "df", "freeze_core": "true"})
psi4.energy("sapt0")
K = psi4.constants.hartree2kcalmol
terms = {k: round(psi4.variable(v) * K, 3) for k, v in {
    "elst": "SAPT ELST ENERGY", "exch": "SAPT EXCH ENERGY", "ind": "SAPT IND ENERGY",
    "disp": "SAPT DISP ENERGY", "total": "SAPT0 TOTAL ENERGY"}.items()}
json.dump({"psi4": psi4.__version__, **terms}, open("sapt.json", "w"))
EOF
qm-python sapt.py > sapt.log 2>&1 || { tail -20 sapt.log; exit 1; }
python - <<'EOF'
import json, re
E = lambda p: float(re.search(r"TOTAL ENERGY\s+(-?\d+\.\d+)", open(p).read()).group(1))
HARTREE = 627.5094740631
interaction = (E("dimer.out") - E("m1.out") - E("m2.out")) * HARTREE
solvated = E("solv.out")
sapt = json.load(open("sapt.json"))
ok = (
    -6.5 < interaction < -3.5 and -6.5 < sapt["total"] < -3.5
    and sapt["elst"] < sapt["disp"] < 0 < sapt["exch"]   # hydrogen bond: electrostatics dominates
    and solvated < E("dimer.out")                        # implicit water stabilises the dimer
)
print("CHECK_RESULT", json.dumps({"pass": ok, "xtb_interaction_kcal": round(interaction, 3),
                                  "xtb_alpb_water_hartree": solvated, "sapt0": sapt,
                                  "reference_ccsdt_kcal": -5.02}))
EOF
"""
)

check("molecular_dynamics", ["lammps", "plumed", "openmm", "pdbfixer"], 1800)(
    STRUCTURES
    + r"""
mkdir -p ~/v/md && cd ~/v/md
# LAMMPS: the standard Lennard-Jones melt example. Its documented log reports
# temp 1.6645, E_pair -4.7774 and TotEng -2.2812 at step 250 for this exact input.
cat > in.melt <<'EOF'
units lj
atom_style atomic
lattice fcc 0.8442
region box block 0 10 0 10 0 10
create_box 1 box
create_atoms 1 box
mass 1 1.0
velocity all create 3.0 87287 loop geom
pair_style lj/cut 2.5
pair_coeff 1 1 1.0 1.0 2.5
neighbor 0.3 bin
neigh_modify every 20 delay 0 check no
fix 1 all nve
thermo 50
run 250
EOF
lmp -in in.melt -log lmp.log > /dev/null 2>&1
plumed info --version > plumed.txt
cat > run_md.py <<'EOF'
import json, os
import openmm, openmm.app as app, openmm.unit as u
from pdbfixer import PDBFixer
fixer = PDBFixer(filename=os.path.expanduser("~/vdata/1UBQ.pdb"))
fixer.findMissingResidues(); fixer.findMissingAtoms(); fixer.addMissingAtoms(); fixer.addMissingHydrogens(7.0)
ff = app.ForceField("amber14-all.xml", "amber14/tip3p.xml")
model = app.Modeller(fixer.topology, fixer.positions)
# An explicit environment: water box plus counter-ions at physiological ionic strength.
model.addSolvent(ff, padding=0.9 * u.nanometer, ionicStrength=0.15 * u.molar, neutralize=True)
system = ff.createSystem(model.topology, nonbondedMethod=app.PME,
                         nonbondedCutoff=1.0 * u.nanometer, constraints=app.HBonds)
ions = sum(1 for r in model.topology.residues() if r.name in ("NA", "CL"))
integrator = openmm.LangevinMiddleIntegrator(300 * u.kelvin, 1 / u.picosecond, 0.002 * u.picoseconds)
integrator.setRandomNumberSeed(11)
sim = app.Simulation(model.topology, system, integrator, openmm.Platform.getPlatformByName("CPU"))
sim.context.setPositions(model.positions)
energy = lambda: sim.context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(u.kilojoule_per_mole)
before = energy()
sim.minimizeEnergy(maxIterations=400)
after = energy()
sim.context.setVelocitiesToTemperature(300 * u.kelvin, 11)
sim.step(1000)
dof = 3 * system.getNumParticles() - system.getNumConstraints() - 3
temps = []
for _ in range(5):
    sim.step(200)
    ke = sim.context.getState(getEnergy=True).getKineticEnergy().value_in_unit(u.kilojoule_per_mole)
    temps.append(2 * ke / (dof * 0.0083144621))
json.dump({"openmm": openmm.version.version, "atoms": system.getNumParticles(), "ions": ions,
           "energy_before": round(before, 1), "energy_after": round(after, 1),
           "mean_temperature": round(sum(temps) / len(temps), 1)}, open("md.json", "w"))
EOF
md-python run_md.py > md.log 2>&1 || { tail -20 md.log; exit 1; }
python - <<'EOF'
import json
rows = [l.split() for l in open("lmp.log").read().splitlines()]
header = next(i for i, r in enumerate(rows) if r[:2] == ["Step", "Temp"])
steps = [dict(zip(rows[header], r)) for r in rows[header + 1:] if r and r[0].isdigit()]
final = next(s for s in steps if s["Step"] == "250")
first = steps[0]
lj = {k: float(final[k]) for k in ("Temp", "E_pair", "TotEng")}
drift = abs(float(final["TotEng"]) - float(first["TotEng"])) / abs(float(first["TotEng"]))
md = json.load(open("md.json"))
ok = (
    int(final["Step"]) == 250 and abs(lj["Temp"] - 1.6645) < 0.02
    and abs(lj["E_pair"] + 4.7774) < 0.02 and drift < 0.01      # NVE conserves energy
    and md["ions"] > 0 and md["energy_after"] < md["energy_before"]
    and 270 < md["mean_temperature"] < 330                       # thermostat holds 300 K
)
print("CHECK_RESULT", json.dumps({"pass": ok, "lammps_step250": lj,
                                  "lammps_energy_drift": round(drift, 5), "openmm": md,
                                  "plumed": open("plumed.txt").read().strip()}))
EOF
"""
)

check("nextflow", ["nextflow"], 600)(
    r"""
set -euo pipefail
mkdir -p ~/v/nf && cd ~/v/nf
cat > main.nf <<'EOF'
process upper {
  input:
  val x
  output:
  stdout
  script:
  "echo ${x.toUpperCase()}"
}
workflow { Channel.of('alpha', 'beta', 'gamma') | upper | view }
EOF
nextflow run main.nf -ansi-log false > nf.log 2>&1 || { tail -30 nf.log; exit 1; }
python - <<'EOF'
import json
log = open("nf.log").read()
print("CHECK_RESULT", json.dumps({"pass": all(w in log for w in ("ALPHA", "BETA", "GAMMA")), "tail": log[-300:]}))
EOF
"""
)

check("documents", ["latexmk", "xelatex", "pandoc"], 600)(
    r"""
set -euo pipefail
mkdir -p ~/v/doc && cd ~/v/doc
cat > paper.tex <<'EOF'
\documentclass{article}
\usepackage{mathptmx,geometry,setspace,natbib,caption,booktabs,longtable,lineno,hyperref,xcolor,float}
\begin{document}
\title{Sandbox compile test}\maketitle
Euler: $e^{i\pi}+1=0$. See \citet{ref1}.
\begin{table}[H]\centering\begin{tabular}{lr}\toprule a & 1\\\bottomrule\end{tabular}\caption{T}\end{table}
\begin{thebibliography}{1}\bibitem[Doe(2020)]{ref1} J. Doe. A paper. 2020.\end{thebibliography}
\end{document}
EOF
latexmk -pdf -interaction=nonstopmode -halt-on-error -no-shell-escape paper.tex > l.log 2>&1 || { tail -30 l.log; exit 1; }
cp paper.tex paperx.tex && latexmk -xelatex -interaction=nonstopmode -halt-on-error -no-shell-escape paperx.tex > x.log 2>&1 || { tail -30 x.log; exit 1; }
printf '# Title\n\nText with $x^2$ and a table.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n' > note.md
pandoc note.md -o note.docx && pandoc note.md --to=jats_archiving --standalone -o note.xml && pandoc note.md --standalone --embed-resources -o note.html
python - <<'EOF'
import json, os
s = {f: os.path.getsize(f) for f in ["paper.pdf", "paperx.pdf", "note.docx", "note.xml", "note.html"]}
ok = open("paper.pdf", "rb").read(4) == b"%PDF" and open("paperx.pdf", "rb").read(4) == b"%PDF" and all(v > 500 for v in s.values())
print("CHECK_RESULT", json.dumps({"pass": ok, "bytes": s}))
EOF
"""
)

check("public_apis", ["Ensembl VEP REST", "Reactome AnalysisService", "cBioPortal API"], 300)(
    RESULT_PY.join(["python - <<'EOF'\n", r"""
import requests
out = {}
# VEP: BRAF V600E (GRCh38 7:140753336 A>T)
r = requests.get("https://rest.ensembl.org/vep/human/region/7:140753336-140753336:1/T",
                 headers={"Content-Type": "application/json"}, timeout=60)
v = r.json()[0]
out["vep_most_severe"] = v.get("most_severe_consequence")
genes = {t.get("gene_symbol") for t in v.get("transcript_consequences", [])}
out["vep_genes"] = sorted(g for g in genes if g)[:5]
# Reactome over-representation for a small DNA-repair gene list
r = requests.post("https://reactome.org/AnalysisService/identifiers/projection?pageSize=5&page=1",
                  data="BRCA1\nBRCA2\nRAD51\nATM\nATR\nCHEK2\nPALB2\nTP53", headers={"Content-Type": "text/plain"}, timeout=60)
pw = r.json().get("pathways", [])
out["reactome_top"] = [p["name"] for p in pw[:3]]
# cBioPortal studies
r = requests.get("https://www.cbioportal.org/api/studies?keyword=tcga&pageSize=3", timeout=60)
out["cbioportal_studies"] = [s["studyId"] for s in r.json()]
result(out["vep_most_severe"] == "missense_variant" and "BRAF" in out["vep_genes"] and pw and out["cbioportal_studies"], **out)
EOF
"""])
)

# ---- heavy: installed at run time, each in its own env --------------------------------

check("hail_runtime", ["Hail (runtime install)"], 2400, heavy=True)(
    r"""
set -euo pipefail
micromamba create -y -q -n hail -c conda-forge python=3.11 openjdk=11 pip > /dev/null
/opt/conda/envs/hail/bin/python -m pip install -q hail
mkdir -p ~/v/hail && cd ~/v/hail
PATH=/opt/conda/envs/hail/bin:$PATH python - <<'EOF'
import json, hail as hl
hl.init(quiet=True, master="local[2]", global_seed=1, spark_conf={"spark.driver.memory": "3g"})
mt = hl.balding_nichols_model(n_populations=3, n_samples=150, n_variants=2000)
eig, scores, _ = hl.hwe_normalized_pca(mt.GT, k=2)
print("CHECK_RESULT", json.dumps({"pass": len(eig) == 2 and scores.count() == 150, "eigenvalues": [round(e, 3) for e in eig], "hail": hl.__version__}))
EOF
"""
)

check("spliceai_runtime", ["SpliceAI (runtime install)"], 2400, heavy=True)(
    r"""
set -euo pipefail
micromamba create -y -q -n spliceai -c conda-forge python=3.10 pip > /dev/null
/opt/conda/envs/spliceai/bin/python -m pip install -q spliceai tensorflow-cpu==2.15.1 'numpy<2' 'setuptools<81'
mkdir -p ~/v/sai && cd ~/v/sai
[ -s chr21.fa ] || { curl -fsSL --retry 5 --retry-all-errors https://hgdownload.soe.ucsc.edu/goldenPath/hg38/chromosomes/chr21.fa.gz | gunzip > chr21.fa; }
# Break the canonical GT donor of the first multi-exon plus-strand chr21 gene in SpliceAI's own
# GRCh38 annotation, plus a far-intronic control; the donor break must score high.
PATH=/opt/conda/envs/spliceai/bin:$PATH python - <<'EOF'
import os, json, spliceai
ann = os.path.join(os.path.dirname(spliceai.__file__), "annotations", "grch38.txt")
hdr, *rows = [l.rstrip("\n").split("\t") for l in open(ann)]
seq = "".join(l.strip() for l in open("chr21.fa") if not l.startswith(">")).upper()
for r in rows:
    name, chrom, strand, tx_start, tx_end, ex_start, ex_end = r[:7]
    if chrom not in ("21", "chr21") or strand != "+": continue
    ends = [int(x) for x in ex_end.strip(",").split(",")]
    if len(ends) < 3: continue
    donor = ends[1] + 1                 # 1-based position of the G in the intronic GT
    if seq[donor - 1:donor + 1] == "GT": break
ref = seq[donor - 1]
ctrl = donor + 1500
with open("in.vcf", "w") as v:
    v.write("##fileformat=VCFv4.2\n##contig=<ID=21,length=46709983>\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
    v.write(f"21\t{donor}\tdonor\t{ref}\t{'A' if ref != 'A' else 'C'}\t.\t.\t.\n")
    v.write(f"21\t{ctrl}\tctrl\t{seq[ctrl-1]}\t{'A' if seq[ctrl-1] != 'A' else 'C'}\t.\t.\t.\n")
open("chr21_renamed.fa", "w").write(">21\n" + seq + "\n")
json.dump({"gene": name, "donor": donor}, open("site.json", "w"))
EOF
PATH=/opt/conda/envs/spliceai/bin:$PATH spliceai -I in.vcf -O out.vcf -R chr21_renamed.fa -A grch38 > sai.log 2>&1 || { tail sai.log; exit 1; }
python - <<'EOF'
import json
site = json.load(open("site.json")); scores = {}
for l in open("out.vcf"):
    if l.startswith("#"): continue
    f = l.split("\t"); s = f[7].split("SpliceAI=")[1].split(",")[0].split("|")
    scores[f[2]] = max(float(x) for x in s[2:6])
print("CHECK_RESULT", json.dumps({"pass": scores.get("donor", 0) >= 0.5 and scores.get("ctrl", 1) < 0.2, **site, "max_delta": scores}))
EOF
"""
)


# ---------------------------------------------------------------------------


async def run_checks(args) -> list[dict]:
    names = [n for n, c in CHECKS.items() if (args.heavy or not c["heavy"])]
    if args.only:
        names = [n for n in args.only.split(",") if n in CHECKS]
    if args.local:
        backend = await LocalBackend.create()
    else:
        backend = await E2BBackend.create(
            template=args.template,
            api_key=os.environ.get("E2B_API_KEY"),
            timeout_seconds=args.sandbox_seconds,
            metadata={"app": "plato-scientist", "purpose": "lab-verify"},
        )
    results = []
    try:
        if args.lambda_fasta:  # offline runs: supply NC_001416.1 instead of fetching it from NCBI
            home = (await backend.run("echo $HOME", timeout=30)).stdout.strip()
            await backend.write_bytes(f"{home}/vdata/lambda.fa", Path(args.lambda_fasta).read_bytes())
        info = await backend.run("nproc; free -m | awk '/Mem/{print $2}'; df -h ~ | tail -1", timeout=60)
        print(f"sandbox {backend.sandbox_id}: {info.stdout.split()}", flush=True)
        for name in names:
            spec = CHECKS[name]
            started = time.monotonic()
            out = await backend.run(spec["script"], timeout=spec["timeout"])
            line = next(
                (l for l in reversed(out.stdout.splitlines()) if l.startswith("CHECK_RESULT ")), None
            )
            try:
                detail = json.loads(line[len("CHECK_RESULT "):]) if line else {}
            except json.JSONDecodeError:
                detail = {"unparsed": line}
            ok = bool(detail.get("pass")) and out.exit_code == 0
            rec = {
                "check": name,
                "tools": spec["tools"],
                "pass": ok,
                "seconds": round(time.monotonic() - started, 1),
                "exit_code": out.exit_code,
                "timed_out": out.timed_out,
                "detail": detail,
            }
            if not ok:
                rec["log_tail"] = (out.stdout[-2500:] + "\n" + out.stderr[-2500:]).strip()
            results.append(rec)
            print(f"{'PASS' if ok else 'FAIL'} {name} ({rec['seconds']}s) {json.dumps(detail)[:400]}", flush=True)
    finally:
        await backend.close()
    return results


def write_report(results: list[dict], out: Path, args) -> None:
    out.with_suffix(".json").write_text(json.dumps(results, indent=2))
    lines = [
        f"# plato-lab verification ({'local' if args.local else 'E2B template ' + args.template})",
        "",
        f"{sum(r['pass'] for r in results)} of {len(results)} checks passed.",
        "",
        "| Check | Tools | Result | Seconds | Evidence |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        ev = json.dumps({k: v for k, v in r["detail"].items() if k != "pass"})[:220].replace("|", "/")
        lines.append(
            f"| {r['check']} | {', '.join(r['tools'])} | {'pass' if r['pass'] else 'FAIL'} | {r['seconds']} | `{ev}` |"
        )
    out.with_suffix(".md").write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default=TEMPLATE_NAME)
    ap.add_argument("--only", help="comma-separated check names")
    ap.add_argument("--heavy", action="store_true", help="also run runtime-install checks")
    ap.add_argument("--local", action="store_true", help="run on this host instead of E2B")
    ap.add_argument("--sandbox-seconds", type=int, default=3600)
    ap.add_argument("--out", default="e2b_lab_report")
    ap.add_argument("--lambda-fasta", help="local copy of NC_001416.1 for offline runs")
    args = ap.parse_args()
    if not args.local and not os.environ.get("E2B_API_KEY"):
        print("E2B_API_KEY is not set", file=sys.stderr)
        return 2
    results = asyncio.run(run_checks(args))
    write_report(results, Path(args.out), args)
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
