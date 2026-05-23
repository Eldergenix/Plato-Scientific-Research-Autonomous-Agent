"""Executable scientific-analysis helpers for agent workflows.

The functions in this module are deliberately deterministic and artifact
oriented. They return publication-ready Markdown/LaTeX snippets, structured
tables, reproducibility metadata, and optional plot artifacts so downstream
agents can carry real calculations into Methods and Results sections instead
of paraphrasing unverifiable claims.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


ScientificOperation = Literal[
    "formula_mass",
    "harmonic_oscillator",
    "linear_regression",
    "single_cell_qc",
    "quantum_pauli",
    "publication_plot",
]


class ScientificAnalysisInput(BaseModel):
    """Input schema for ``run_scientific_analysis``."""

    operation: ScientificOperation
    data: dict[str, Any] = Field(default_factory=dict)
    output_dir: str | None = Field(
        default=None,
        description="Optional directory for generated CSV/PNG/HTML artifacts.",
    )
    random_seed: int = 1729


class ScientificArtifact(BaseModel):
    path: str
    kind: str
    description: str


class ScientificAnalysisResult(BaseModel):
    operation: ScientificOperation
    markdown: str
    latex: str
    tables: list[dict[str, Any]] = Field(default_factory=list)
    values: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ScientificArtifact] = Field(default_factory=list)
    reproducibility: dict[str, Any] = Field(default_factory=dict)
    checks: list[dict[str, Any]] = Field(default_factory=list)


def run_scientific_analysis(
    payload: ScientificAnalysisInput,
) -> ScientificAnalysisResult:
    """Execute one deterministic scientific calculation or plotting workflow."""
    operations = {
        "formula_mass": _formula_mass,
        "harmonic_oscillator": _harmonic_oscillator,
        "linear_regression": _linear_regression,
        "single_cell_qc": _single_cell_qc,
        "quantum_pauli": _quantum_pauli,
        "publication_plot": _publication_plot,
    }
    return operations[payload.operation](payload)


def _artifact_dir(payload: ScientificAnalysisInput) -> Path | None:
    if not payload.output_dir:
        return None
    base = Path(payload.output_dir)
    digest = _hash_payload(payload.data)[:10]
    path = base / "scientific_analysis_artifacts" / f"{payload.operation}_{digest}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _base_reproducibility(payload: ScientificAnalysisInput) -> dict[str, Any]:
    return {
        "operation": payload.operation,
        "random_seed": payload.random_seed,
        "input_sha256": _hash_payload(payload.data),
        "optional_engines": {
            "plotly": _module_available("plotly"),
            "statsmodels": _module_available("statsmodels"),
            "scanpy": _module_available("scanpy"),
            "qutip": _module_available("qutip"),
            "chempy": _module_available("chempy"),
            "openbabel": _module_available("openbabel"),
        },
    }


def _hash_payload(data: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _formula_mass(payload: ScientificAnalysisInput) -> ScientificAnalysisResult:
    import pandas as pd

    formula = str(payload.data.get("formula") or "C8H10N4O2")
    counts = _parse_formula(formula)
    missing = sorted(set(counts) - set(_ATOMIC_WEIGHTS))
    if missing:
        raise ValueError(f"Unsupported elements in formula {formula!r}: {missing}")

    rows: list[dict[str, Any]] = []
    molar_mass = 0.0
    for element, count in sorted(counts.items()):
        mass = _ATOMIC_WEIGHTS[element] * count
        molar_mass += mass
        rows.append(
            {
                "element": element,
                "count": count,
                "atomic_weight_g_mol": _ATOMIC_WEIGHTS[element],
                "mass_contribution_g_mol": mass,
            }
        )
    for row in rows:
        row["mass_fraction"] = row["mass_contribution_g_mol"] / molar_mass

    equation_terms = " + ".join(f"{row['count']}\\,{row['element']}" for row in rows)
    markdown = (
        f"Formula mass for `{formula}` is **{molar_mass:.6f} g/mol**. "
        "The calculation sums each atom count multiplied by its standard "
        "atomic weight."
    )
    latex = (
        "\\subsubsection{Formula mass}\n"
        f"For ${formula}$, the atom-count expression is ${equation_terms}$. "
        f"The molar mass is $M = \\sum_i n_i A_i = {molar_mass:.6f}\\,\\mathrm{{g\\,mol^{{-1}}}}$."
    )
    artifacts: list[ScientificArtifact] = []
    out_dir = _artifact_dir(payload)
    if out_dir is not None:
        table_path = out_dir / "formula_mass_table.csv"
        pd.DataFrame(rows).to_csv(table_path, index=False)
        artifacts.append(
            ScientificArtifact(
                path=str(table_path),
                kind="csv",
                description="Formula-mass atom counts and mass contributions.",
            )
        )
    return ScientificAnalysisResult(
        operation=payload.operation,
        markdown=markdown,
        latex=latex,
        tables=rows,
        values={"formula": formula, "molar_mass_g_mol": molar_mass},
        artifacts=artifacts,
        reproducibility=_base_reproducibility(payload),
        checks=[
            {
                "name": "atom_balance",
                "passed": sum(counts.values()) > 0,
                "detail": f"{sum(counts.values())} atoms parsed",
            }
        ],
    )


def _parse_formula(formula: str) -> dict[str, int]:
    tokens = re.findall(r"([A-Z][a-z]?|\(|\)|\d+)", formula)
    if not tokens or "".join(tokens) != formula:
        raise ValueError(f"Invalid chemical formula: {formula!r}")
    stack: list[dict[str, int]] = [{}]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "(":
            stack.append({})
            index += 1
        elif token == ")":
            if len(stack) == 1:
                raise ValueError(f"Unmatched ')' in formula: {formula!r}")
            group = stack.pop()
            index += 1
            multiplier = 1
            if index < len(tokens) and tokens[index].isdigit():
                multiplier = int(tokens[index])
                index += 1
            for element, count in group.items():
                stack[-1][element] = stack[-1].get(element, 0) + count * multiplier
        elif token.isdigit():
            raise ValueError(f"Unexpected count {token!r} in formula: {formula!r}")
        else:
            index += 1
            count = 1
            if index < len(tokens) and tokens[index].isdigit():
                count = int(tokens[index])
                index += 1
            stack[-1][token] = stack[-1].get(token, 0) + count
    if len(stack) != 1:
        raise ValueError(f"Unmatched '(' in formula: {formula!r}")
    return stack[0]


def _harmonic_oscillator(payload: ScientificAnalysisInput) -> ScientificAnalysisResult:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from scipy.integrate import solve_ivp

    mass = float(payload.data.get("mass", 2.0))
    spring_constant = float(payload.data.get("spring_constant", 8.0))
    x0 = float(payload.data.get("x0", 1.0))
    v0 = float(payload.data.get("v0", 0.0))
    t_end = float(payload.data.get("t_end", 2.0 * math.pi))
    n_points = int(payload.data.get("n_points", 200))
    if mass <= 0 or spring_constant <= 0 or n_points < 5:
        raise ValueError(
            "mass and spring_constant must be positive; n_points must be >= 5"
        )

    omega = math.sqrt(spring_constant / mass)
    period = 2.0 * math.pi / omega
    t_eval = np.linspace(0.0, t_end, n_points)

    def rhs(_t: float, y: list[float]) -> list[float]:
        return [y[1], -(spring_constant / mass) * y[0]]

    solution = solve_ivp(
        rhs,
        (0.0, t_end),
        [x0, v0],
        t_eval=t_eval,
        rtol=1e-10,
        atol=1e-12,
    )
    displacement = solution.y[0]
    velocity = solution.y[1]
    energy = 0.5 * mass * velocity**2 + 0.5 * spring_constant * displacement**2
    energy_drift = float(np.max(np.abs(energy - energy[0])))

    artifacts: list[ScientificArtifact] = []
    out_dir = _artifact_dir(payload)
    if out_dir is not None:
        df = pd.DataFrame(
            {
                "time": t_eval,
                "displacement": displacement,
                "velocity": velocity,
                "energy": energy,
            }
        )
        csv_path = out_dir / "harmonic_oscillator_timeseries.csv"
        df.to_csv(csv_path, index=False)
        artifacts.append(
            ScientificArtifact(
                path=str(csv_path),
                kind="csv",
                description="Time, displacement, velocity, and total energy.",
            )
        )

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(t_eval, displacement, label="displacement")
        ax.plot(t_eval, velocity, label="velocity", alpha=0.75)
        ax.set_xlabel("Time")
        ax.set_ylabel("State")
        ax.set_title("Simple harmonic oscillator")
        ax.grid(alpha=0.25)
        ax.legend()
        fig.tight_layout()
        png_path = out_dir / "harmonic_oscillator.png"
        fig.savefig(png_path, dpi=180)
        plt.close(fig)
        artifacts.append(
            ScientificArtifact(
                path=str(png_path),
                kind="png",
                description="Publication-ready oscillator state plot.",
            )
        )

    markdown = (
        f"The undamped oscillator has angular frequency **{omega:.6f} rad/s** "
        f"and period **{period:.6f} s**. Numerical integration conserved total "
        f"energy to a maximum absolute drift of **{energy_drift:.3e}**."
    )
    latex = (
        "\\subsubsection{Harmonic oscillator model}\n"
        f"The displacement obeys $m\\ddot x + kx = 0$ with $m={mass:g}$ and "
        f"$k={spring_constant:g}$. Thus $\\omega=\\sqrt{{k/m}}={omega:.6f}$ "
        f"and $T=2\\pi/\\omega={period:.6f}$."
    )
    return ScientificAnalysisResult(
        operation=payload.operation,
        markdown=markdown,
        latex=latex,
        values={
            "omega_rad_s": omega,
            "period": period,
            "energy_initial": float(energy[0]),
            "max_abs_energy_drift": energy_drift,
        },
        artifacts=artifacts,
        reproducibility={
            **_base_reproducibility(payload),
            "solver": "scipy.integrate.solve_ivp",
            "rtol": 1e-10,
            "atol": 1e-12,
        },
        checks=[
            {
                "name": "energy_conservation",
                "passed": energy_drift < 1e-8,
                "detail": f"max_abs_energy_drift={energy_drift:.3e}",
            }
        ],
    )


def _linear_regression(payload: ScientificAnalysisInput) -> ScientificAnalysisResult:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    y = np.asarray(payload.data.get("y", [1.0, 2.1, 2.9, 4.2, 5.1]), dtype=float)
    x_raw = payload.data.get("x", [0.0, 1.0, 2.0, 3.0, 4.0])
    x = np.asarray(x_raw, dtype=float)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    if x.shape[0] != y.shape[0] or y.shape[0] < x.shape[1] + 2:
        raise ValueError("x and y must have compatible rows with enough observations")
    feature_names = payload.data.get("feature_names") or [
        f"x{i + 1}" for i in range(x.shape[1])
    ]

    used_statsmodels = _module_available("statsmodels")
    if used_statsmodels:
        import statsmodels.api as sm

        design = sm.add_constant(x, has_constant="add")
        model = sm.OLS(y, design).fit()
        fitted = np.asarray(model.fittedvalues)
        params = np.asarray(model.params)
        stderr = np.asarray(model.bse)
        pvalues = np.asarray(model.pvalues)
        conf_int = np.asarray(model.conf_int())
        r_squared = float(model.rsquared)
    else:
        design = np.column_stack([np.ones(x.shape[0]), x])
        params, *_ = np.linalg.lstsq(design, y, rcond=None)
        fitted = design @ params
        residual = y - fitted
        dof = max(1, design.shape[0] - design.shape[1])
        sigma2 = float((residual @ residual) / dof)
        cov = sigma2 * np.linalg.inv(design.T @ design)
        stderr = np.sqrt(np.diag(cov))
        pvalues = np.full(params.shape, math.nan)
        conf_int = np.column_stack([params - 1.96 * stderr, params + 1.96 * stderr])
        total = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = 1.0 - float(np.sum(residual**2)) / total if total else 1.0

    names = ["intercept", *[str(name) for name in feature_names]]
    rows = [
        {
            "term": names[i],
            "coefficient": float(params[i]),
            "std_error": float(stderr[i]),
            "p_value": None if math.isnan(float(pvalues[i])) else float(pvalues[i]),
            "ci_low": float(conf_int[i, 0]),
            "ci_high": float(conf_int[i, 1]),
        }
        for i in range(len(params))
    ]

    artifacts: list[ScientificArtifact] = []
    out_dir = _artifact_dir(payload)
    if out_dir is not None:
        table_path = out_dir / "linear_regression_coefficients.csv"
        pd.DataFrame(rows).to_csv(table_path, index=False)
        artifacts.append(
            ScientificArtifact(
                path=str(table_path),
                kind="csv",
                description="Regression coefficient table with confidence intervals.",
            )
        )
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.scatter(y, fitted, color="#4f46e5")
        lims = [
            min(float(y.min()), float(fitted.min())),
            max(float(y.max()), float(fitted.max())),
        ]
        ax.plot(lims, lims, "k--", linewidth=1)
        ax.set_xlabel("Observed")
        ax.set_ylabel("Fitted")
        ax.set_title("Observed vs fitted response")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        png_path = out_dir / "linear_regression_observed_vs_fitted.png"
        fig.savefig(png_path, dpi=180)
        plt.close(fig)
        artifacts.append(
            ScientificArtifact(
                path=str(png_path),
                kind="png",
                description="Observed-versus-fitted regression diagnostic plot.",
            )
        )

    markdown = (
        f"Fitted an OLS regression with **{len(y)} observations** and "
        f"**{x.shape[1]} predictors**. The model achieved **R^2={r_squared:.6f}** "
        f"using {'statsmodels' if used_statsmodels else 'NumPy least squares'}."
    )
    latex = (
        "\\subsubsection{Linear model}\n"
        "The fitted model was $y_i=\\beta_0+\\sum_j \\beta_j x_{ij}+\\epsilon_i$. "
        f"The coefficient of determination was $R^2={r_squared:.6f}$."
    )
    return ScientificAnalysisResult(
        operation=payload.operation,
        markdown=markdown,
        latex=latex,
        tables=rows,
        values={"r_squared": r_squared, "n_observations": int(len(y))},
        artifacts=artifacts,
        reproducibility={
            **_base_reproducibility(payload),
            "engine": "statsmodels.OLS" if used_statsmodels else "numpy.linalg.lstsq",
        },
        checks=[
            {
                "name": "finite_coefficients",
                "passed": bool(np.all(np.isfinite(params))),
                "detail": f"{len(params)} coefficients estimated",
            }
        ],
    )


def _single_cell_qc(payload: ScientificAnalysisInput) -> ScientificAnalysisResult:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    counts = np.asarray(
        payload.data.get("counts", [[3, 0, 2], [4, 5, 2], [0, 1, 3]]),
        dtype=float,
    )
    genes = payload.data.get("genes") or ["MT-ND1", "ACTB", "MS4A1"]
    cells = payload.data.get("cells") or [
        f"cell_{i + 1}" for i in range(counts.shape[0])
    ]
    mt_prefix = str(payload.data.get("mt_prefix") or "MT-")
    if (
        counts.ndim != 2
        or counts.shape[1] != len(genes)
        or counts.shape[0] != len(cells)
    ):
        raise ValueError("counts must be a 2D matrix matching genes and cells")

    mt_mask = np.asarray([str(gene).startswith(mt_prefix) for gene in genes])
    total_counts = counts.sum(axis=1)
    detected_genes = (counts > 0).sum(axis=1)
    mt_counts = (
        counts[:, mt_mask].sum(axis=1) if mt_mask.any() else np.zeros(counts.shape[0])
    )
    pct_mt = np.divide(
        mt_counts * 100.0,
        total_counts,
        out=np.zeros_like(mt_counts),
        where=total_counts > 0,
    )
    cell_rows = [
        {
            "cell": str(cells[i]),
            "total_counts": float(total_counts[i]),
            "n_genes_by_counts": int(detected_genes[i]),
            "pct_counts_mt": float(pct_mt[i]),
        }
        for i in range(len(cells))
    ]
    gene_rows = [
        {
            "gene": str(genes[j]),
            "total_counts": float(counts[:, j].sum()),
            "n_cells_by_counts": int((counts[:, j] > 0).sum()),
            "is_mitochondrial": bool(mt_mask[j]),
        }
        for j in range(len(genes))
    ]

    artifacts: list[ScientificArtifact] = []
    out_dir = _artifact_dir(payload)
    if out_dir is not None:
        cell_path = out_dir / "single_cell_cell_qc.csv"
        gene_path = out_dir / "single_cell_gene_qc.csv"
        pd.DataFrame(cell_rows).to_csv(cell_path, index=False)
        pd.DataFrame(gene_rows).to_csv(gene_path, index=False)
        artifacts.extend(
            [
                ScientificArtifact(
                    path=str(cell_path), kind="csv", description="Per-cell QC metrics."
                ),
                ScientificArtifact(
                    path=str(gene_path), kind="csv", description="Per-gene QC metrics."
                ),
            ]
        )
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.scatter(total_counts, detected_genes, c=pct_mt, cmap="viridis", s=60)
        ax.set_xlabel("Total counts")
        ax.set_ylabel("Detected genes")
        ax.set_title("Single-cell QC summary")
        fig.tight_layout()
        png_path = out_dir / "single_cell_qc.png"
        fig.savefig(png_path, dpi=180)
        plt.close(fig)
        artifacts.append(
            ScientificArtifact(
                path=str(png_path),
                kind="png",
                description="Single-cell QC scatter plot.",
            )
        )

    markdown = (
        f"Computed single-cell QC for **{counts.shape[0]} cells** and "
        f"**{counts.shape[1]} genes**. Median total counts were "
        f"**{float(np.median(total_counts)):.3f}** and median detected genes "
        f"were **{float(np.median(detected_genes)):.3f}**."
    )
    latex = (
        "\\subsubsection{Single-cell quality control}\n"
        "For each cell, total counts, detected genes, and mitochondrial percentage "
        "were computed as $p_{\\mathrm{MT}}=100\\,C_{\\mathrm{MT}}/C_{\\mathrm{total}}$."
    )
    return ScientificAnalysisResult(
        operation=payload.operation,
        markdown=markdown,
        latex=latex,
        tables=[
            {"name": "cell_qc", "rows": cell_rows},
            {"name": "gene_qc", "rows": gene_rows},
        ],
        values={
            "n_cells": int(counts.shape[0]),
            "n_genes": int(counts.shape[1]),
            "scanpy_available": _module_available("scanpy"),
        },
        artifacts=artifacts,
        reproducibility=_base_reproducibility(payload),
        checks=[
            {
                "name": "nonnegative_counts",
                "passed": bool(np.all(counts >= 0)),
                "detail": "All count entries are nonnegative.",
            }
        ],
    )


def _quantum_pauli(payload: ScientificAnalysisInput) -> ScientificAnalysisResult:
    import numpy as np

    pauli = str(
        payload.data.get("operator") or payload.data.get("pauli") or "X"
    ).upper()
    matrices = {
        "X": np.asarray([[0, 1], [1, 0]], dtype=complex),
        "Y": np.asarray([[0, -1j], [1j, 0]], dtype=complex),
        "Z": np.asarray([[1, 0], [0, -1]], dtype=complex),
    }
    if pauli not in matrices:
        raise ValueError("operator/pauli must be one of X, Y, or Z")
    operator = matrices[pauli]
    eigenvalues = np.linalg.eigvalsh(operator)
    trace = np.trace(operator)
    determinant = np.linalg.det(operator)
    state = np.asarray(payload.data.get("state") or [1.0, 0.0], dtype=complex)
    norm = float(np.vdot(state, state).real)
    if state.shape != (2,) or norm <= 0:
        raise ValueError("state must be a nonzero two-element vector")
    state = state / math.sqrt(norm)
    expectation = np.vdot(state, operator @ state)

    markdown = (
        f"Pauli-{pauli} has eigenvalues **{_format_complex_list(eigenvalues)}**, "
        f"trace **{trace.real:.1f}**, determinant **{determinant.real:.1f}**, "
        f"and expectation value **{expectation.real:.6f}** for the supplied state."
    )
    latex = (
        f"\\subsubsection{{Pauli-{pauli} operator}}\n"
        f"For the normalized state $|\\psi\\rangle$, "
        f"$\\langle \\sigma_{pauli} \\rangle = \\langle\\psi|\\sigma_{pauli}|\\psi\\rangle = {expectation.real:.6f}$."
    )
    values = {
        "operator": pauli,
        "eigenvalues": [float(v.real) for v in eigenvalues],
        "trace": float(trace.real),
        "determinant": float(determinant.real),
        "expectation": float(expectation.real),
        "qutip_available": _module_available("qutip"),
    }
    artifacts: list[ScientificArtifact] = []
    out_dir = _artifact_dir(payload)
    if out_dir is not None:
        json_path = out_dir / "quantum_pauli_invariants.json"
        json_path.write_text(
            json.dumps(values, indent=2, sort_keys=True), encoding="utf-8"
        )
        artifacts.append(
            ScientificArtifact(
                path=str(json_path),
                kind="json",
                description="Pauli-operator invariants and expectation value.",
            )
        )
    return ScientificAnalysisResult(
        operation=payload.operation,
        markdown=markdown,
        latex=latex,
        values=values,
        artifacts=artifacts,
        reproducibility=_base_reproducibility(payload),
        checks=[
            {
                "name": "hermitian_operator",
                "passed": bool(np.allclose(operator, operator.conj().T)),
                "detail": f"Pauli-{pauli} equals its conjugate transpose.",
            },
            {
                "name": "normalized_state",
                "passed": bool(np.isclose(np.vdot(state, state).real, 1.0)),
                "detail": "State norm is one after normalization.",
            },
        ],
    )


def _format_complex_list(values: Any) -> str:
    return ", ".join(f"{float(value.real):g}" for value in values)


def _publication_plot(payload: ScientificAnalysisInput) -> ScientificAnalysisResult:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    x = np.asarray(payload.data.get("x", [0, 1, 2, 3]), dtype=float)
    y = np.asarray(payload.data.get("y", [0, 1, 4, 9]), dtype=float)
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError("x and y must be one-dimensional arrays of equal length")
    chart_type = str(payload.data.get("chart_type") or "line")
    title = str(payload.data.get("title") or "Publication plot")
    x_label = str(payload.data.get("x_label") or "x")
    y_label = str(payload.data.get("y_label") or "y")
    out_dir = _artifact_dir(payload)
    artifacts: list[ScientificArtifact] = []

    if out_dir is not None:
        data_path = out_dir / "plot_data.csv"
        pd.DataFrame({x_label: x, y_label: y}).to_csv(data_path, index=False)
        artifacts.append(
            ScientificArtifact(
                path=str(data_path),
                kind="csv",
                description="Data used to render the plot.",
            )
        )

        fig, ax = plt.subplots(figsize=(6, 4))
        if chart_type == "scatter":
            ax.scatter(x, y, color="#4f46e5")
        elif chart_type == "bar":
            ax.bar(x, y, color="#4f46e5", alpha=0.85)
        else:
            ax.plot(x, y, marker="o", color="#4f46e5")
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.set_title(title)
        ax.grid(alpha=0.25)
        fig.tight_layout()
        png_path = out_dir / "publication_plot.png"
        fig.savefig(png_path, dpi=180)
        plt.close(fig)
        artifacts.append(
            ScientificArtifact(
                path=str(png_path), kind="png", description="Matplotlib static plot."
            )
        )

        if _module_available("plotly"):
            import plotly.express as px

            df = pd.DataFrame({x_label: x, y_label: y})
            if chart_type == "scatter":
                plotly_fig = px.scatter(df, x=x_label, y=y_label, title=title)
            elif chart_type == "bar":
                plotly_fig = px.bar(df, x=x_label, y=y_label, title=title)
            else:
                plotly_fig = px.line(
                    df, x=x_label, y=y_label, title=title, markers=True
                )
            html_path = out_dir / "publication_plot.html"
            plotly_fig.write_html(html_path, include_plotlyjs=True, full_html=True)
            artifacts.append(
                ScientificArtifact(
                    path=str(html_path),
                    kind="html",
                    description="Standalone interactive Plotly plot.",
                )
            )

    markdown = (
        f"Generated a **{chart_type}** plot with **{len(x)} points**. "
        "The output includes the source data table and static manuscript figure"
        + (
            " plus an interactive Plotly HTML artifact."
            if _module_available("plotly")
            else "."
        )
    )
    latex = (
        "\\subsubsection{Plot generation}\n"
        "The plotted data were exported alongside the figure so the visualization can be reproduced exactly."
    )
    return ScientificAnalysisResult(
        operation=payload.operation,
        markdown=markdown,
        latex=latex,
        values={"n_points": int(len(x)), "chart_type": chart_type},
        artifacts=artifacts,
        reproducibility=_base_reproducibility(payload),
        checks=[
            {
                "name": "finite_plot_values",
                "passed": bool(np.all(np.isfinite(x)) and np.all(np.isfinite(y))),
                "detail": f"{len(x)} x/y pairs checked",
            }
        ],
    )


_ATOMIC_WEIGHTS: dict[str, float] = {
    "H": 1.00794,
    "B": 10.81,
    "C": 12.011,
    "N": 14.0067,
    "O": 15.9994,
    "F": 18.998403163,
    "Na": 22.98976928,
    "Mg": 24.305,
    "Al": 26.9815385,
    "Si": 28.085,
    "P": 30.973761998,
    "S": 32.065,
    "Cl": 35.453,
    "K": 39.0983,
    "Ca": 40.078,
    "Fe": 55.845,
    "Cu": 63.546,
    "Zn": 65.38,
    "Br": 79.904,
    "I": 126.90447,
}


__all__ = [
    "ScientificAnalysisInput",
    "ScientificAnalysisResult",
    "ScientificArtifact",
    "run_scientific_analysis",
]
