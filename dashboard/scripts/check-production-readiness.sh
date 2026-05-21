#!/usr/bin/env bash
# Read-only production readiness check for the hosted Plato SaaS/Lab deployment.
#
# This script intentionally does not set variables or deploy. It verifies the
# current Railway service and public origin after release prep or after a deploy.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash dashboard/scripts/check-production-readiness.sh [options]

Options:
  --service NAME        Railway service to read (default: plato).
  --environment NAME    Railway environment to read (default: production).
  --origin URL          Public HTTPS app origin (default: https://discovering.app).
  --variables-file PATH Use a local Railway variables snapshot instead of the CLI.
                        Accepts JSON (`railway variables --json`) or KV (`railway variables --kv`).
  --lines N             Railway log lines to scan per log type (default: 500).
  --skip-logs           Skip Railway build/deploy log scans.
  -h, --help            Show this help text.

Checks:
  1. Hosted SaaS/Lab Railway variables via the redacted preflight.
  2. Public /api/v1/health returns 200 with ok=true.
  3. Public signed-out /api/v1/auth/me reports auth_required=true and no user.
  4. Public unauthenticated /api/v1/projects returns 401.
  5. Hosted user/Lab pages render without app-error markers.
  6. Latest Railway build and deployment logs contain no warning/error markers.
EOF
}

service="plato"
environment="production"
origin="https://discovering.app"
lines="500"
skip_logs="0"
variables_file=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --service)
      if [ "$#" -lt 2 ]; then
        echo "--service requires a value" >&2
        usage >&2
        exit 2
      fi
      service="$2"
      shift
      ;;
    --environment)
      if [ "$#" -lt 2 ]; then
        echo "--environment requires a value" >&2
        usage >&2
        exit 2
      fi
      environment="$2"
      shift
      ;;
    --origin)
      if [ "$#" -lt 2 ]; then
        echo "--origin requires a value" >&2
        usage >&2
        exit 2
      fi
      origin="${2%/}"
      shift
      ;;
    --lines)
      if [ "$#" -lt 2 ]; then
        echo "--lines requires a value" >&2
        usage >&2
        exit 2
      fi
      lines="$2"
      shift
      ;;
    --variables-file)
      if [ "$#" -lt 2 ]; then
        echo "--variables-file requires a value" >&2
        usage >&2
        exit 2
      fi
      variables_file="$2"
      shift
      ;;
    --skip-logs)
      skip_logs="1"
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

