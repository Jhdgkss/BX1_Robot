#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
SKETCH_PATH="${1:-sketch}"
if [ ! -d "$SKETCH_PATH" ]; then echo "ERROR: sketch folder not found: $SKETCH_PATH" >&2; exit 2; fi
echo "BX1 v10.39 - Compile MCU RouterBridge sketch only"
echo "No upload or flash will be performed by this script."
arduino-cli lib install Arduino_RouterBridge@0.4.3 || true
arduino-cli lib install Arduino_LSM6DSOX@1.1.2 || true
arduino-cli lib install Arduino_HardwareServo@0.0.1 || true
arduino-cli lib install "Adafruit NeoPixel@1.15.5" || true
arduino-cli compile --fqbn arduino:zephyr:unoq "$SKETCH_PATH"
