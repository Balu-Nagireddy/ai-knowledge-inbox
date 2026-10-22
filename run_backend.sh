#!/usr/bin/env bash
echo "Starting AI Knowledge Inbox Backend..."
cd "$(dirname "$0")/backend"
./venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
