#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"

# ---- colour helpers ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ---- check prerequisites ----
command -v uv  >/dev/null 2>&1 || err "uv not found — install it first: https://docs.astral.sh/uv/"
command -v npm >/dev/null 2>&1 || err "npm not found — install Node.js first"

# ---- data check ----
if [ ! -d "$SCRIPT_DIR/data/daily" ] || [ -z "$(ls -A "$SCRIPT_DIR/data/daily" 2>/dev/null)" ]; then
    warn "data/daily/ is empty or missing"
    warn "Please add daily parquet files and contract.json to data/ before running backtests."
    warn "The server will start but return an empty stock list."
fi

# ---- backend setup ----
echo ""
echo "========== Backend =========="
cd "$SCRIPT_DIR/backend"

if [ ! -d ".venv" ]; then
    log "Creating Python virtual environment ..."
    uv venv
fi

log "Installing / updating Python dependencies ..."
uv pip install flask flask-cors polars pytest -q --index-url "$MIRROR" 2>&1 | tail -1
uv pip install vnpy -q --index-url "$MIRROR" 2>&1 | tail -1
uv pip install alphalens-reloaded scipy scikit-learn pyarrow -q --index-url "$MIRROR" 2>&1 | tail -1

log "Starting backend (Flask on :5000) ..."
.venv/bin/python app.py &
BACKEND_PID=$!

# ---- frontend setup ----
echo ""
echo "========== Frontend ========="
cd "$SCRIPT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    log "Installing Node dependencies ..."
    npm install --silent
fi

log "Starting frontend (Vite on :5173) ..."
npm run dev -- --host &
FRONTEND_PID=$!

# ---- ready ----
echo ""
echo "=============================================="
echo "  Backend  → http://localhost:5000"
echo "  Frontend → http://localhost:5173"
echo "  Press Ctrl+C to stop all services"
echo "=============================================="
echo ""

cleanup() {
    echo ""
    log "Shutting down ..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup INT TERM
wait
