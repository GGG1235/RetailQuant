#!/bin/bash
# Start the backtest system: backend API + frontend dev server

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> 启动后端 API (Flask on :5000)"
cd "$SCRIPT_DIR/backend"
.venv/bin/python app.py &
BACKEND_PID=$!

echo "==> 启动前端开发服务器 (Vite on :5173)"
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "后端: http://localhost:5000"
echo "前端: http://localhost:5173"
echo ""
echo "按 Ctrl+C 停止所有服务"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
