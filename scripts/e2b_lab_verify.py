#!/usr/bin/env python3
"""Verify every tool in the ``plato-lab`` E2B template with real runs on small data.

Each check runs a small but complete analysis whose correct answer is known in advance
(planted variants, a planted deletion, a planted repeat expansion, a tutorial GWAS hit,
a known peptide mass, bundled package example data) and passes only if the tool
recovers it. Public data comes from NCBI, the PLINK tutorial, the CNVkit repository and
package-bundled examples; public APIs (Ensembl VEP, Reactome, cBioPortal) are called
live.

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
  curl -fsSL --retry 3 "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id=NC_001416.1&rettype=fasta&retmode=text" -o lambda.fa
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
# PLINK 1.07 tutorial data (HapMap, 89 samples, 83,534 SNPs); the tutorial's top hit is rs2222162.
curl -fsSL --retry 3 https://zzz.bwh.harvard.edu/plink/hapmap1.zip -o hapmap1.zip
unzip -o -q hapmap1.zip
plink2 --pedmap hapmap1 --make-pgen --out hm > /dev/null
plink2 --pfile hm --maf 0.01 --glm allow-no-covars --out assoc > glm.log 2>&1 || { tail glm.log; exit 1; }
python - <<'EOF'
import glob, json
f = glob.glob("assoc*.glm.logistic*")[0]
rows = [l.rstrip("\n").split("\t") for l in open(f)]
h = rows[0]; ip, iid = h.index("P"), h.index("ID")
best = min((r for r in rows[1:] if r[ip] != "NA"), key=lambda r: float(r[ip]))
print("CHECK_RESULT", json.dumps({"pass": best[iid] == "rs2222162", "top_snp": best[iid], "p": float(best[ip]), "tested": len(rows) - 1}))
EOF
"""
)

check("cnvkit", ["cnvkit.py"], 600)(
    r"""
set -euo pipefail
mkdir -p ~/v/cnv && cd ~/v/cnv
curl -fsSL --retry 3 https://raw.githubusercontent.com/etal/cnvkit/v0.9.12/test/formats/amplicon.cnr -o amplicon.cnr
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
normal <- system.file("extdata", "example_normal_tiny.txt.gz", package = "PureCN")
tumor <- system.file("extdata", "example_tumor_tiny.txt.gz", package = "PureCN")
vcf <- system.file("extdata", "example.vcf.gz", package = "PureCN")
intervals <- system.file("extdata", "example_intervals_tiny.txt", package = "PureCN")
set.seed(123)
ret <- runAbsoluteCN(normal.coverage.file = normal, tumor.coverage.file = tumor, vcf.file = vcf,
                     genome = "hg19", sampleid = "Sample1", interval.file = intervals,
                     max.candidate.solutions = 1, max.ploidy = 4, test.purity = seq(0.3, 0.7, by = 0.05),
                     post.optimize = FALSE, plot.cnv = FALSE, verbose = FALSE)
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
hl.init(quiet=True, master="local[2]", spark_conf={"spark.driver.memory": "3g"})
mt = hl.balding_nichols_model(n_populations=3, n_samples=150, n_variants=2000, seed=1)
eig, scores, _ = hl.hwe_normalized_pca(mt.GT, k=2)
print("CHECK_RESULT", json.dumps({"pass": len(eig) == 2 and scores.count() == 150, "eigenvalues": [round(e, 3) for e in eig], "hail": hl.__version__}))
EOF
"""
)

check("spliceai_runtime", ["SpliceAI (runtime install)"], 2400, heavy=True)(
    r"""
set -euo pipefail
micromamba create -y -q -n spliceai -c conda-forge python=3.10 pip > /dev/null
/opt/conda/envs/spliceai/bin/python -m pip install -q spliceai tensorflow-cpu==2.15.1 'numpy<2'
mkdir -p ~/v/sai && cd ~/v/sai
[ -s chr21.fa ] || { curl -fsSL https://hgdownload.soe.ucsc.edu/goldenPath/hg38/chromosomes/chr21.fa.gz | gunzip > chr21.fa; }
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
