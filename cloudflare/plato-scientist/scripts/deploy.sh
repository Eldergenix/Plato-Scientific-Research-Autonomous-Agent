#!/usr/bin/env bash
# Deploy the Plato scientist to Cloudflare (https://jarvisos.xyz) backed by Supabase Postgres.
#
# Required environment (never commit these):
#   PLATO_DATABASE_URL   Supabase *session pooler* URI, port 5432, with ?sslmode=require
#                        (session mode is required: runs hold session-level advisory locks)
#   ANTHROPIC_API_KEY    Anthropic API key
#   CLOUDFLARE_API_TOKEN or a prior `npx wrangler login`; the account must own the jarvisos.xyz zone
# Optional:
#   PLATO_API_TOKEN      bearer token for the UI/API (generated and printed once if unset)
#   PLATO_INTERNAL_TOKEN Worker -> Container shared secret (generated if unset)
#   PLATO_SECRETS_KEY_FILE  where the account secrets key is kept on this machine
#                        (default ~/.config/plato/secrets-key). The key derives the password
#                        pepper and encrypts saved API keys; it is set once and never replaced.
#   E2B_API_KEY          E2B key: agents then run experiments in E2B sandboxes built from the
#                        plato-lab template (python scripts/e2b_lab_template.py). Without it,
#                        experiments run in the container's own sandbox.
#   SKIP_MIGRATIONS=1    skip applying the schema from this machine (the container also migrates on start)
#
# Needs: node/npm, docker (wrangler builds and pushes the container image), python3 with asyncpg for migrations.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(cd ../.. && pwd)"

