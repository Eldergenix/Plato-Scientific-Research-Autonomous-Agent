#!/usr/bin/env bash
# Plato hosted SaaS/Lab preflight.
#
# Validates the Clerk/Lab production contract without printing secret values.
# By default it checks the current process environment. Use --railway to stream
# linked Railway service variables into the Python checker via stdin.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash dashboard/scripts/check-hosted-saas-preflight.sh [--railway] [--service NAME] [--environment NAME] [--hosted-required] [--strict]

Options:
  --railway             Read variables from the linked Railway service.
  --service NAME        Railway service to read, for example plato.
  --environment NAME    Railway environment to read, for example production.
  --hosted-required     Treat Clerk hosted mode as required even if provider flags are absent.
  --strict              Fail when warnings are emitted, not only errors.
EOF
}

source_mode="env"
hosted_required="0"
strict="0"
railway_service=""
railway_environment=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --railway)
      source_mode="railway"
      ;;
    --service)
      if [ "$#" -lt 2 ]; then
        echo "--service requires a value" >&2
        usage >&2
        exit 2
      fi
      railway_service="$2"
      shift
      ;;
    --environment)
      if [ "$#" -lt 2 ]; then
        echo "--environment requires a value" >&2
        usage >&2
        exit 2
      fi
      railway_environment="$2"
      shift
      ;;
    --hosted-required)
      hosted_required="1"
      ;;
    --strict)
      strict="1"
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

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
checker="${script_dir}/check_hosted_saas_preflight.py"

checker_args=(--source "$source_mode")
if [ "$hosted_required" = "1" ]; then
  checker_args+=(--hosted-required)
fi
if [ "$strict" = "1" ]; then
  checker_args+=(--strict)
fi

if [ "$source_mode" = "railway" ]; then
  railway_args=(variables --json)
  if [ -n "$railway_service" ]; then
    railway_args+=(--service "$railway_service")
  fi
  if [ -n "$railway_environment" ]; then
    railway_args+=(--environment "$railway_environment")
  fi
  railway "${railway_args[@]}" | python3 "$checker" "${checker_args[@]}"
else
  if [ -n "$railway_service" ] || [ -n "$railway_environment" ]; then
    echo "--service/--environment require --railway" >&2
    usage >&2
    exit 2
  fi
  python3 "$checker" "${checker_args[@]}"
fi
