#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${1:-}"
if [ -z "$PORT" ]; then
  PORT="$(hostname -I | awk '{print $1}')"
fi

echo "BX1 v10.39 - Upload MCU sketch"
echo "============================="
echo "Target network port: $PORT"
echo
echo "This requires a successful compile first:"
echo "  bash tools/compile_mcu_sketch.sh"
echo

arduino-cli upload -p "$PORT" --fqbn arduino:zephyr:unoq sketch
