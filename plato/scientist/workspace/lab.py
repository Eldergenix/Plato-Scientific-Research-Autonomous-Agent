"""The ``plato-lab`` E2B template: a computational biology and document workstation.

Build it with ``python scripts/e2b_lab_template.py`` and verify every tool on small
public data with ``python scripts/e2b_lab_verify.py``. :data:`LAB_SUMMARY` is what
the research-engineer agent is told the template contains; keep it in step with
:func:`lab_template` and the verification script.

Layout:

* ``/opt/conda`` (conda-forge + bioconda, owned by ``user``): Python 3.12 scientific
  stack and the bioinformatics command-line tools. Agents add packages with
  ``micromamba install`` without sudo.
* ``/opt/conda/envs/<tool>``: tools whose dependencies conflict (GATK, Sniffles2, CNVkit,
  ExpansionHunter, and R 4.4 with Bioconductor), each exposed by a wrapper in
  ``/opt/conda/bin``.
* System: TeX Live (pdflatex, xelatex, biber, latexmk), ripgrep, unzip, pigz.
"""

from __future__ import annotations

import shlex

TEMPLATE_NAME = "plato-lab"

# Bioconda tools that conflict with each other (boost, libdeflate, R, Python pins) each
# get their own env; thin wrappers in /opt/conda/bin put them on PATH. The specs below
# were solved against conda-forge + bioconda (strict priority) before being pinned here.
CONDA_BASE = [
    "python=3.12",
    "numpy",
    "scipy",
    "pandas",
    "scikit-learn",
    "statsmodels",
    "matplotlib",
    "seaborn",
    "networkx",
    "pysam",
    "biopython",
    "requests",
    "openjdk=17",
    "pandoc>=3.1",
    "samtools",
    "bcftools",
    "htslib",
    "bwa-mem2",
    "minimap2",
    "bedtools",
    "plink2",
    "wgsim",
    "nextflow",
    # CPU build of PyTorch from conda-forge (E2B has no GPU); SigProfilerExtractor needs it.
    "pytorch=*=cpu*",
]
# env name -> (conda specs, pip packages, {name exposed on PATH: executable in the env})
CONDA_TOOL_ENVS: dict[str, tuple[list[str], list[str], dict[str, str]]] = {
    "gatk": (["gatk4"], [], {"gatk": "gatk"}),
    "sniffles": (["python=3.12", "sniffles>=2"], [], {"sniffles": "sniffles"}),
    "cnvkit": (["python=3.12", "cnvkit>=0.9.14"], [], {"cnvkit.py": "cnvkit.py"}),
    "expansionhunter": (
        ["expansionhunter"],
        [],
        {"ExpansionHunter": "ExpansionHunter"},
    ),
    "r": (
        [
            "r-base=4.4",
            "r-biocmanager",
            "bioconductor-clusterprofiler",
            "bioconductor-org.hs.eg.db",
            "bioconductor-dose",
            "bioconductor-msstats",
            "bioconductor-purecn",
        ],
        [],
        {"R": "R", "Rscript": "Rscript"},
    ),
    # AlphaPeptDeep pins numpy<2 and pandas<3, which the base stack has outgrown.
    "peptdeep": (
        ["python=3.11", "pytorch=*=cpu*", "numpy<2", "pandas<3", "pip"],
        ["peptdeep"],
        {"peptdeep": "peptdeep", "peptdeep-python": "python"},
    ),
}
PIP_BASE = ["pyopenms", "SigProfilerExtractor", "igv-reports"]

_PATH = "/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_MM = "micromamba"
_CHANNELS = "-c conda-forge -c bioconda --channel-priority strict"


def _wrapper_commands() -> list[str]:
    """Shell commands that write one exec wrapper per exposed executable."""
    cmds = []
    for env, (_, _, exes) in CONDA_TOOL_ENVS.items():
        for exposed, exe in exes.items():
            prefix = f"/opt/conda/envs/{env}/bin"
            # The env's own lib first: a manylinux wheel in the env (pip-installed torch
            # extensions) can otherwise bind the base image's older libstdc++ first.
            lib = f"/opt/conda/envs/{env}/lib"
            script = (
                f"#!/bin/sh\nPATH={prefix}:$PATH LD_LIBRARY_PATH={lib}${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}} "
                f'exec {prefix}/{exe} "$@"\n'
            )
            target = f"/opt/conda/bin/{exposed}"
            cmds.append(
                f"printf %s {shlex.quote(script)} > {target} && chmod +x {target}"
            )
    return cmds


