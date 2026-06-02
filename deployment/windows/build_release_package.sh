#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION_VALUE="${1:-$(cat "$ROOT_DIR/VERSION" 2>/dev/null || echo "0.1.0")}"
PACKAGE_NAME="TechTracker-v${VERSION_VALUE}-windows-server"
OUT_DIR="$ROOT_DIR/dist/releases"
STAGING="$OUT_DIR/$PACKAGE_NAME"
ZIP_PATH="$OUT_DIR/$PACKAGE_NAME.zip"

rm -rf "$STAGING" "$ZIP_PATH"
mkdir -p "$STAGING" "$OUT_DIR"

copy_path() {
  local src="$1"
  if [[ -e "$ROOT_DIR/$src" ]]; then
    mkdir -p "$STAGING/$(dirname "$src")"
    cp -a "$ROOT_DIR/$src" "$STAGING/$src"
  fi
}

for item in \
  "agents" \
  "deployment" \
  "inventory_api" \
  "lstm_remote_service" \
  "TechTracker_django" \
  "techtracker_vue" \
  "manage.py" \
  "requirements.txt" \
  "README.txt" \
  "API_SPEC.md" \
  "DB_SCHEMA.md" \
  "VERSION" \
  "LICENSE"; do
  copy_path "$item"
done

find "$STAGING" \
  \( -name ".git" -o -name ".idea" -o -name ".vscode" -o -name "__pycache__" -o -name ".pytest_cache" -o -name ".mypy_cache" \) -prune -exec rm -rf {} + 2>/dev/null || true

find "$STAGING" \
  \( -name "*.pyc" -o -name "*.pyo" -o -name "*.log" -o -name ".DS_Store" -o -name "Thumbs.db" \) -delete

rm -rf \
  "$STAGING/.venv" \
  "$STAGING/env" \
  "$STAGING/venv" \
  "$STAGING/node_modules" \
  "$STAGING/techtracker_vue/node_modules" \
  "$STAGING/techtracker_vue/dist" \
  "$STAGING/logs" \
  "$STAGING/backups" \
  "$STAGING/research"

find "$STAGING" -name ".env.local" -delete
find "$STAGING" -name ".env" -delete

WINSW_VERSION="${WINSW_VERSION:-2.12.0}"
WINSW_LOCAL="$ROOT_DIR/deployment/windows/bin/WinSW-x64.exe"
WINSW_STAGING="$STAGING/deployment/windows/bin/WinSW-x64.exe"
WINSW_URL="https://github.com/winsw/winsw/releases/download/v${WINSW_VERSION}/WinSW-x64.exe"
mkdir -p "$(dirname "$WINSW_STAGING")"
if [[ -f "$WINSW_LOCAL" ]]; then
  cp -a "$WINSW_LOCAL" "$WINSW_STAGING"
else
  echo "Downloading WinSW ${WINSW_VERSION} for offline installer package"
  curl -fL --retry 5 --retry-delay 2 --connect-timeout 30 --max-time 300 -o "$WINSW_STAGING" "$WINSW_URL"
fi
if [[ ! -s "$WINSW_STAGING" ]] || [[ "$(stat -c '%s' "$WINSW_STAGING")" -lt 1048576 ]]; then
  echo "WinSW binary was not bundled correctly: $WINSW_STAGING" >&2
  exit 1
fi

# Windows PowerShell 5.1 is conservative about script encodings. Release
# packages store PowerShell scripts as UTF-8 with BOM and CRLF line endings so
# Russian text and parser-sensitive blocks are read consistently on Windows
# Server.
python3 - "$STAGING" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
for path in root.joinpath("deployment", "windows").rglob("*.ps1"):
    text = path.read_text(encoding="utf-8-sig")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
PY

cat > "$STAGING/INSTALL_WINDOWS_SERVER.txt" <<'TXT'
TechTracker Windows Server package

1. Install prerequisites:
   - Python 3.11/3.12
   - Node.js LTS
   - Git
   - PostgreSQL
   - PowerShell 5+ or PowerShell 7

2. Extract this folder anywhere, for example C:\Temp\TechTracker-vX.Y.Z.

3. Run bootstrap installer. It will ask for DB/admin/server settings and create .env.local automatically.

4. Run PowerShell as Administrator:
   cd C:\Temp\TechTracker-vX.Y.Z
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\windows\bootstrap_techtracker.ps1 -AppRoot C:\TechTracker

5. Open:
   http://SERVER_IP:8080

Details:
   deployment\windows\README.md
TXT

(
  cd "$OUT_DIR"
  7z a -tzip "$ZIP_PATH" "$PACKAGE_NAME" >/dev/null
)

echo "$ZIP_PATH"
