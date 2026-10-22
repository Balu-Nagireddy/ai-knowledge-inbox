#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

# Windows Git Bash uses Scripts/python.exe; macOS/Linux uses bin/python.
if [[ -f "$VENV_DIR/Scripts/python.exe" ]]; then
  VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
elif [[ -f "$VENV_DIR/bin/python" ]]; then
  VENV_PYTHON="$VENV_DIR/bin/python"
else
  echo "Backend virtual environment not found or incomplete: $VENV_DIR" >&2
  echo "Run bash setup.sh first, or on Windows run setup.bat." >&2
  exit 1
fi

cd "$BACKEND_DIR"
exec "$VENV_PYTHON" -m uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --reload
