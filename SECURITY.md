# Security policy

## Reporting a vulnerability

**Do not open a public issue for a security report.** GitHub's *private
vulnerability reporting* is enabled on this repository — please use the
**Security → Report a vulnerability** flow to file confidentially.

If that channel is unavailable, email the maintainers (see `pyproject.toml`
`authors` for current contacts) with `[security]` in the subject line.
We will acknowledge within **5 business days** and aim for a triage
disposition within **10 business days**. Coordinated disclosure: please
allow up to **90 days** before any public discussion.

In your report, include:

- A minimal reproduction (commit hash, command, or input).
- The expected vs. observed behavior.
- The impact you believe a real attacker would have, and against which
  trust boundary (see "Threat model" below).

We do not currently run a paid bug bounty. Researchers acting in good
faith under the timeline above will be credited in `CHANGELOG.md` unless
they request anonymity.

## Supported versions

Plato is pre-1.0 research software. Only the `main` branch receives
security fixes. Tagged releases are snapshots; if a vulnerability lands
in a release tag, the fix appears on `main` and you are expected to
upgrade. We do not backport.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | Yes — current dev. |
| Tagged releases | No — upgrade to `main`. |
| Pre-Phase-1 (before commit `8fc74ad`) | No — substantial rewrite since. |

## Threat model

Plato orchestrates LLM agents that read external papers, call retrieval
APIs, and generate code. The trust boundaries below describe what we
defend, what we explicitly do not defend, and where we expect the
operator to add controls.

### 1. LLM-generated code (HIGH-RISK, partially mitigated)

**What:** Paper-graph nodes ask LLMs to produce Python. Today, only the
`cmbagent`-driven analysis path executes that code, and it does so in
the **same Python process** as the agent — there is no sandbox.

**Trust assumption:** the operator running Plato is the only consumer
of the generated code. Plato is not a multi-tenant code-execution
service.

**Mitigations in place:**
- `plato.io.scoped_writer.ScopedWriter` constrains *file writes* by
  paper-graph nodes that adopt it (`plato/io/scoped_writer.py`). It
  refuses absolute paths, `..`-traversal, symlink escapes, and writes
  outside a per-node glob allowlist.
- The dashboard treats project directories as data, never as code:
  it never `import`s or `exec`s contents from a project tree.

**Known limitation (tracked):** `cmbagent` code-exec is not yet
sandboxed. The Phase-5 *Executor refactor* (see `CHANGELOG.md`) will
move execution into a subprocess with `seccomp` / network-egress
controls. Until then, **do not run Plato with API keys that have
production write access** and **do not run on shared hosts**.

### 2. Retrieved abstracts and external text (MITIGATED)

**What:** the literature node ingests paper abstracts from arXiv,
Semantic Scholar, ADS, and Perplexity. An adversarial paper can carry
prompt-injection text designed to override Plato's system prompt.

**Mitigations in place:**
- All external text is wrapped in `<external kind="...">` markers via
  `plato.safety.sanitize.wrap_external` before reaching the prompt
  (`plato/safety/sanitize.py`).
- `plato.safety.sanitize.detect_injection_signals` flags common
  patterns ("ignore previous instructions", role-hijack phrases,
  hidden Unicode tag chars, large base64 blobs) and the literature
  node logs warnings on a hit (`plato/langgraph_agents/literature.py`).
- Adversarial coverage: `tests/safety/test_prompt_injection.py` and
  `tests/safety/test_pdf_injection.py` exercise both layers.

**Residual risk:** these are heuristic filters, not guarantees. A
sufficiently novel injection payload may slip through. Operators
running on sensitive corpora should add a model-level review pass
(judge LLM, content classifier) downstream.

### 3. User-uploaded PDFs (MITIGATED)

**What:** the dashboard accepts PDF uploads as project inputs. PDFs
can carry both injection text (extracted into prompts) and crafted
binaries that target the parser.

**Mitigations in place:**
- PDFs are written into per-project directories under the dashboard's
  storage root (`dashboard/backend/...`); they are never executed.
- Extracted text passes through `wrap_external` and
  `detect_injection_signals` on the same path as retrieved abstracts.
- `tests/safety/test_pdf_injection.py` covers a malicious-PDF payload.

**Residual risk:** PDF parser CVEs are scanned via `pip-audit` /
`safety` in `.github/workflows/security.yml`, but a zero-day in a
parser dependency could still expose Plato. Treat the dashboard host
as if any uploaded PDF could be hostile.

### 4. Dashboard authentication and authorization (DELEGATED)

**What:** the dashboard backend trusts the `X-Plato-User` header to
identify the requester (see `dashboard/backend/src/plato_dashboard/auth.py`).
That header is meant to be set by an upstream proxy (Cloudflare Access,
oauth2-proxy, ...) after it has authenticated the user against the
real IdP.

**Trust assumption:** the dashboard is **not** internet-exposed
without an authenticating proxy in front of it. In that posture the
header is unforgeable. In `PLATO_DASHBOARD_AUTH_REQUIRED=1` mode
requests without a header are rejected with 401.

**Mitigations in place:**
- `extract_user_id` strips whitespace and rejects empty values.
- `require_user_id` raises 401 in required-mode when the header is
  missing or blank.
- `tests/safety/test_dashboard_auth_bypass.py` covers empty,
  whitespace-only, and CRLF-injection header attempts.

**Residual risk:** if the dashboard is deployed without an upstream
authenticating proxy, **anyone on the network can set the header to
any value and impersonate any user**. This is documented and intended:
the dashboard does not own identity. Do not bind it to a public
interface without a proxy.

### Out of scope

The following are explicitly outside the threat model:

- Denial of service from an LLM provider rate-limiting Plato. Treated
  as an availability problem, not a security one.
- Side-channel attacks (timing, cache) against the Python interpreter
  or NumPy/SciPy.
- Physical-host compromise of the operator's machine.
- Supply-chain attacks against PyPI mirrors that are not detected by
  `pip-audit` / `safety` at the time of install.

## Defense-in-depth: what runs in CI

The `security` workflow (`.github/workflows/security.yml`) runs on every
PR, every push to `main`, and nightly:

- **bandit** — static analysis of `plato/` and `evals/`. Fails on any
  HIGH-severity finding.
- **safety** — known-CVE scan of resolved deps. Fails on critical CVEs.
- **pip-audit** — PyPA's own CVE check. Fails on any vulnerability
  (`--strict`).
- **gitleaks** — git-history secret scan. Fails on any leak.

`scripts/security_smoke.sh` runs the same scanners locally before push.
