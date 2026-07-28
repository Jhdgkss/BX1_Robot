#!/usr/bin/env bash
set -euo pipefail
HOST="${BX1_HEALTH_HOST:-127.0.0.1}"
PORT="${BX1_WEB_PORT:-8088}"
URL="http://${HOST}:${PORT}/"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

for _ in $(seq 1 20); do
  if "$PYTHON_BIN" - "$URL" >/dev/null 2>&1 <<'PY'
import sys, urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=1.5) as response:
    if response.status >= 400:
        raise SystemExit(1)
    response.read(64)
PY
  then
    echo "[BX1] Web health check passed: $URL"
    exit 0
  fi
  sleep 1
 done

echo "[BX1] ERROR: service process started but web console did not answer at $URL" >&2
ss -ltnp 2>/dev/null | grep ":${PORT} " >&2 || true
exit 1
