#!/usr/bin/env bash
# Run backend (uvicorn, :8000) and frontend (vite, :5173) locally without Docker.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Missing .env - copy .env.example and set REDIS_URL"; exit 1
fi

if [ ! -x .venv/bin/uvicorn ]; then
  [ -x .venv/bin/python ] || python3.12 -m venv .venv 2>/dev/null || python3 -m venv .venv
  .venv/bin/pip install -r backend/requirements.txt
fi

[ -d frontend/node_modules ] || (cd frontend && npm install)

trap 'kill 0' EXIT
.venv/bin/uvicorn backend.main:app --reload --port 8000 &
(cd frontend && npm run dev) &
wait
