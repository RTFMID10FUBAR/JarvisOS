#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
fi

echo "Starting GhostMesh API on http://0.0.0.0:8000"
python3 main.py
