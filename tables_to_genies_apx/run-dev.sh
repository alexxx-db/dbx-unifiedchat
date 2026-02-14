#!/bin/bash
# APX App Development Server Launcher
# Starts both FastAPI backend and React frontend (Vite dev server)

set -e

PROJECT_ROOT=$(cd "$(dirname "$0")" && pwd)
BACKEND_DIR="$PROJECT_ROOT/src/tables_genies/backend"
FRONTEND_DIR="$PROJECT_ROOT/src/tables_genies/ui"

echo "🚀 Starting Tables to Genies APX App (Development Mode)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Clean up any existing processes
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    if [ ! -z "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ] && kill -0 $FRONTEND_PID 2>/dev/null; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    echo "✅ Cleanup complete"
}
trap cleanup EXIT INT TERM

# Start Backend (FastAPI on port 8000)
echo ""
echo "📦 Starting FastAPI backend on http://localhost:8000"
echo "   API docs: http://localhost:8000/docs"
echo "   Health:   http://localhost:8000/health"
echo ""
cd "$PROJECT_ROOT"
python3 -m uvicorn src.tables_genies.backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload &
BACKEND_PID=$!

# Wait for backend to start and stabilize
sleep 4

# Start Frontend (Vite dev server)
echo ""
echo "⚛️  Starting React frontend (Vite dev server)"
cd "$FRONTEND_DIR"
bun run dev &
FRONTEND_PID=$!

# Wait for frontend to start
sleep 3

# Display final startup info
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Servers are running!"
echo ""
echo "📱 Frontend:   http://localhost:5173 (or 3000+ if in use)"
echo "🔌 Backend:    http://localhost:8000"
echo "📚 API Docs:   http://localhost:8000/docs"
echo "❤️  Health:    http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop both servers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Wait for all background jobs
wait
