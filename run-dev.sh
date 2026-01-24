#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "${ROOT_DIR}/.env.local" ]]; then
  echo "Missing .env.local in project root" >&2
  exit 1
fi

if [[ ! -d "${ROOT_DIR}/.venv" ]]; then
  echo "Missing .venv. Create it with: python -m venv .venv" >&2
  exit 1
fi

# Load env vars for Django
set -a
source "${ROOT_DIR}/.env.local"
set +a

# Activate venv
source "${ROOT_DIR}/.venv/bin/activate"

# Start backend
pushd "${ROOT_DIR}" >/dev/null
python manage.py runserver 0.0.0.0:8000 &
BACK_PID=$!
popd >/dev/null

# Start frontend
pushd "${ROOT_DIR}/techtracker_vue" >/dev/null
npm run serve &
FRONT_PID=$!
popd >/dev/null

cleanup() {
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT

wait "$BACK_PID" "$FRONT_PID"
