#!/usr/bin/env bash
# =============================================================================
# run_dev.sh -- start the WHOLE system with one command.
# =============================================================================
# Launches:
#   1. the FastAPI backend (REST + WebSocket) on http://127.0.0.1:8000
#   2. the React dashboard (Vite dev server) on http://localhost:5173
#
# Usage (from the project root):   bash scripts/run_dev.sh
# Press Ctrl+C to stop BOTH servers.
#
# Works on macOS/Linux and on Windows via Git Bash. It auto-detects the Python
# virtual environment location (Scripts on Windows, bin elsewhere).
# =============================================================================

set -e

# Move to the project root (the folder ABOVE this scripts/ folder).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# --- Find the virtual environment's Python ---------------------------------
if [ -f ".venv/Scripts/python.exe" ]; then
  PYTHON=".venv/Scripts/python.exe"        # Windows
elif [ -f ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"                # macOS / Linux
else
  echo "!! No virtual environment found. Create one first:"
  echo "     python -m venv .venv"
  echo "     .venv/Scripts/pip install -r requirements.txt   (Windows)"
  echo "     .venv/bin/pip install -r requirements.txt       (macOS/Linux)"
  exit 1
fi

# --- Make sure the model is trained (so predictions work immediately) -------
if [ ! -f "ml/artifacts/model.joblib" ]; then
  echo ">> No trained model found. Training on synthetic data (takes seconds)..."
  "$PYTHON" ml/train.py
fi

# --- Start the backend ------------------------------------------------------
echo ">> Starting backend on http://127.0.0.1:8000 ..."
"$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# --- Start the frontend -----------------------------------------------------
echo ">> Starting dashboard on http://localhost:5173 ..."
cd frontend
# Install node modules the first time.
if [ ! -d "node_modules" ]; then
  echo ">> Installing frontend dependencies (first run only)..."
  npm install
fi
npm run dev &
FRONTEND_PID=$!
cd "$ROOT_DIR"

# --- Clean shutdown: kill both servers when this script is stopped ----------
cleanup() {
  echo ""
  echo ">> Shutting down..."
  kill "$BACKEND_PID" 2>/dev/null || true
  kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "============================================================"
echo "  Backend : http://127.0.0.1:8000  (docs at /docs)"
echo "  Dashboard: http://localhost:5173"
echo "  Press Ctrl+C to stop both."
echo "============================================================"

# Wait so Ctrl+C reaches this script (and triggers cleanup).
wait
