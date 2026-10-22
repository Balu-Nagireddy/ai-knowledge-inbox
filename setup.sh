#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || { echo "Python 3.10+ is required." >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Node.js and npm are required." >&2; exit 1; }
if command -v python3 >/dev/null 2>&1; then PYTHON=python3; else PYTHON=python; fi

"$PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required; found " + sys.version.split()[0])
print("Python", sys.version.split()[0])
PY

if [[ ! -d "$BACKEND_DIR/.venv" ]]; then "$PYTHON" -m venv "$BACKEND_DIR/.venv"; fi
"$BACKEND_DIR/.venv/bin/python" -m pip install --upgrade pip
"$BACKEND_DIR/.venv/bin/python" -m pip install -r "$BACKEND_DIR/requirements.txt"
if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  echo "Created backend/.env from backend/.env.example. Add GEMINI_API_KEY to enable Gemini."
fi
cd "$FRONTEND_DIR"
if [[ -f package-lock.json ]]; then npm ci; else npm install; fi

echo
echo "Setup complete."
echo "Terminal 1: bash run_backend.sh"
echo "Terminal 2: bash run_frontend.sh"
echo "API docs: http://127.0.0.1:8000/docs"
