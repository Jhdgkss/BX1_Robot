#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "BX1 v10.3 - Force restart web service"
echo "====================================="
./STOP_BX1_WEB.sh 2>/dev/null || true
pkill -f "python.*main.py" 2>/dev/null || true
pkill -f "Arduino_Q_Client_V1" 2>/dev/null || true
sleep 1
./START_BX1_WEB.sh --force
