"""The ``plato-lab`` E2B template: a computational biology and document workstation.

Build it with ``python scripts/e2b_lab_template.py`` and verify every tool on small
public data with ``python scripts/e2b_lab_verify.py``. :data:`LAB_SUMMARY` is what
the research-engineer agent is told the template contains; keep it in step with
:func:`lab_template` and the verification script.

Layout:

* ``/opt/conda`` (conda-forge + bioconda, owned by ``user``): Python 3.12 scientific
  stack, cheminformatics (RDKit, Open Babel), the bioinformatics and structure
  command-line tools (HMMER, Foldseek, MMseqs2, DSSP) and pathway analysis
  (gseapy, igraph). Agents add packages with ``micromamba install`` without sudo.
* ``/opt/conda/envs/<tool>``: tools whose dependencies conflict (GATK, Sniffles2, CNVkit,
  ExpansionHunter, R 4.4 with Bioconductor, AutoDock Vina docking, LAMMPS/OpenMM
  molecular dynamics, and xtb/Psi4 quantum chemistry), each exposed by a wrapper in
  ``/opt/conda/bin``.
* System: TeX Live (pdflatex, xelatex, biber, latexmk), ripgrep, unzip, pigz.

Notes on the molecular tools, each found while verifying them:

* The wrapper pythons (``dock-python``, ``md-python``, ``qm-python``) are the only way to
  reach OpenMM, Psi4, Meeko and the Vina bindings: the recorded ``experiment.py`` runs
  under the base interpreter, which cannot import them. The wrapper sets the env's own
  ``lib`` first, which Psi4 needs for its MKL build.
* LAMMPS is pinned to a ``cpu_py312*nompi*`` build: the CUDA builds are four times the
  size for a sandbox with no GPU, and one sandbox is one machine, so MPI buys nothing.
  The build number is pinned too, because the GCC 15 rebuilds need a newer glibc than the
  base image has; see the comment on the ``md`` env.
* RDKit lives in base, so nothing should ``pip install rdkit`` on top of it: the wheel
  shadows the conda package with a second, differently built copy.
* ``mkdssp`` 4.x tries mmCIF first and prints a parse error to stderr before falling back
  to PDB. It still exits 0 and writes the classic DSSP output; do not treat that line as
  a failure.
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
    # Cheminformatics: compound parsing, descriptors, scaffolds, conformers, format
    # conversion. RDKit is in base so every experiment can import it without a setup step.
    "rdkit",
    "openbabel",
    # Structure files (mmCIF/PDB) without the Biopython PDB parser's gaps.
    "gemmi",
    # Sequence and structure search: profile HMMs, fast sequence search, structural
    # alignment, and secondary structure (mkdssp).
    "hmmer",
    "mmseqs2",
    "foldseek",
    "dssp",
    # Pathways: over-representation and permutation-based GSEA, plus graph topology.
    "gseapy",
    "python-igraph",
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
    # Docking. Vina's Boost build pins an older librdkit than base carries, and Meeko
    # follows Vina's RDKit, so ligand preparation lives beside it in this env.
    "dock": (
        ["python=3.12", "numpy", "rdkit", "vina", "meeko", "openbabel"],
        [],
        {
            "vina": "vina",
            "vina_split": "vina_split",
            "mk_prepare_ligand.py": "mk_prepare_ligand.py",
            "mk_prepare_receptor.py": "mk_prepare_receptor.py",
            "mk_export.py": "mk_export.py",
            "dock-python": "python",
        },
    ),
    # Molecular dynamics. The CPU, no-MPI LAMMPS build (E2B has no GPU and one sandbox is
    # one machine) is a quarter the size of the CUDA builds; PLUMED comes with it for
    # free-energy methods. OpenMM covers biomolecular force fields and explicit solvent.
    #
    # The build number is pinned, not just the variant. conda-forge rebuilt LAMMPS
    # 2025.07.22 against GCC 15 from build 4 on (``libgcc >=15``), and GCC 15 emits the
    # ISO C23 symbols (``__isoc23_strtol`` and friends) that glibc only exports from
    # GLIBC_2.38. The E2B base image is Debian 12 with glibc 2.36, where those builds
    # fail to load at all: ``lmp: /lib/x86_64-linux-gnu/libm.so.6: version 'GLIBC_2.38'
    # not found``. Build 3 is the same LAMMPS version from the GCC 14 toolchain and needs
    # no symbol above GLIBC_2.34. Only move this pin forward after checking the new build
    # with ``readelf -V`` (or a sandbox), not because a newer one exists.
    "md": (
        [
            "python=3.12",
            "numpy",
            "scipy",
            "lammps=2025.07.22=cpu_py312*nompi_3",
            "openmm",
            "mdanalysis",
            "parmed",
            "pdbfixer",
        ],
        [],
        {
            "lmp": "lmp",
            "plumed": "plumed",
            "md-python": "python",
        },
    ),
    # Quantum chemistry: GFN2-xTB for semi-empirical energies, geometries and implicit
    # solvation; Psi4 for ab initio energies and SAPT interaction-energy decomposition.
    "qm": (
        ["python=3.12", "numpy", "xtb", "psi4"],
        [],
        {"xtb": "xtb", "qm-python": "python"},
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
# Emptying the package cache is what keeps the build on disk. micromamba keeps every
# downloaded tarball and its extracted copy under ``/opt/conda/pkgs``; measured on the
# ``dock`` env (236 MB of tarballs) the cache plus the env is 2,464 MB and the env alone
# is 1,223 MB, so the cache is roughly half of each env's footprint and it accumulates.
# Creating the nine envs in one step without clearing it needs about 3.6 GB of tarballs
# and their extracted copies live at once, which overflowed the build disk.
_CLEAN = f"{_MM} clean -y -a"


def _env_commands(env: str) -> list[str]:
    """Create one tool env, add its pip packages, then empty the package cache.

    One step per env, each ending in a clean, holds peak disk to a single env's cache
    instead of all nine, and lets a failed build resume from the last env that worked
    rather than rebuilding every one of them.
    """
    specs, pips, _ = CONDA_TOOL_ENVS[env]
    commands = [
        f"{_MM} create -y -q -n {env} {_CHANNELS} " + " ".join(f"'{p}'" for p in specs)
    ]
    if pips:
        commands.append(
            f"/opt/conda/envs/{env}/bin/python -m pip install --no-cache-dir -q "
            + " ".join(pips)
        )
    return [*commands, _CLEAN]


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
        "seaborn, networkx, pysam, Bio, requests, torch, pyopenms, SigProfilerExtractor, igv_reports, "
        "rdkit, gemmi, gseapy, igraph'"
    ),
    (
        "obabel -:'CC(=O)Oc1ccccc1C(=O)O' -osmi 2>/dev/null | grep -q . "
        "&& hmmbuild -h > /dev/null && mmseqs version && foldseek version && mkdssp --version"
    ),
    # Each extra env runs its own entry point: docking, MD and quantum chemistry.
    (
        "vina --version && vina_split --help > /dev/null && "
        "dock-python -c 'import meeko, rdkit, vina; print(vina.__file__)'"
    ),
    (
        "lmp -h > /dev/null && plumed info --version > /dev/null && "
        "md-python -c 'import openmm, MDAnalysis, pdbfixer, parmed; "
        'openmm.Platform.getPlatformByName("CPU")\''
    ),
    "xtb --version && qm-python -c 'import psi4; print(psi4.__version__)'",
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
    "with peptdeep-python, or the peptdeep CLI); "
    "chemistry and structure: rdkit, gemmi, obabel (Open Babel), hmmer (hmmbuild/hmmsearch/"
    "phmmer/jackhmmer), mmseqs, foldseek, mkdssp, and gseapy + igraph for enrichment and "
    "network topology; docking: vina (AutoDock Vina 1.2), vina_split and Meeko's "
    "mk_prepare_ligand.py / mk_prepare_receptor.py / mk_export.py, with dock-python for the "
    "Vina and Meeko "
    "Python APIs; molecular dynamics: lmp (LAMMPS, CPU, no MPI), plumed, and md-python for "
    "OpenMM, MDAnalysis, ParmEd and PDBFixer (explicit solvent, ions at a chosen ionic "
    "strength, thermostats and barostats); quantum chemistry: xtb (GFN2-xTB energies, "
    "geometry optimisation, ALPB/GBSA implicit solvents) and qm-python for Psi4 1.11 "
    "(SCF/DFT/MP2 and SAPT interaction-energy decomposition into electrostatics, exchange, "
    "induction and dispersion). TeX Live "
    "with latexmk, xelatex and biber. Install anything else with install_packages (bioconda first "
    "for bioinformatics). experiment.py runs under the base Python, which has rdkit, gemmi, "
    "gseapy and igraph but not openmm, psi4, meeko or the Vina bindings: reach those through "
    "the command-line names above (subprocess, e.g. ['md-python', 'run_md.py']), writing the "
    "helper script beside experiment.py. Code that uses multiprocessing must live in a file "
    "with an if __name__ == '__main__' guard (spawned workers re-import it). There is no GPU, "
    "so keep simulations small: a few thousand atoms, picoseconds not nanoseconds, semi-empirical "
    "or small-basis quantum chemistry. Public APIs such as Ensembl REST (VEP), Reactome "
    "AnalysisService, cBioPortal, NCBI E-utilities, RCSB PDB (files.rcsb.org), UniProt, the "
    "AlphaFold DB, PubChem PUG-REST, ChEMBL, KEGG REST, STRING and InterPro are reachable while "
    "you work, but not during the recorded run, so download what the experiment needs in setup."
)


def lab_template():
    """Return the E2B ``Template`` definition (requires the ``e2b`` SDK)."""
    from e2b import Template

    template = (
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
            [
                f"{_MM} install -y -q -n base {_CHANNELS} "
                + " ".join(f"'{p}'" for p in CONDA_BASE),
                _CLEAN,
            ],
            user="user",
        )
    )
    # One build step per tool env, so the package cache is emptied between them.
    for env in CONDA_TOOL_ENVS:
        template = template.run_cmd(_env_commands(env), user="user")
    return (
        template.run_cmd(_wrapper_commands(), user="user")
        .run_cmd(
            [
                "/opt/conda/bin/python -m pip install --no-cache-dir -q "
                + " ".join(PIP_BASE),
                _CLEAN,
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
