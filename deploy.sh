#!/usr/bin/env bash
set -e

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

# ── Python backend ────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "[valmiki] Creating venv..."
  uv venv
fi

echo "[valmiki] Installing Python deps..."
uv pip install -e ".[dev]" --quiet

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

wait
