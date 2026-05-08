#!/usr/bin/env bash
set -e

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

# ── Python backend ────────────────────────────────────────────────────────────
echo "[valmiki] Syncing Python deps..."
uv sync --extra dev --quiet

# ── Node frontend ─────────────────────────────────────────────────────────────
if [ ! -d "story_viewer/node_modules" ]; then
  echo "[valmiki] Installing Node deps..."
  (cd story_viewer && npm install --silent)
fi

mkdir -p output

# ── Launch both ───────────────────────────────────────────────────────────────
echo "[valmiki] Starting backend on :8642 and frontend on :5173"
echo "[valmiki] Ctrl+C to stop both."
echo ""

trap 'kill %1 %2 2>/dev/null; exit 0' INT TERM

.venv/bin/uvicorn server:app --reload --port 8642 &
(cd story_viewer && npm run dev) &

# Open browser once Vite is ready (WSL2 / Linux / macOS)
(
  sleep 3
  if grep -qi microsoft /proc/version 2>/dev/null; then
    explorer.exe "http://localhost:5173/" 2>/dev/null || true
  elif command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:5173/"
  elif command -v open &>/dev/null; then
    open "http://localhost:5173/"
  fi
) &

wait
