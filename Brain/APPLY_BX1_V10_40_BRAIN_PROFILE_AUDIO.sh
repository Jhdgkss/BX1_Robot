#!/usr/bin/env bash
set -Eeuo pipefail

PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD="$PATCH_DIR/payload"
TARGET="${1:-/home/arduino/Arduino_Q_Client_V1}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$TARGET/backups/v10_40_$STAMP"
SERVICE_WAS_ACTIVE=0
APPLIED=0

restore_previous() {
    local status=$?
    if [[ $status -eq 0 ]]; then
        return
    fi
    echo
    echo "[BX1] Installation failed. Restoring v10.40 backup..."
    if [[ -d "$BACKUP" ]]; then
        cp -a "$BACKUP/." "$TARGET/" || true
    fi
    if [[ $SERVICE_WAS_ACTIVE -eq 1 ]]; then
        sudo systemctl restart bx1-web.service || true
    fi
    echo "[BX1] Previous files restored from: $BACKUP"
    exit "$status"
}
trap restore_previous ERR

if [[ ! -f "$TARGET/python/main.py" ]]; then
    echo "ERROR: BX1 Body project not found at: $TARGET"
    echo "Usage: $0 [/home/arduino/Arduino_Q_Client_V1]"
    exit 2
fi
if [[ ! -f "$PAYLOAD/python/main.py" ]]; then
    echo "ERROR: v10.40 patch payload is incomplete."
    exit 3
fi

mkdir -p "$BACKUP/python"
for file in \
    python/main.py python/audio_io.py python/bx1_robot_client.py python/web_control.py \
    python/config.example.json python/config.fresh.json \
    app.yaml CHANGELOG.md README.md VERSION.txt; do
    if [[ -f "$TARGET/$file" ]]; then
        mkdir -p "$BACKUP/$(dirname "$file")"
        cp -a "$TARGET/$file" "$BACKUP/$file"
    fi
done

if systemctl is-active --quiet bx1-web.service; then
    SERVICE_WAS_ACTIVE=1
    sudo systemctl stop bx1-web.service
fi

cp -a "$PAYLOAD/." "$TARGET/"
APPLIED=1

PYTHON="$TARGET/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(command -v python3)"
fi

"$PYTHON" -m compileall -q "$TARGET/python"

# Validate the embedded browser JavaScript when Node is available.
if command -v node >/dev/null 2>&1; then
    TMP_JS="$(mktemp /tmp/bx1_v1040_web_XXXXXX.js)"
    "$PYTHON" - "$TARGET/python/web_control.py" "$TMP_JS" <<'PY'
from pathlib import Path
import re, sys
source = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"<script>(.*?)</script>", source, re.S)
if not match:
    raise SystemExit("embedded web script not found")
Path(sys.argv[2]).write_text(match.group(1), encoding="utf-8")
PY
    node --check "$TMP_JS"
    rm -f "$TMP_JS"
fi

# This release is Linux/Python only. Do not invoke App Lab or flash the MCU.
sudo systemctl restart bx1-web.service
sleep 4
sudo systemctl --no-pager --full status bx1-web.service | sed -n '1,24p'

if command -v curl >/dev/null 2>&1; then
    curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8088/ >/dev/null
fi

trap - ERR

echo
echo "============================================================"
echo " BX1 Robot Body v10.40 installed successfully"
echo "============================================================"
echo "Backup : $BACKUP"
echo "Target : $TARGET"
echo
echo "No MCU compile or firmware upload was performed."
echo "Open Speech Input and press 'Sync Brain profile now' after"
echo "Robot Brain V2.10.0 is running and its phrases are generated."
