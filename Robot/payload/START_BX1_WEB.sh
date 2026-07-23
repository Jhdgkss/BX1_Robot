#!/usr/bin/env bash
set -u
set -o pipefail

# Single-click / SSH starter for the BX1 UNO Q body client.
# v10.41: capture-ID diagnostics, transient-safe endpointing and faster primary STT.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_DIR="$ROOT_DIR/python"
APP_ENTRY="$ROOT_DIR/main.py"
PORT="${BX1_WEB_PORT:-8088}"
URL="http://127.0.0.1:${PORT}"
NETWORK_URL="http://BX1.local:${PORT}"
FORCE_RESTART="false"
NO_BROWSER="false"
LOG_DIR="$ROOT_DIR/runtime/logs"
LOG_FILE="$LOG_DIR/web_startup.log"
mkdir -p "$LOG_DIR"

if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
fi

for arg in "$@"; do
  case "$arg" in
    --force|--force-restart) FORCE_RESTART="true" ;;
    --no-browser|--headless) NO_BROWSER="true" ;;
  esac
done

open_browser() {
  [ "$NO_BROWSER" = "true" ] && return 0
  (
    sleep 1
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$URL" >/dev/null 2>&1 || true
    elif command -v sensible-browser >/dev/null 2>&1; then
      sensible-browser "$URL" >/dev/null 2>&1 || true
    fi
  ) &
}

listener_lines() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | awk -v p=":${PORT}" '$4 ~ p {print}' || true
  fi
}

pids_on_port() {
  {
    if command -v ss >/dev/null 2>&1; then
      ss -ltnp 2>/dev/null | awk -v p=":${PORT}" '$4 ~ p {print}' | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p'
    fi
    if command -v fuser >/dev/null 2>&1; then
      fuser -n tcp "$PORT" 2>/dev/null || true
    fi
    if command -v lsof >/dev/null 2>&1; then
      lsof -ti tcp:"$PORT" 2>/dev/null || true
    fi
    pgrep -f "Arduino_Q_Client_V1.*/main.py --standalone" 2>/dev/null || true
    pgrep -f "Arduino_Q_Client_V1.*/python/main.py" 2>/dev/null || true
  } | tr ' ' '\n' | awk 'NF && !seen[$1]++ {print}'
}

bx1_web_responding() {
  "$PYTHON_BIN" - <<PY_INNER >/dev/null 2>&1
import json
import urllib.request
try:
    with urllib.request.urlopen("$URL/api/status", timeout=1.5) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    raise SystemExit(0 if isinstance(data, dict) else 1)
except Exception:
    raise SystemExit(1)
PY_INNER
}

kill_port_pids() {
  PIDS="$(pids_on_port | tr '\n' ' ')"
  if [ -z "${PIDS// }" ]; then
    return 0
  fi
  echo "Stopping process id(s): $PIDS"
  kill $PIDS 2>/dev/null || true
  sleep 1
  STILL=""
  for pid in $PIDS; do
    if kill -0 "$pid" 2>/dev/null; then
      STILL="$STILL $pid"
    fi
  done
  if [ -n "${STILL// }" ]; then
    echo "Forcing process id(s):$STILL"
    kill -9 $STILL 2>/dev/null || true
    sleep 1
  fi
}

print_header() {
  echo "============================================================"
  echo " BX1 UNO Q Body Client - Web Control Starter v10.41"
  echo "============================================================"
  echo "Project : $ROOT_DIR"
  echo "Web UI  : $URL"
  echo "Network : try $NETWORK_URL from another device"
  echo "Stop    : close this window or press Ctrl+C"
  echo "Force   : ./START_BX1_WEB.sh --force"
  echo "Service : ./REPAIR_BX1_STARTUP.sh"
  echo "Python  : ${PYTHON_BIN:-missing}"
  echo "App     : $APP_ENTRY"
  echo "Log     : $LOG_FILE"
  echo "------------------------------------------------------------"
}

print_header | tee -a "$LOG_FILE"

if [ ! -f "$APP_ENTRY" ]; then
  echo "ERROR: Cannot find $APP_ENTRY" | tee -a "$LOG_FILE"
  echo "The startup fix should have created this compatibility launcher." | tee -a "$LOG_FILE"
  exit 2
fi
if [ ! -d "$PY_DIR" ] || [ ! -f "$PY_DIR/main.py" ]; then
  echo "ERROR: Cannot find $PY_DIR/main.py" | tee -a "$LOG_FILE"
  exit 2
fi
if [ -z "${PYTHON_BIN:-}" ] || [ ! -x "$PYTHON_BIN" ]; then
  echo "ERROR: Python executable not found. Try: sudo apt install -y python3 python3-venv" | tee -a "$LOG_FILE"
  exit 127
fi

LISTENER="$(listener_lines)"
if [ -n "$LISTENER" ]; then
  echo "Port ${PORT} is already in use." | tee -a "$LOG_FILE"
  echo "$LISTENER" | tee -a "$LOG_FILE"
  echo "------------------------------------------------------------" | tee -a "$LOG_FILE"
  if bx1_web_responding; then
    echo "BX1 Web Control already appears to be running." | tee -a "$LOG_FILE"
    echo "Web UI  : $URL" | tee -a "$LOG_FILE"
    echo "Network : $NETWORK_URL" | tee -a "$LOG_FILE"
    open_browser
    exit 0
  fi
  if [ "$FORCE_RESTART" = "true" ]; then
    echo "Force restart requested. Stopping old listener on port ${PORT}..." | tee -a "$LOG_FILE"
    kill_port_pids
  else
    echo "Something is using port ${PORT}, but it does not answer like BX1 Web Control." | tee -a "$LOG_FILE"
    echo "Run: cd $ROOT_DIR && ./START_BX1_WEB.sh --force" | tee -a "$LOG_FILE"
    exit 1
  fi
fi

if [ -n "$(listener_lines)" ]; then
  echo "Port ${PORT} is still busy after stop attempt." | tee -a "$LOG_FILE"
  echo "Run: ss -ltnp | grep ':${PORT}'" | tee -a "$LOG_FILE"
  exit 1
fi

open_browser
cd "$ROOT_DIR"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Python web service..." | tee -a "$LOG_FILE"
PYTHONUNBUFFERED=1 "$PYTHON_BIN" -u "$APP_ENTRY" --standalone 2>&1 | tee -a "$LOG_FILE"
CODE=${PIPESTATUS[0]}

echo "------------------------------------------------------------" | tee -a "$LOG_FILE"
echo "BX1 web service exited with code: $CODE" | tee -a "$LOG_FILE"
if [ "$CODE" -ne 0 ]; then
  echo "It crashed or failed to start. Last 80 log lines:" | tee -a "$LOG_FILE"
  tail -80 "$LOG_FILE"
  echo "Useful service log command:" | tee -a "$LOG_FILE"
  echo "  sudo journalctl -u bx1-web.service -n 120 --no-pager" | tee -a "$LOG_FILE"
fi
exit "$CODE"
