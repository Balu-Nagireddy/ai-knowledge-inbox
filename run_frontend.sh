#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

command -v npm >/dev/null 2>&1 || { echo "npm is required. Install Node.js LTS first." >&2; exit 1; }
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Frontend dependencies are missing. Run ./setup.sh first." >&2
  exit 1
fi

cd "$FRONTEND_DIR"
exec npm run dev
