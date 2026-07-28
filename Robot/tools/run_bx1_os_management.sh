#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
CONFIG_PATH="$ROOT_DIR/python/config.json"
PORT="${BX1_WEB_PORT:-8089}"

if [ "$ROOT_DIR" = "/home/arduino/Arduino_Q_Client_V1" ]; then
  echo "[BX1 OS] Refusing to run management from the live installation." >&2
  exit 78
fi
if [ "$PORT" = "8088" ]; then
  echo "[BX1 OS] Refusing reserved existing Robot UI port 8088." >&2
  exit 78
fi
if [ ! -x "$PYTHON_BIN" ] || [ ! -f "$CONFIG_PATH" ]; then
  echo "[BX1 OS] Isolated Python environment or configuration is missing." >&2
  exit 78
fi

export PYTHONPATH="$ROOT_DIR/python"
export BX1_QUALIFICATION_MODE=1
export BX1_OBSERVER_ONLY=1
export BX1_OS_RELEASE_VERSION=0.3.0
export BX1_BODY_CONFIG="$CONFIG_PATH"
export BX1_WEB_HOST="${BX1_WEB_HOST:-0.0.0.0}"
export BX1_WEB_PORT="$PORT"
export BX1_RUNTIME_DIR="${BX1_RUNTIME_DIR:-$ROOT_DIR/runtime}"
export BX1_LOG_DIR="${BX1_LOG_DIR:-$ROOT_DIR/logs}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$ROOT_DIR/cache}"
export TMPDIR="${TMPDIR:-$ROOT_DIR/runtime/tmp}"

mkdir -p "$BX1_RUNTIME_DIR" "$BX1_LOG_DIR" "$XDG_CACHE_HOME" "$TMPDIR"
if [ -n "${BX1_PID_FILE:-}" ]; then
  printf '%s\n' "$$" > "$BX1_PID_FILE"
fi

exec "$PYTHON_BIN" -u -m bx1_management \
  --config "$CONFIG_PATH" \
  --host "$BX1_WEB_HOST" \
  --port "$BX1_WEB_PORT"
