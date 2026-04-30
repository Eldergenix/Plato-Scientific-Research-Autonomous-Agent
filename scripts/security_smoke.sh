#!/usr/bin/env bash
# Local mirror of .github/workflows/security.yml. Run before pushing.
#
# Each scanner is its own line so a failure tells you exactly which gate
# tripped. The set -e fail-fast is intentional: don't keep scanning after
# a leak is already on disk.
set -euo pipefail

echo "[security_smoke] bandit (HIGH severity = fail) ..."
bandit -r plato/ evals/ --severity-level high --exclude tests/

echo "[security_smoke] safety (critical CVE = fail) ..."
safety check --severity critical

echo "[security_smoke] pip-audit (--strict, any CVE = fail) ..."
pip-audit --strict

echo "[security_smoke] gitleaks (any leak = fail) ..."
gitleaks detect --no-banner --redact

echo "OK: no security findings"