if [[ ! "$origin" =~ ^https://[^/]+(:[0-9]+)?$ ]]; then
  echo "--origin must be an HTTPS origin without a path: ${origin}" >&2
  exit 2
fi

if [[ ! "$lines" =~ ^[0-9]+$ ]] || [ "$lines" -lt 1 ]; then
  echo "--lines must be a positive integer" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
preflight_checker="${script_dir}/check_hosted_saas_preflight.py"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

status=0
preflight_failed=0
variables_read_failed=0
build_log_failed=0
deploy_log_failed=0
app_not_found_failed=0
variables_json="${tmp_dir}/railway-variables.json"
variables_kv="${tmp_dir}/railway-variables.env"
app_not_found_paths="${tmp_dir}/app-not-found-paths.txt"

section() {
  printf '\n== %s ==\n' "$1"
}

mark_failed() {
  status=1
}

record_app_not_found() {
  local label="$1"

  app_not_found_failed=1
  printf '%s\n' "$label" >>"$app_not_found_paths"
}

railway_value() {
  VARS_FILE="$variables_json" VAR_NAME="$1" python3 - <<'PY'
import json
import os
from pathlib import Path

values = json.loads(Path(os.environ["VARS_FILE"]).read_text(encoding="utf-8"))
value = values.get(os.environ["VAR_NAME"], "")
if value is None:
    value = ""
print(str(value).strip())
PY
}

var_equals() {
  local name="$1"
  local expected="$2"
  local actual
  actual="$(railway_value "$name")"
  [ "$actual" = "$expected" ]
}

var_min_length() {
  local name="$1"
  local min_length="$2"
  local actual
  actual="$(railway_value "$name")"
  [ "${#actual}" -ge "$min_length" ]
}

kv_variables_to_json() {
  VARS_KV_FILE="$variables_kv" python3 - <<'PY'
import json
import os
from pathlib import Path

values = {}
for line in Path(os.environ["VARS_KV_FILE"]).read_text(encoding="utf-8").splitlines():
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key] = value
print(json.dumps(values))
PY
}

load_variables_file() {
  local path="$1"

  if [ ! -f "$path" ]; then
    echo "--variables-file does not exist: ${path}" >&2
    return 1
  fi

  if python3 -m json.tool "$path" >/dev/null 2>&1; then
    cp "$path" "$variables_json"
    return 0
  fi

  cp "$path" "$variables_kv"
  kv_variables_to_json >"$variables_json"
}

read_railway_variables() {
  local attempt

  if [ -n "$variables_file" ]; then
    load_variables_file "$variables_file"
    return "$?"
  fi

  for attempt in 1 2 3; do
    if railway variables --json --service "$service" --environment "$environment" >"$variables_json"; then
      return 0
    fi
    if railway variables --kv --service "$service" --environment "$environment" >"$variables_kv"; then
      kv_variables_to_json >"$variables_json"
      return 0
    fi
    if [ "$attempt" -lt 3 ]; then
      echo "railway variables read failed; retrying (${attempt}/3)" >&2
      sleep "$attempt"
    fi
  done

  return 1
}

fetch_with_retries() {
  local body="$1"
  local url="$2"
  local expected_code="$3"
  local follow_redirects="$4"
  local label="$5"
  local attempt
  local code
  local application_not_found=0
  local curl_args=(-sS)

  if [ "$follow_redirects" = "1" ]; then
    curl_args=(-LsS)
  fi

  for attempt in 1 2 3; do
    code="$(curl "${curl_args[@]}" -o "$body" -w '%{http_code}' "$url" || true)"
    if [ "$code" = "$expected_code" ]; then
      printf '%s' "$code"
      return 0
    fi
    application_not_found=0
    if [ "$code" = "404" ] && grep -Fq "Application not found" "$body"; then
      application_not_found=1
    fi
    if [ "$attempt" -lt 3 ] && (
      [ "$application_not_found" -eq 1 ] ||
      [ "$code" = "000" ] ||
      { [[ "$code" =~ ^[0-9]+$ ]] && [ "$code" -ge 500 ]; }
    ); then
      echo "${label} returned HTTP ${code}; retrying (${attempt}/3)" >&2
      sleep "$attempt"
      continue
    fi
    printf '%s' "$code"
    return 0
  done

  printf '%s' "$code"
}

print_remediation() {
  local variable_commands=0

  cat <<EOF

Next steps to clear production blockers:
EOF

  if [ "$variables_read_failed" -eq 1 ]; then
    cat <<EOF
  1. Restore Railway CLI variable access, then re-run the checker.
     The variable snapshot could not be read, so this run cannot safely infer which hosted variables are missing.
       railway variables --json --service ${service} --environment ${environment}
     If the CLI keeps failing, provide a local JSON or KV snapshot with:
       bash dashboard/scripts/check-production-readiness.sh --service ${service} --environment ${environment} --origin ${origin} --variables-file /path/to/railway-variables.json
EOF
  else

    if ! var_min_length "PLATO_BACKEND_PROXY_SECRET" 32; then
      if [ "$variable_commands" -eq 0 ]; then
        echo "  1. Set missing or invalid hosted variables without triggering partial deploys:"
      fi
      cat <<EOF
       PLATO_BACKEND_PROXY_SECRET="\$(openssl rand -base64 32)"
       railway variables --service ${service} --environment ${environment} --skip-deploys --set "PLATO_BACKEND_PROXY_SECRET=\${PLATO_BACKEND_PROXY_SECRET}"
EOF
      variable_commands=1
    fi

    if ! var_equals "PLATO_PUBLIC_ORIGIN" "$origin"; then
      if [ "$variable_commands" -eq 0 ]; then
        echo "  1. Set missing or invalid hosted variables without triggering partial deploys:"
      fi
      echo "       railway variables --service ${service} --environment ${environment} --skip-deploys --set 'PLATO_PUBLIC_ORIGIN=${origin}'"
      variable_commands=1
    fi

    if ! var_equals "NEXT_PUBLIC_PLATO_HOSTED_BILLING" "enabled"; then
      if [ "$variable_commands" -eq 0 ]; then
        echo "  1. Set missing or invalid hosted variables without triggering partial deploys:"
      fi
      echo "       railway variables --service ${service} --environment ${environment} --skip-deploys --set 'NEXT_PUBLIC_PLATO_HOSTED_BILLING=enabled'"
      variable_commands=1
    fi

    if [ "$variable_commands" -eq 0 ] && [ "$preflight_failed" -eq 1 ]; then
      cat <<EOF
  1. Resolve the hosted preflight errors or warnings printed above.
     Secret-valued variables such as Clerk keys, database URLs, Redis URLs, or LLM provider keys must be set in Railway manually.
EOF
    elif [ "$variable_commands" -eq 0 ]; then
      echo "  1. Hosted variables look complete in Railway."
    fi
  fi

  if [ "$variables_read_failed" -eq 1 ]; then
    cat <<EOF
  2. Re-run this read-only checker after Railway variables are readable.
EOF
  elif [ "$app_not_found_failed" -eq 1 ]; then
    cat <<EOF
  2. Restore the public domain routing/deployment for ${origin}.
     Reconnect the domain to the ${service} service, confirm the service has an active deployment, or redeploy the current checkout:
       railway up
EOF
  elif [ "$variable_commands" -eq 1 ]; then
    cat <<EOF
  2. Deploy the current checkout once after those variables are set:
       railway up
EOF
  elif [ "$build_log_failed" -eq 1 ] || [ "$deploy_log_failed" -eq 1 ]; then
    cat <<EOF
  2. Deploy the current checkout once so local warning fixes reach Railway:
       railway up
EOF
  elif [ "$preflight_failed" -eq 1 ]; then
    cat <<EOF
  2. Deploy the current checkout once after the preflight issues are resolved:
       railway up
EOF
  else
    cat <<EOF
  2. Fix the failed HTTP/page check above, or deploy the current checkout if the live service is stale:
       railway up
EOF
  fi

  if [ "$variables_read_failed" -eq 1 ] && [ "$app_not_found_failed" -eq 1 ]; then
    cat <<EOF
  3. Restore the public domain routing/deployment for ${origin}.
     Reconnect the domain to the ${service} service, confirm the service has an active deployment, or redeploy the current checkout:
       railway up
EOF
    if [ -s "$app_not_found_paths" ]; then
      cat <<EOF
     Routes that ended in Railway Application not found after retries:
EOF
      sort -u "$app_not_found_paths" | sed 's/^/       - /'
    fi
    cat <<EOF
  4. Re-run this read-only checker with log scanning enabled:
       bash dashboard/scripts/check-production-readiness.sh --service ${service} --environment ${environment} --origin ${origin}
EOF
    return
  fi

  if [ "$app_not_found_failed" -eq 1 ] && [ -s "$app_not_found_paths" ]; then
    cat <<EOF
     Routes that ended in Railway Application not found after retries:
EOF
    sort -u "$app_not_found_paths" | sed 's/^/       - /'
  fi

  cat <<EOF
  3. Re-run this read-only checker with log scanning enabled:
       bash dashboard/scripts/check-production-readiness.sh --service ${service} --environment ${environment} --origin ${origin}
EOF
}

probe_page() {
  local path="$1"
  local label="$2"
  local expected_marker="$3"
  local body="${tmp_dir}/page-${label}.html"
  local code

  code="$(fetch_with_retries "$body" "${origin}${path}" "200" "1" "$path")"
  printf 'HTTP %s %s%s\n' "$code" "$origin" "$path"
  if [ "$code" != "200" ]; then
    if [ "$code" = "404" ] && grep -Fq "Application not found" "$body"; then
      record_app_not_found "$path"
    fi
    echo "expected ${path} to resolve to a 200 page after redirects" >&2
    mark_failed
    return
  fi
  if grep -Eiq 'Application error|Internal Server Error|NEXT_NOT_FOUND|500 Internal|Unhandled Runtime Error' "$body"; then
    echo "${path} rendered an app-error marker" >&2
    mark_failed
  fi
  if grep -Eiq 'login-auth-config-error|account-auth-config-error|organization-auth-config-error|billing-auth-config-error|account-settings-fallback|organization-settings-fallback|Hosted billing disabled|hosted config error|Billing data needs attention|billing warning' "$body"; then
    echo "${path} rendered a hosted SaaS/Lab fallback or warning marker" >&2
    mark_failed
  fi
  if [ -n "$expected_marker" ] && ! grep -Fq "$expected_marker" "$body"; then
    echo "${path} did not render expected hosted marker: ${expected_marker}" >&2
    mark_failed
  fi
}

section "Hosted SaaS/Lab preflight"
if ! read_railway_variables; then
  echo "failed to read Railway variables" >&2
  printf '{}\n' >"$variables_json"
  variables_read_failed=1
  preflight_failed=1
  mark_failed
elif ! python3 "$preflight_checker" --source railway --hosted-required --strict <"$variables_json"; then
  preflight_failed=1
  mark_failed
fi

section "Live health"
health_body="${tmp_dir}/health.json"
health_code="$(fetch_with_retries "$health_body" "${origin}/api/v1/health" "200" "0" "/api/v1/health")"
cat "$health_body" || true
printf '\nHTTP %s %s/api/v1/health\n' "$health_code" "$origin"
if [ "$health_code" != "200" ] || ! grep -q '"ok"[[:space:]]*:[[:space:]]*true' "$health_body"; then
  if [ "$health_code" = "404" ] && grep -Fq "Application not found" "$health_body"; then
    record_app_not_found "/api/v1/health"
  fi
  echo "health check failed" >&2
  mark_failed
fi

section "Signed-out auth status"
auth_body="${tmp_dir}/auth-me.json"
auth_code="$(fetch_with_retries "$auth_body" "${origin}/api/v1/auth/me" "200" "0" "/api/v1/auth/me")"
cat "$auth_body" || true
printf '\nHTTP %s %s/api/v1/auth/me\n' "$auth_code" "$origin"
if [ "$auth_code" != "200" ] ||
  ! grep -q '"auth_required"[[:space:]]*:[[:space:]]*true' "$auth_body" ||
  ! grep -q '"user_id"[[:space:]]*:[[:space:]]*null' "$auth_body"; then
  if [ "$auth_code" = "404" ] && grep -Fq "Application not found" "$auth_body"; then
    record_app_not_found "/api/v1/auth/me"
  fi
  echo "expected signed-out /api/v1/auth/me to report auth_required=true and user_id=null" >&2
  mark_failed
fi

section "Unauthenticated projects boundary"
projects_body="${tmp_dir}/projects.json"
projects_code="$(fetch_with_retries "$projects_body" "${origin}/api/v1/projects" "401" "0" "/api/v1/projects")"
cat "$projects_body" || true
printf '\nHTTP %s %s/api/v1/projects\n' "$projects_code" "$origin"
if [ "$projects_code" != "401" ]; then
  if [ "$projects_code" = "404" ] && grep -Fq "Application not found" "$projects_body"; then
    record_app_not_found "/api/v1/projects"
  fi
  echo "expected unauthenticated /api/v1/projects to return 401" >&2
  mark_failed
fi

section "Hosted user/Lab pages"
probe_page "/login" "login" "data-clerk-publishable-key"
probe_page "/settings/account" "account" "data-clerk-publishable-key"
probe_page "/settings/organization" "organization" "data-clerk-publishable-key"
probe_page "/settings/billing" "billing" "data-clerk-publishable-key"

if [ "$skip_logs" != "1" ]; then
  bad_log_pattern='warning|warn|error|failed|deprecated|deprecation|backtracking|taking longer|looking at multiple versions|traceback|exception|curl: \([0-9]+\)'

  section "Railway build logs"
  build_log="${tmp_dir}/railway-build.log"
  if railway logs --service "$service" --environment "$environment" --build --lines "$lines" >"$build_log"; then
    if grep -Eini "$bad_log_pattern" "$build_log"; then
      echo "build log scan found warning/error markers" >&2
      build_log_failed=1
      mark_failed
    else
      echo "build log scan clean"
    fi
  else
    echo "failed to read Railway build logs" >&2
    mark_failed
  fi

  section "Railway deployment logs"
  deploy_log="${tmp_dir}/railway-deploy.log"
  if railway logs --service "$service" --environment "$environment" --deployment --lines "$lines" >"$deploy_log"; then
    if grep -Eini "$bad_log_pattern" "$deploy_log"; then
      echo "deployment log scan found warning/error markers" >&2
      deploy_log_failed=1
      mark_failed
    else
      echo "deployment log scan clean"
    fi
  else
    echo "failed to read Railway deployment logs" >&2
    mark_failed
  fi
fi

section "Result"
if [ "$status" -eq 0 ]; then
  echo "OK: production readiness checks passed."
else
  print_remediation
  echo "Production readiness checks failed." >&2
fi

exit "$status"
