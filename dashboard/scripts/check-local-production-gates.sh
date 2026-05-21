#!/usr/bin/env bash
# Run local source gates before mutating Railway production.
#
# This script is intentionally local/read-only. It verifies the code paths that
# feed the hosted SaaS/Lab production deployment, then leaves live environment
# checks to check-production-readiness.sh after variables/deploy are in place.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash dashboard/scripts/check-local-production-gates.sh [--skip-e2e]

Options:
  --skip-e2e    Skip the full Playwright suite. Targeted hosted checks still run.
  -h, --help    Show this help text.

Checks:
  1. Root Python lint + tests.
  2. Dashboard backend lint + tests.
  3. Frontend typecheck + production build.
  4. Hosted SaaS/Lab focused Playwright checks.
  5. Optional full Playwright suite.
  6. Git whitespace check.
EOF
}

skip_e2e="0"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --skip-e2e)
      skip_e2e="1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
frontend_dir="${repo_root}/dashboard/frontend"
backend_dir="${repo_root}/dashboard/backend"

section() {
  printf '\n== %s ==\n' "$1"
}

section "Root Python gates"
(cd "$repo_root" && uv run ruff check .)
(cd "$repo_root" && uv run pytest -q)

section "Dashboard backend gates"
(cd "$backend_dir" && uv run ruff check .)
(cd "$backend_dir" && uv run pytest -q)

section "Frontend typecheck and build"
(cd "$frontend_dir" && env -u FORCE_COLOR -u NO_COLOR npm run typecheck)
(cd "$frontend_dir" && env -u FORCE_COLOR -u NO_COLOR npm run build)

section "Hosted SaaS/Lab focused E2E"
(
  cd "$frontend_dir"
  PLAYWRIGHT_EXPECT_CLERK_AUTH=1 \
    PLATO_AUTH_PROVIDER=clerk \
    NEXT_PUBLIC_PLATO_AUTH_PROVIDER=clerk \
    NEXT_PUBLIC_PLATO_HOSTED_BILLING=enabled \
    env -u FORCE_COLOR -u NO_COLOR npm run test:e2e -- tests/e2e/hosted-auth.spec.ts --workers=1
)
(
  cd "$frontend_dir"
  PLAYWRIGHT_EXPECT_HOSTED_BILLING_CONFIG_ERROR=1 \
    NEXT_PUBLIC_PLATO_HOSTED_BILLING=enabled \
    env -u FORCE_COLOR -u NO_COLOR npm run test:e2e -- tests/e2e/settings-billing.spec.ts --workers=1
)
(
  cd "$frontend_dir"
  env -u FORCE_COLOR -u NO_COLOR npm run test:e2e -- tests/e2e/hosted-trial-quota.spec.ts --workers=1
)

if [ "$skip_e2e" != "1" ]; then
  section "Full frontend E2E"
  (cd "$frontend_dir" && env -u FORCE_COLOR -u NO_COLOR npm run test:e2e)
fi

section "Git whitespace"
(cd "$repo_root" && git diff --check)

section "Result"
echo "OK: local production gates passed."
