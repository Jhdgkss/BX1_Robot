#!/usr/bin/env bash
set -e

# Stops the BX1 UNO Q body client web listener on the selected port.
# V8.2: finds listeners using ss, fuser, lsof and common BX1 python command lines.
# Default port is 8088. Override with: BX1_WEB_PORT=8089 ./STOP_BX1_WEB.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${BX1_WEB_PORT:-8088}"

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
    pgrep -f "Arduino_Q_Client_V1.*/python/main.py" 2>/dev/null || true
    pgrep -f "python3 .*main.py --standalone" 2>/dev/null || true
    pgrep -f "python .*main.py --standalone" 2>/dev/null || true
  } | tr ' ' '\n' | awk 'NF && !seen[$1]++ {print}'
}

echo "============================================================"
echo " BX1 UNO Q Body Client - Stop Web Control v10.10"
echo "============================================================"
echo "Project : $ROOT_DIR"
echo "Port    : $PORT"
echo "------------------------------------------------------------"

if command -v ss >/dev/null 2>&1; then
  echo "Current listener check:"
  ss -ltnp 2>/dev/null | awk -v p=":${PORT}" '$4 ~ p {print}' || true
  echo "------------------------------------------------------------"
fi

PIDS="$(pids_on_port | tr '\n' ' ')"
if [ -z "${PIDS// }" ]; then
  echo "No BX1 listener found on port ${PORT}."
  exit 0
fi

echo "Stopping process id(s): $PIDS"
kill $PIDS 2>/dev/null || true
sleep 1

STILL_RUNNING=""
for pid in $PIDS; do
  if kill -0 "$pid" 2>/dev/null; then
    STILL_RUNNING="$STILL_RUNNING $pid"
  fi
done

if [ -n "${STILL_RUNNING// }" ]; then
  echo "Some processes did not stop cleanly; forcing:$STILL_RUNNING"
  kill -9 $STILL_RUNNING 2>/dev/null || true
  sleep 1
fi

if command -v ss >/dev/null 2>&1 && ss -ltnp 2>/dev/null | awk -v p=":${PORT}" '$4 ~ p {found=1} END {exit !found}'; then
  echo "Port ${PORT} is still in use. Try:"
  echo "  sudo fuser -k ${PORT}/tcp"
  exit 1
fi

echo "Stopped. Port ${PORT} is clear."
