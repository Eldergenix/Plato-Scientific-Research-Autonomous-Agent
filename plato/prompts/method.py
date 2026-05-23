method_planner_prompt = r"""
{research_idea}

Instruction for planning:

Given these datasets, and information on the features and project idea, we want to design a methodology to implement this idea.
The goal of the task is to write a plan that will be used to generate a detailed description of the methodology that will be used to perform the research project.

- Start by requesting the *researcher* to provide reasoning  relevant to the given project idea.
- Clarify the specific hypotheses, assumptions, or questions that should be investigated.
- This can be done in multiple steps. 
- The focus should be strictly on the methods and workflow for this specific project to be performed. **Do not include** any discussion of future directions, future work, project extensions, or limitations.
- The description should be written as if it were a senior researcher explaining to her research assistant how to perform the research necessary for this project.
- Explicitly identify the mathematical models, statistical tests, equations, variables, parameters, random seeds, plotting outputs, and reproducibility artifacts that the results workflow must produce.
- If the project includes numerical analysis, require the use of Plato's scientific tool registry where applicable, especially `run_scientific_analysis`, so calculations can be repeated and checked from structured outputs rather than only from prose.
- If the project includes genomic intervals, reference DNA, annotations, VCF variants, variant-aware sequence extraction, motifs, or genome tracks, require `prepare_genomekit_query` from the genomics tool registry. The methodology must state the genome build, DNA0 interval coordinates, strand, resource paths, expected JSON/table outputs, and any first-run GenomeKit data-cache or remote-resource requirements.

The final step of the plan must be entirely dedicated to writing the full Methodology description.

The only agent involved in this workflow is the researcher.

In this task we do not perform any calculations or analyses, only outline the methodology. 
"""

method_researcher_prompt = r"""
{research_idea}

Given this information, we want to design a methodology to implement this idea.
The goal of the task is to develop a detailed methodology that will be used to carry out the research project.

- You should focus on the methods for this specific project to be performed. **Do not include** any discussion of future directions, future work, project extensions, or limitations.
- The methodology description should be written as if it were a senior researcher explaining to her research assistant how to perform the project. 
- Include a reproducibility subsection. It must specify data inputs, preprocessing filters, equations or mathematical models, statistical tests, plotting/graphing outputs, random seeds, software/tool choices, expected output files, and validation checks.
- When calculations are needed, name the exact operation to run through Plato's scientific-analysis registry when possible: `formula_mass`, `harmonic_oscillator`, `linear_regression`, `single_cell_qc`, `quantum_pauli`, or `publication_plot`.
- For genomics resource access, call `prepare_genomekit_query` through Plato's genomics registry when possible, naming the exact GenomeKit-backed operation: `sequence`, `annotation_overlaps`, `vcf_query`, `variant_sequence`, `motif_scan`, or `track_query`.

The designed methodology should focus on describing the research and analysis that will be performed.

The full methodology description should be written in markdown format and include all the details of the designed methodology.
It should be roughly 500 words long.
"""
