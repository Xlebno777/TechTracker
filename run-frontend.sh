#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONT_DIR="${ROOT_DIR}/techtracker_vue"

if [[ ! -d "${FRONT_DIR}" ]]; then
  echo "Missing ${FRONT_DIR}" >&2
  exit 1
fi

if [[ ! -d "${FRONT_DIR}/node_modules" ]]; then
  echo "node_modules not found, installing..."
  (cd "${FRONT_DIR}" && npm install)
fi

cd "${FRONT_DIR}"
npm run serve
