#!/usr/bin/env bash
# Plato Dashboard — real LLM smoke test.
#
# Once a real provider key is configured (env var, ~/.plato/keys.json, or
# /api/v1/keys), this script triggers a fast-mode idea run and tails the
# SSE event stream until the run finishes. Total wall-time: ~30-60s on
# Gemini Flash, ~$0.001 per run.
#
# Usage:
#   bash scripts/run-real-smoke.sh           # Gemini (cheapest)
#   PROVIDER=openai bash scripts/run-real-smoke.sh
#   PROVIDER=anthropic bash scripts/run-real-smoke.sh

set -euo pipefail

API="${PLATO_API:-http://127.0.0.1:7878/api/v1}"
PID="${PID:-$(cat /tmp/plato-smoke-pid.txt 2>/dev/null || echo '')}"
PROVIDER="${PROVIDER:-gemini}"

if [ -z "$PID" ]; then
  echo "→ Creating a fresh project…"
  PID=$(curl -sX POST "$API/projects" -H "Content-Type: application/json" \
    -d '{"name":"real-llm-smoke","data_description":"Stellar luminosity vs distance from Hipparcos. Tools: pandas, numpy, matplotlib, astropy."}' \
    | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
fi
echo "Project: $PID"

# Step 1 — verify a key is configured.
status=$(curl -s "$API/keys/status")
echo ""
echo "Key status: $status"
case "$PROVIDER" in
  gemini)   key_field="GEMINI";    model="gemini-2.0-flash" ;;
  openai)   key_field="OPENAI";    model="gpt-4.1-mini"     ;;
  anthropic) key_field="ANTHROPIC"; model="claude-3.7-sonnet" ;;
  *) echo "Unknown PROVIDER=$PROVIDER (use gemini|openai|anthropic)"; exit 2 ;;
esac
state=$(echo "$status" | python3 -c "import sys, json; print(json.load(sys.stdin).get('$key_field', 'unset'))")
if [ "$state" = "unset" ]; then
  echo ""
  echo "✗ No $key_field key configured. Add one first:"
  echo ""
  echo "    # Option A — UI:"
  echo "    open http://localhost:3001/keys"
  echo ""
  echo "    # Option B — curl:"
  echo "    curl -X PUT $API/keys -H 'Content-Type: application/json' \\"
  echo "      -d '{\"$key_field\": \"<your-key>\"}'"
  echo ""
  echo "    # Option C — env var (then restart backend):"
  case "$PROVIDER" in
    gemini)    echo "    export GOOGLE_API_KEY=<your-key>" ;;
    openai)    echo "    export OPENAI_API_KEY=<your-key>" ;;
    anthropic) echo "    export ANTHROPIC_API_KEY=<your-key>" ;;
  esac
  echo "    pkill -f 'uvicorn plato_dashboard.api.server'"
  echo "    cd dashboard/backend && source .venv/bin/activate"
  echo "    nohup python -m uvicorn plato_dashboard.api.server:app --port 7878 &"
  exit 1
fi

# Step 2 — live ping the provider to validate the key.
echo ""
echo "→ Live-pinging $PROVIDER…"
curl -sX POST "$API/keys/test/$key_field" | python3 -m json.tool

# Step 3 — start the run.
echo ""
echo "→ Starting fast-mode idea run with $model…"
RUN=$(curl -sX POST "$API/projects/$PID/stages/idea/run" \
  -H "Content-Type: application/json" \
  -d "{\"mode\":\"fast\",\"models\":{\"llm\":\"$model\"}}" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Run ID: $RUN"
echo ""

# Step 4 — tail SSE.
echo "→ Tailing SSE (max 120s)…"
echo "─────────────────────────────────────────────────────────────"
( curl -sN -H "Accept: text/event-stream" \
  "$API/projects/$PID/runs/$RUN/events" 2>/dev/null \
  & SSE_PID=$!
  sleep 120
  kill $SSE_PID 2>/dev/null ) | python3 -c '
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line.startswith("data:"):
        continue
    try:
        evt = json.loads(line[5:].strip())
    except Exception:
        continue
    kind = evt.get("kind", "?")
    if kind == "log.line":
        agent = evt.get("agent") or evt.get("source", "")
        text = (evt.get("text") or "")[:120]
        print(f"  {agent:14} | {text}")
    elif kind == "node.entered":
        print(f"→ {evt.get(\"name\")}")
    elif kind == "tokens.delta":
        m = evt.get("model", "?")
        p, c = evt.get("prompt", 0), evt.get("completion", 0)
        print(f"  ── tokens: +{p} in / +{c} out ({m})")
    elif kind == "stage.finished":
        print(f"\n✓ Finished: {evt.get(\"status\")}")
        sys.exit(0)
    elif kind == "error":
        print(f"\n✗ Error: {evt.get(\"message\", \"\")[:200]}")
'

echo ""
echo "─────────────────────────────────────────────────────────────"
echo "→ Final idea on disk:"
echo ""
cat ~/.plato/projects/$PID/input_files/idea.md 2>/dev/null | head -30 || echo "  (idea.md not written — check error above)"
echo ""
echo "Open http://localhost:3001/ to see it in the dashboard."
