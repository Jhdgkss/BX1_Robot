#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# bx1-web.service exists specifically to provide the web console.  Force the
# listener on at service startup so a stale/configured false value cannot leave
# systemd active with nothing listening on port 8088.
export BX1_WEB_ENABLED="${BX1_WEB_ENABLED:-1}"
export BX1_WEB_HOST="${BX1_WEB_HOST:-0.0.0.0}"
export BX1_WEB_PORT="${BX1_WEB_PORT:-8088}"

PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [ -z "${PYTHON_BIN:-}" ]; then
  echo "[BX1] ERROR: python3 not found." >&2
  exit 127
fi
if [ ! -f "$ROOT_DIR/main.py" ]; then
  echo "[BX1] ERROR: Missing $ROOT_DIR/main.py compatibility launcher." >&2
  echo "[BX1] Expected application at $ROOT_DIR/python/main.py" >&2
  exit 2
fi
if [ ! -f "$ROOT_DIR/python/main.py" ]; then
  echo "[BX1] ERROR: Missing $ROOT_DIR/python/main.py" >&2
  exit 2
fi
exec "$PYTHON_BIN" -u "$ROOT_DIR/main.py" --standalone --web-enabled
