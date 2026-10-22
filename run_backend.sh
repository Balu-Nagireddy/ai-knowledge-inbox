#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Backend virtual environment not found: $VENV_DIR" >&2
  echo "Run ./setup.sh first." >&2
  exit 1
fi

cd "$BACKEND_DIR"
exec "$VENV_DIR/bin/python" -m uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --reload
