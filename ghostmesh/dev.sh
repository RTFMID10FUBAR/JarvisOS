#!/bin/bash
# Start GhostMesh in development mode (both frontend and backend)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting GhostMesh..."

# Start backend in background
if command -v python3 >/dev/null 2>&1; then
    (
        cd "$SCRIPT_DIR/backend"
        if [ -f .env ]; then
            export $(grep -v '^#' .env | xargs 2>/dev/null)
        fi
        pip3 install -r requirements.txt -q
        python3 main.py &
        echo "Backend PID: $!"
    )
else
    echo "Python3 not found — backend will not start. Frontend will use offline mock data."
fi

# Start frontend
cd "$SCRIPT_DIR/frontend"
if [ ! -d node_modules ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

echo ""
echo "GhostMesh Frontend: http://localhost:5173"
echo "GhostMesh API:      http://localhost:8000"
echo ""

npm run dev
