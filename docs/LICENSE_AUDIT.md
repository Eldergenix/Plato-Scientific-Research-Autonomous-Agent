# License Audit

Plato ships under **GPLv3** (see top-level [`LICENSE`](../LICENSE) and the
`license` field in [`pyproject.toml`](../pyproject.toml)). Every runtime
dependency must compose cleanly with that choice.

This document is the committed snapshot for human review. The CI job in
`.github/workflows/license-audit.yml` re-runs the underlying script on every
PR and fails the build if a new dependency violates the rules below.

## 1. Summary

- Tool: `scripts/license_audit.py` (uses stdlib `importlib.metadata`).
- Distributions audited: **239** (Plato + dashboard backend + transitive deps).
- Incompatible distributions: **0** after reviewed overrides.
- All findings exit cleanly: `python scripts/license_audit.py --format=md`
  returns exit code 0.

## 2. License distribution

| License family               | Count | Notes                                 |
|------------------------------|------:|---------------------------------------|
| MIT                          |    92 | dominant license across the deps      |
| Apache-2.0                   |    58 | includes "Apache 2.0" / "Apache License 2.0" string variants |
| BSD-3-Clause                 |    55 | including 3-Clause BSD synonyms       |
| PSF-2.0                      |     3 | Python Software Foundation            |
| ISC                          |     3 |                                       |
| BSD-2-Clause                 |     3 |                                       |
| GPL-3.0 / GPL-3.0+ / GPLv3   |     3 | first-party (Plato) plus GPLv3 deps   |
| MPL-2.0                      |     3 | including compound exprs with MIT     |
| LGPL-3.0 / LGPL-3.0-or-later |     2 |                                       |
| AGPL-3.0 (PyMuPDF)           |     1 | dual-licensed; AGPL-3.0 path is GPLv3-compatible |
| NCSA, MIT-CMU, 0BSD, CC0, Zlib | misc | all permissive, GPLv3-compatible    |

(Re-generate the full breakdown with the reproduction command in section 6.)

## 3. Per-dependency table

The full per-dependency table — name, version, license, source URL, and
GPLv3-compatibility verdict — is regenerated on every CI run and uploaded
as the `license-audit` artifact in JSON, CSV, and Markdown form. To produce
the same table locally, see the reproduction command in section 6.

The on-disk snapshot below covers the load-bearing direct dependencies
called out in `pyproject.toml`.

| Name                    | Version  | License        | Source                                                    | GPLv3 OK |
|-------------------------|----------|----------------|-----------------------------------------------------------|----------|
| langchain-google-genai  | latest   | MIT            | https://github.com/langchain-ai/langchain                 | yes      |
| langchain-anthropic     | >=0.3.10 | MIT            | https://github.com/langchain-ai/langchain                 | yes      |
| langchain-openai        | >=0.3.12 | MIT            | https://github.com/langchain-ai/langchain                 | yes      |
| langgraph               | >=0.3.25 | MIT            | https://github.com/langchain-ai/langgraph                 | yes      |
| langgraph-checkpoint-sqlite | >=2.0.0 | MIT         | https://github.com/langchain-ai/langgraph                 | yes      |
| sqlalchemy              | >=2.0    | MIT            | https://www.sqlalchemy.org                                | yes      |
| httpx                   | >=0.27   | BSD-3-Clause   | https://github.com/encode/httpx                           | yes      |
| google-cloud-aiplatform | latest   | Apache-2.0     | https://github.com/googleapis/python-aiplatform           | yes      |
| google-ai-generativelanguage | >=0.6.17 | Apache-2.0 | https://github.com/googleapis/python-ai-generativelanguage | yes  |
| flatbuffers             | >=24.12  | Apache-2.0     | https://github.com/google/flatbuffers                     | yes      |
| filelock                | >=3.17   | Unlicense      | https://github.com/tox-dev/filelock                       | yes      |
| cmbagent                | >=0.0.1.post63 | (no metadata; upstream repo) | https://github.com/CMBAgents/cmbagent  | reviewed (see §4) |
| pymupdf                 | latest   | AGPL-3.0 / Artifex Commercial | https://github.com/pymupdf/pymupdf         | yes (AGPL-3.0 path) |
| pillow                  | latest   | MIT-CMU        | https://github.com/python-pillow/Pillow                   | yes      |
| jsonschema              | latest   | MIT            | https://github.com/python-jsonschema/jsonschema           | yes      |
| futurehouse-client      | latest   | Apache-2.0     | https://github.com/Future-House/futurehouse-client        | yes      |
| json5                   | latest   | Apache-2.0     | https://github.com/dpranke/pyjson5                        | yes      |
| pydantic (transitive)   | latest   | MIT            | https://github.com/pydantic/pydantic                      | yes      |

The full enumeration of transitive dependencies is regenerated by CI; this
table is reviewed manually each time a direct dependency in
`pyproject.toml` changes.

## 4. Vendor terms summary

- **cmbagent** (Apache-2.0 per upstream `pyproject.toml`/LICENSE; PyPI
  metadata is missing) — the audit script special-cases the package as the
  upstream repository's LICENSE file is Apache-2.0. We pin to a known good
  release and re-validate on each bump.
- **futurehouse-client** — Apache-2.0. Compatible.
- **langgraph / langgraph-checkpoint-sqlite** — MIT. Compatible.
- **langchain-\*** packages — MIT. Compatible.
- **pydantic** — MIT (License-Expression). Compatible.
- **httpx** — BSD-3-Clause. Compatible.
- **sqlalchemy** — MIT. Compatible.
- **PyMuPDF** — dual-licensed AGPL-3.0 OR Artifex commercial. We use the
  AGPL-3.0 path, which is GPLv3-compatible. If we ever need the commercial
  branch we must revisit downstream distribution rights.
- **healpy** — PyPI metadata is `GPL-2.0-only`, but the upstream LICENSE in
  the healpy repository is `GPL-2.0-or-later`. The audit script applies a
  reviewed override (`scripts/license_audit.py::LICENSE_OVERRIDES`) to
  reflect upstream reality. Reconfirm on every healpy upgrade.

## 5. Compatibility statement

After reviewing every installed distribution, every direct dependency in
`pyproject.toml`, and the transitive dependency tree as resolved by `pip`
into the project's venv, **Plato's full runtime is compatible with GPLv3**.
The `scripts/license_audit.py` tool exits 0 against the venv used by CI,
and the project itself is licensed under the GPLv3 terms in `LICENSE`.

The audit tool is intentionally conservative:
- Unrecognised license strings fail closed.
- Incompatibility tokens (`Proprietary`, `BUSL`, `Elastic`, `Commons Clause`,
  `CC-BY-NC`, `GPL-2.0-only`, `SSPL`) take precedence over compatibility
  matches, so a `MIT OR Proprietary` dual license fails.
- Reviewed overrides for upstream metadata bugs (currently only `healpy`)
  are listed in code with a citation.

## 6. Reproduction

Re-generate this snapshot from a clean venv:

```bash
pip install -e ".[obs]"
python scripts/license_audit.py --format=md > docs/LICENSE_AUDIT.md
```

For machine-readable output:

```bash
python scripts/license_audit.py --format=json > license-audit.json
python scripts/license_audit.py --format=csv > license-audit.csv
```

To regenerate the CycloneDX SBOM:

```bash
pip install cyclonedx-bom
python scripts/generate_sbom.py --output sbom.json
```

Both scripts are wired into `.github/workflows/license-audit.yml`, which
runs on every PR and nightly at 04:00 UTC.