: "${PLATO_DATABASE_URL:?set PLATO_DATABASE_URL (Supabase session pooler URI)}"
: "${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY}"
case "$PLATO_DATABASE_URL" in
  *:6543/*) echo "PLATO_DATABASE_URL points at the transaction pooler (6543); use the session pooler (5432)." >&2; exit 1;;
esac

npm ci --no-audit --no-fund
npx wrangler whoami >/dev/null || { echo "Not authenticated: run 'npx wrangler login' or export CLOUDFLARE_API_TOKEN." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker must be running: wrangler builds the container image locally." >&2; exit 1; }

if [[ "${SKIP_MIGRATIONS:-0}" != "1" ]]; then
  echo "Applying database migrations..."
  (cd "$ROOT" && PLATO_DATABASE_URL="$PLATO_DATABASE_URL" python3 -m plato.scientist.db.migrate)
fi

echo "Ensuring Hyperdrive config 'plato-supabase'..."
HD_ID="$(npx wrangler hyperdrive list 2>/dev/null | grep -E '\bplato-supabase\b' | grep -oE '[0-9a-f]{32}' | head -n1 || true)"
if [[ -z "$HD_ID" ]]; then
  # Caching off: the UI polls campaign status, and cached reads showed stale phases for minutes.
  HD_ID="$(npx wrangler hyperdrive create plato-supabase --connection-string="$PLATO_DATABASE_URL" \
    --caching-disabled | grep -oE '[0-9a-f]{32}' | head -n1)"
fi
[[ "$HD_ID" =~ ^[0-9a-f]{32}$ ]] || { echo "Could not determine the Hyperdrive id." >&2; exit 1; }
npx wrangler hyperdrive update "$HD_ID" --caching-disabled >/dev/null  # also for a reused config
sed -i.bak -E "s/(\"id\": \")[0-9a-f]{32}(\")/\1${HD_ID}\2/" wrangler.jsonc && rm -f wrangler.jsonc.bak
echo "Hyperdrive: $HD_ID"

GENERATED_API_TOKEN=""
if [[ -z "${PLATO_API_TOKEN:-}" ]]; then
  PLATO_API_TOKEN="$(openssl rand -hex 32)"; GENERATED_API_TOKEN=1
fi
PLATO_INTERNAL_TOKEN="${PLATO_INTERNAL_TOKEN:-$(openssl rand -hex 32)}"

echo "Deploying Worker + Container..."
npm run deploy  # immediate container rollout; in-flight campaigns resume from Postgres

# PLATO_SECRETS_KEY: replacing it would invalidate every password and saved API key, so it is
# only ever uploaded when the Worker doesn't have one. A copy stays on this machine (mode 600)
# so a re-created Worker can be given the same key.
KEY_FILE="${PLATO_SECRETS_KEY_FILE:-$HOME/.config/plato/secrets-key}"
LISTED="$(npx wrangler secret list --format json)" || { echo "Could not list the Worker's secrets; not touching PLATO_SECRETS_KEY." >&2; exit 1; }
HAS_KEY="$(printf '%s' "$LISTED" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const j=JSON.parse(s.slice(s.indexOf("["),s.lastIndexOf("]")+1));process.stdout.write(j.some(x=>x.name==="PLATO_SECRETS_KEY")?"1":"0")})')" \
  || { echo "Could not read the Worker's secret list; not touching PLATO_SECRETS_KEY." >&2; exit 1; }
NEW_SECRETS_KEY=""
if [[ "$HAS_KEY" == "1" ]]; then
  echo "PLATO_SECRETS_KEY is already set on the Worker; keeping it."
else
  if [[ -s "$KEY_FILE" ]]; then
    NEW_SECRETS_KEY="$(tr -d '[:space:]' < "$KEY_FILE")"; echo "Restoring PLATO_SECRETS_KEY from $KEY_FILE."
  else
    NEW_SECRETS_KEY="$(openssl rand -base64 32)"
    (umask 077 && mkdir -p "$(dirname "$KEY_FILE")" && printf '%s\n' "$NEW_SECRETS_KEY" > "$KEY_FILE")
    echo "Generated PLATO_SECRETS_KEY; a copy is in $KEY_FILE (back it up, never commit it)."
  fi
  [[ "$(printf '%s' "$NEW_SECRETS_KEY" | openssl base64 -d -A 2>/dev/null | wc -c)" -ge 32 ]] || { echo "PLATO_SECRETS_KEY must be base64 of at least 32 bytes." >&2; exit 1; }
fi

SECRETS="$(mktemp)"; chmod 600 "$SECRETS"; trap 'rm -f "$SECRETS"' EXIT
PLATO_API_TOKEN="$PLATO_API_TOKEN" PLATO_INTERNAL_TOKEN="$PLATO_INTERNAL_TOKEN" NEW_SECRETS_KEY="$NEW_SECRETS_KEY" E2B_API_KEY="${E2B_API_KEY:-}" node -e '
  const e = process.env;
  process.stdout.write(JSON.stringify({
    PLATO_API_TOKEN: e.PLATO_API_TOKEN, PLATO_INTERNAL_TOKEN: e.PLATO_INTERNAL_TOKEN,
    ANTHROPIC_API_KEY: e.ANTHROPIC_API_KEY, PLATO_DATABASE_URL: e.PLATO_DATABASE_URL,
    ...(e.NEW_SECRETS_KEY ? { PLATO_SECRETS_KEY: e.NEW_SECRETS_KEY } : {}),
    ...(e.E2B_API_KEY ? { E2B_API_KEY: e.E2B_API_KEY } : {}),
  }));' > "$SECRETS"
npx wrangler secret bulk "$SECRETS"

echo "Smoke test..."
for i in $(seq 1 30); do
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "authorization: Bearer $PLATO_API_TOKEN" https://jarvisos.xyz/api/health || true)"
  [[ "$code" == "200" ]] && break
  sleep 5
done
curl -fsS -H "authorization: Bearer $PLATO_API_TOKEN" https://jarvisos.xyz/api/health && echo
# Signed out, /api/me answers {"account":null} (the UI then shows sign-in).
[[ "$(curl -fsS https://jarvisos.xyz/api/me)" == '{"account":null}' ]] || { echo "GET /api/me did not answer signed-out." >&2; exit 1; }
curl -fsS -o /dev/null https://jarvisos.xyz/app/main.js || { echo "UI assets missing." >&2; exit 1; }
if [[ -n "$GENERATED_API_TOKEN" ]]; then
  echo "Generated PLATO_API_TOKEN (store it in your password manager; it is not shown again):"
  echo "$PLATO_API_TOKEN"
fi
