#!/usr/bin/env bash
# Local mirror of .github/workflows/security.yml. Run before pushing.
#
# Each scanner is its own line so a failure tells you exactly which gate
# tripped. The set -e fail-fast is intentional: don't keep scanning after
# a leak is already on disk.
set -euo pipefail

echo "[security_smoke] bandit (HIGH severity = fail) ..."
bandit -r plato/ evals/ --severity-level high --exclude tests/

echo "[security_smoke] safety (advisory report) ..."
safety check --policy-file .safety-policy.yml --save-json safety-report.json || true

echo "[security_smoke] pip-audit (known CVE hard gate) ..."
python .github/scripts/pip_audit_gate.py

echo "[security_smoke] gitleaks (any leak = fail) ..."
gitleaks detect --no-banner --redact

echo "OK: no security findings"
