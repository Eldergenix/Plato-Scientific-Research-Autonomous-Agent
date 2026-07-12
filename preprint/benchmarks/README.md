# External biomedical benchmark integration

Plato-Bio pins external benchmark metadata before evaluation so task coverage
cannot drift silently between runs. The first integration targets
**CompBioBench v1**, a CC BY 4.0 benchmark of 100 computational-biology tasks.

- Paper: <https://www.biorxiv.org/content/10.64898/2026.04.06.716850v2>
- Dataset: <https://huggingface.co/datasets/Genentech/compbiobench-data-v1>
- Pinned revision: `c673f0855fce09d320f1677f168f7864eec52c1a`
- Catalog SHA-256: `ac8a5dcf813e9e89556701648140a84b2757fe449e35650168de54baed75ce1c`

Run:

```bash
python -m evals.biomedical_benchmarks
```

The generated manifest deliberately states
`performance_results_included: false`. Catalog ingestion and coverage are not
agent efficacy results. A publishable comparison still requires frozen model
versions, repeated runs, executable outputs, blinded or rubric-based scoring,
and explicit handling of tasks whose evidence is insufficient.
