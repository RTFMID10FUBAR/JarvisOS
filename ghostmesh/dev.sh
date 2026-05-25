#!/bin/bash
# Start GhostMesh in development mode (both frontend and backend)
# Usage: ./dev.sh [port]
#   port — optional backend port (default 8080)
#          e.g.  ./dev.sh 9090   or   GHOSTMESH_PORT=9090 ./dev.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Allow port override via arg or env var
if [ -n "$1" ]; then
  export GHOSTMESH_PORT="$1"
fi
export GHOSTMESH_PORT="${GHOSTMESH_PORT:-8080}"

echo "Starting GhostMesh (backend port $GHOSTMESH_PORT)..."

# Start backend in background
if command -v python3 >/dev/null 2>&1; then
    (
        cd "$SCRIPT_DIR/backend"
        if [ -f .env ]; then
            set -a
            # shellcheck disable=SC1091
            source .env
            set +a
        fi
        pip3 install -r requirements.txt -q 2>/dev/null
        GHOSTMESH_PORT="$GHOSTMESH_PORT" python3 main.py &
        echo "Backend PID: $!"
    )
else
    echo "Python3 not found — backend will not start. Frontend will use offline mock data."
fi

# Start frontend (Vite proxy reads GHOSTMESH_PORT automatically)
cd "$SCRIPT_DIR/frontend"
if [ ! -d node_modules ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

echo ""
echo "GhostMesh Frontend : http://localhost:5173"
echo "GhostMesh API      : http://localhost:$GHOSTMESH_PORT"
echo "LAN Frontend (S24) : http://$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}'):5173"
echo ""

npm run dev
