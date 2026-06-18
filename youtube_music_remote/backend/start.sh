#!/usr/bin/env bash
# Start the JarvisOS YouTube Music Remote on this computer.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found." >&2
  exit 1
fi

python3 -m pip install -r requirements.txt -q
exec python3 main.py
