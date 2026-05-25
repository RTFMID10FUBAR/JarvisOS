#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup-backend.sh — Prepare the GhostMesh FastAPI backend for Electron packaging
#
# Run this once before `npm run build:all` or `npm run dist:mac`.
# It creates a self-contained Python venv inside ghostmesh/backend/venv/ so
# electron-builder can bundle it without requiring Python on the end-user's machine.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../backend" && pwd)"
VENV_DIR="$BACKEND_DIR/venv"
REQS="$BACKEND_DIR/requirements.txt"

echo "==> Backend directory : $BACKEND_DIR"
echo "==> Venv directory    : $VENV_DIR"

# Check for Python 3.10+
PYTHON="${PYTHON:-python3}"
PY_VERSION=$("$PYTHON" -c 'import sys; print(sys.version_info[:2])')
echo "==> Python version    : $PY_VERSION"

if ! "$PYTHON" -c 'import sys; assert sys.version_info >= (3,10)' 2>/dev/null; then
  echo "ERROR: Python 3.10 or newer is required."
  exit 1
fi

# Create or recreate venv
if [ -d "$VENV_DIR" ]; then
  echo "==> Removing existing venv..."
  rm -rf "$VENV_DIR"
fi

echo "==> Creating venv..."
"$PYTHON" -m venv "$VENV_DIR"

PIP="$VENV_DIR/bin/pip"

echo "==> Upgrading pip..."
"$PIP" install --upgrade pip --quiet

if [ -f "$REQS" ]; then
  echo "==> Installing requirements from $REQS..."
  "$PIP" install -r "$REQS" --quiet
else
  echo "==> No requirements.txt found — installing core deps directly..."
  "$PIP" install fastapi uvicorn httpx python-dotenv --quiet
fi

echo ""
echo "✓ Backend venv ready at $VENV_DIR"
echo ""
echo "Next steps:"
echo "  cd $(dirname "$SCRIPT_DIR")/electron"
echo "  npm install"
echo "  npm run build:frontend   # builds the React app"
echo "  npm run dist:mac         # creates .dmg + .zip in dist/"
