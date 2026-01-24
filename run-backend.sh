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

# Migrations
pushd "${ROOT_DIR}" >/dev/null
python manage.py migrate

# Run server
python manage.py runserver 0.0.0.0:8000
popd >/dev/null
