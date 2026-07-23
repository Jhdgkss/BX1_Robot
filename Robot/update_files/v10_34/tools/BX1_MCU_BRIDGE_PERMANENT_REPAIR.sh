#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY="./.venv/bin/python"
RUNTIME_DIR="/home/arduino/ArduinoApps/bx1-mcu-runtime"

if [ ! -x "$PY" ]; then
  echo "[BX1] Missing project Python: $PY"
  exit 1
fi
if ! command -v arduino-app-cli >/dev/null 2>&1; then
  echo "[BX1] ERROR: arduino-app-cli is not installed or not in PATH."
  exit 1
fi

cat <<'EOF'
============================================================
 BX1 MCU Bridge Permanent Repair / Startup Registration v10.33.1
============================================================
This installs the BX1 MCU Runtime as the Arduino App Lab default,
stops the old Color Your LEDs app, compiles/uploads the current BX1
sketch, verifies the Router RPC methods, and restores the body service.
EOF

echo "[BX1] Stopping body client..."
sudo systemctl stop bx1-web.service || true

# Stop any Arduino App that may currently own/overwrite the MCU sketch.
set +e
arduino-app-cli app stop user:color-your-leds-ip-address >/dev/null 2>&1
arduino-app-cli app stop user:bx1-mcu-runtime >/dev/null 2>&1
set -e

mkdir -p "$RUNTIME_DIR/python" "$RUNTIME_DIR/sketch"
cp sketch/sketch.ino "$RUNTIME_DIR/sketch/sketch.ino"
cp sketch/sketch.yaml "$RUNTIME_DIR/sketch/sketch.yaml"
cat > "$RUNTIME_DIR/app.yaml" <<'EOF'
name: BX1 MCU Runtime
description: Persistent BX1 v10.33.1 MCU bridge, mixed head gimbal and addressable LED control
icon: 🤖
ports: []
bricks: []
EOF
cat > "$RUNTIME_DIR/python/main.py" <<'PY'
#!/usr/bin/env python3
import time
print("[BX1 MCU Runtime] Arduino App companion active.", flush=True)
while True:
    time.sleep(60)
PY
chmod +x "$RUNTIME_DIR/python/main.py"

echo "[BX1] Starting BX1 MCU Runtime. This compiles and uploads the sketch..."
arduino-app-cli app start user:bx1-mcu-runtime
arduino-app-cli properties set default user:bx1-mcu-runtime

# Ensure body service starts after the router. This does not replace App Lab;
# it only establishes correct Linux service ordering.
echo "[BX1] Installing service ordering and restricted Doctor recovery permission..."
sudo mkdir -p /etc/systemd/system/bx1-web.service.d
sudo tee /etc/systemd/system/bx1-web.service.d/10-arduino-router.conf >/dev/null <<'EOF'
[Unit]
After=arduino-router.service
Wants=arduino-router.service
EOF
sudo tee /etc/sudoers.d/bx1-hardware-doctor >/dev/null <<'EOF'
arduino ALL=(root) NOPASSWD: /usr/bin/systemctl restart arduino-router, /usr/bin/systemctl restart arduino-router.service
EOF
sudo chmod 0440 /etc/sudoers.d/bx1-hardware-doctor
if command -v visudo >/dev/null 2>&1; then
  sudo visudo -cf /etc/sudoers.d/bx1-hardware-doctor
fi
sudo systemctl daemon-reload

sleep 10
echo "[BX1] Checking persistent Router RPC / MCU bridge..."
set +e
"$PY" tools/check_mcu_router_bridge.py
CHECK_RC=$?
set -e

echo "[BX1] Starting body service..."
sudo systemctl start bx1-web.service
sleep 8
systemctl status bx1-web.service --no-pager -l || true

if [ "$CHECK_RC" -ne 0 ]; then
  cat <<EOF
------------------------------------------------------------
[BX1] MCU bridge check did not pass.
Useful diagnostics:
  arduino-app-cli properties get default
  arduino-app-cli app list
  systemctl status arduino-router --no-pager -l
  journalctl -u arduino-router -n 120 --no-pager -l
  $PY tools/check_mcu_router_bridge.py
------------------------------------------------------------
EOF
  exit "$CHECK_RC"
fi

cat <<'EOF'
------------------------------------------------------------
[BX1] PASS: BX1 MCU Runtime is the persistent default app.
The bridge, mixed head-gimbal RPCs and LED configuration RPCs passed.
------------------------------------------------------------
EOF
