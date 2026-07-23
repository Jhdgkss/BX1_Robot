#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[BX1] Installing basic Linux packages."
sudo apt update
sudo apt install -y python3 python3-venv python3-pip espeak-ng alsa-utils mpg123 ffmpeg fswebcam v4l-utils

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r python/requirements.txt

chmod +x START_BX1_WEB.sh STOP_BX1_WEB.sh REPAIR_BX1_STARTUP.sh tools/run_robot_body.sh tools/install_bx1_web_service.sh

echo "[BX1] Installing/enabling bx1-web.service for startup."
./tools/install_bx1_web_service.sh

echo "[BX1] Base install complete. Optional voice/camera extras are in python/requirements-optional.txt"
echo "[BX1] For OpenCV/Vosk later: . .venv/bin/activate && pip install -r python/requirements-optional.txt"
echo "[BX1] Web UI: http://BX1.local:8088"