BUILD_SMOKE_TESTS = [
    (
        "/opt/conda/bin/python -c 'import numpy, scipy, pandas, sklearn, statsmodels, matplotlib, "
        "seaborn, networkx, pysam, Bio, requests, torch, pyopenms, SigProfilerExtractor, igv_reports'"
    ),
    "peptdeep-python -c 'import peptdeep, torch'",
    (
        "Rscript -e 'suppressMessages({library(clusterProfiler); library(org.Hs.eg.db); "
        "library(DOSE); library(MSstats); library(PureCN)})'"
    ),
    (
        "samtools --version && bcftools --version && bwa-mem2 version && minimap2 --version "
        "&& bedtools --version && plink2 --version && wgsim 2>&1 | grep -q Usage"
    ),
    "gatk --version && sniffles --version && cnvkit.py version && ExpansionHunter --version",
    "pandoc --version && latexmk -v && xelatex --version && java -version",
]

LAB_SUMMARY = (
    "The sandbox is the plato-lab template (Linux, user 'user' with passwordless sudo, "
    "internet access while you work). Preinstalled: Python 3.12 with numpy, scipy, pandas, "
    "scikit-learn, statsmodels, matplotlib, seaborn, networkx, pysam, biopython; command-line "
    "tools samtools, bcftools, bgzip/tabix, bwa-mem2, minimap2, bedtools, plink2, gatk (GATK4, "
    "Java 17), sniffles (Sniffles2), cnvkit.py, ExpansionHunter, wgsim, nextflow, pandoc; R 4.4 "
    "(Rscript) with Bioconductor clusterProfiler, org.Hs.eg.db, DOSE, MSstats, PureCN; Python "
    "pyopenms, SigProfilerExtractor, igv-reports; AlphaPeptDeep in its own Python (run its scripts "
    "with peptdeep-python, or the peptdeep CLI); TeX Live "
    "with latexmk, xelatex and biber. Install anything else with install_packages (bioconda first "
    "for bioinformatics). Code that uses multiprocessing must live in a file with an "
    "if __name__ == '__main__' guard (spawned workers re-import it). There is no GPU. Public APIs such as Ensembl REST (VEP), Reactome "
    "AnalysisService, cBioPortal and NCBI E-utilities are reachable while you work, but not "
    "during the recorded run, so download what the experiment needs in setup."
)


def lab_template():
    """Return the E2B ``Template`` definition (requires the ``e2b`` SDK)."""
    from e2b import Template

    return (
        Template()
        .from_base_image()
        .apt_install(
            [
                "curl",
                "ca-certificates",
                "bzip2",
                "unzip",
                "pigz",
                "file",
                "ripgrep",
                "procps",
                "git",
                "make",
                "texlive-latex-base",
                "texlive-latex-recommended",
                "texlive-latex-extra",
                "texlive-fonts-recommended",
                "texlive-xetex",
                "texlive-bibtex-extra",
                "latexmk",
                "biber",
                "lmodern",
                "fonts-dejavu",
            ],
            no_install_recommends=True,
        )
        .run_cmd(
            [
                (
                    "curl -fsSL https://micro.mamba.pm/api/micromamba/linux-64/latest "
                    "| tar -xj -C /usr/local bin/micromamba"
                ),
                "mkdir -p /opt/conda/conda-meta && chown -R user:user /opt/conda",
            ],
            user="root",
        )
        .set_envs(
            {"MAMBA_ROOT_PREFIX": "/opt/conda", "PATH": _PATH, "MPLBACKEND": "Agg"}
        )
        .run_cmd(
            f"{_MM} install -y -q -n base {_CHANNELS} "
            + " ".join(f"'{p}'" for p in CONDA_BASE),
            user="user",
        )
        .run_cmd(
            [
                f"{_MM} create -y -q -n {env} {_CHANNELS} "
                + " ".join(f"'{p}'" for p in specs)
                for env, (specs, _, _) in CONDA_TOOL_ENVS.items()
            ]
            + [
                f"/opt/conda/envs/{env}/bin/python -m pip install --no-cache-dir -q "
                + " ".join(pips)
                for env, (_, pips, _) in CONDA_TOOL_ENVS.items()
                if pips
            ],
            user="user",
        )
        .run_cmd(_wrapper_commands(), user="user")
        .run_cmd(
            [
                "/opt/conda/bin/python -m pip install --no-cache-dir -q "
                + " ".join(PIP_BASE),
                f"{_MM} clean -y -a",
            ],
            user="user",
        )
        .run_cmd(
            [
                # Login shells reset PATH from /etc/profile; re-add the conda envs after it.
                (
                    f'printf \'export PATH="{_PATH}"\\nexport MAMBA_ROOT_PREFIX=/opt/conda\\n'
                    "export MPLBACKEND=Agg\\n' > /etc/profile.d/plato-lab.sh"
                ),
                "mkdir -p /home/user/work && chown user:user /home/user/work",
            ],
            user="root",
        )
        # Fail the build loudly if anything installed above does not load (a Bioconductor
        # data package whose post-link download failed installs "successfully" otherwise).
        .run_cmd(BUILD_SMOKE_TESTS, user="user")
        .set_workdir("/home/user/work")
        .set_user("user")
    )
