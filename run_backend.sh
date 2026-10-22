#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
cd "$BACKEND_DIR"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "Error: Python 3.10+ is required." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then "$PYTHON_BIN" -m venv .venv; fi
VENV_PYTHON=".venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Error: $VENV_PYTHON is missing. On Windows, use run_backend.bat." >&2
  exit 1
fi

if [[ "${INSTALL_DEPS:-1}" == "1" ]]; then
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -r requirements.txt
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created backend/.env. Add GEMINI_API_KEY for live Gemini responses."
fi

exec "$VENV_PYTHON" -m uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --reload
