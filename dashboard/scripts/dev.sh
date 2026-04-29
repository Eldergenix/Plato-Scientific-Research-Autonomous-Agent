#!/usr/bin/env bash
# Plato Dashboard — dev launcher.
# Boots the FastAPI backend and Next.js frontend in two background processes,
# tails both logs to stdout, and traps Ctrl-C to bring them down cleanly.

set -euo pipefail
cd "$(dirname "$0")/.."

ROOT="$(pwd)"
BACKEND_PORT="${PLATO_PORT:-7878}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "→ Plato Dashboard dev launcher"
echo "  backend  http://127.0.0.1:${BACKEND_PORT}"
echo "  frontend http://localhost:${FRONTEND_PORT}"
echo ""

# Backend
if [ ! -d "backend/.venv" ]; then
  echo "→ Creating backend venv (Python 3.13)…"
  /opt/homebrew/bin/python3.13 -m venv backend/.venv
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q -e backend
fi

# Frontend
if [ ! -d "frontend/node_modules" ]; then
  echo "→ Installing frontend deps…"
  (cd frontend && npm install --silent)
fi

echo "→ Starting backend on :${BACKEND_PORT}…"
PLATO_PORT="$BACKEND_PORT" \
  backend/.venv/bin/python -m uvicorn plato_dashboard.api.server:app \
    --host 127.0.0.1 --port "$BACKEND_PORT" \
    > /tmp/plato-dashboard-backend.log 2>&1 &
BACKEND_PID=$!

echo "→ Starting frontend on :${FRONTEND_PORT}…"
(cd frontend && PORT="$FRONTEND_PORT" npm run dev > /tmp/plato-dashboard-frontend.log 2>&1) &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "→ Shutting down…"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

# Tail logs
sleep 1.5
echo ""
echo "─── tailing logs (Ctrl-C to stop) ────────────────────────────────────"
tail -F /tmp/plato-dashboard-backend.log /tmp/plato-dashboard-frontend.log
