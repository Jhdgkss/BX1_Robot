#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "[BX1] Repairing BX1 web startup service..."
chmod +x main.py START_BX1_WEB.sh STOP_BX1_WEB.sh tools/run_robot_body.sh tools/install_bx1_web_service.sh
./tools/install_bx1_web_service.sh
