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
pip-audit --skip-editable \
  --ignore-vuln CVE-2025-69872 \
  --ignore-vuln PYSEC-2026-76 \
  --ignore-vuln PYSEC-2026-83 \
  --ignore-vuln CVE-2026-27794 \
  --ignore-vuln CVE-2026-35029 \
  --ignore-vuln CVE-2026-35030 \
  --ignore-vuln GHSA-69x8-hrgq-fjj8 \
  --ignore-vuln CVE-2026-42271

echo "[security_smoke] gitleaks (any leak = fail) ..."
gitleaks detect --no-banner --redact

echo "OK: no security findings"
