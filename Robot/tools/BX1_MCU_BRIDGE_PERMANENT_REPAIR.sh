#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PY="./.venv/bin/python"
APP_USER="${BX1_APP_USER:-${SUDO_USER:-arduino}}"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6 || true)"
[ -n "$APP_HOME" ] || APP_HOME="/home/$APP_USER"
APP_GROUP="$(id -gn "$APP_USER" 2>/dev/null || printf '%s' "$APP_USER")"
RUNTIME_DIR="$APP_HOME/ArduinoApps/bx1-mcu-runtime"
BACKUP_DIR="$APP_HOME/ArduinoApps/backups"
STAMP="$(date +%Y%m%d_%H%M%S)"
DIAG_DIR="$(pwd)/diagnostic_traces"
DIAG_LOG="$DIAG_DIR/BX1_MCU_INSTALL_V10_38_${STAMP}.log"

mkdir -p "$DIAG_DIR"

if [ ! -x "$PY" ]; then
  echo "[BX1] Missing project Python: $PY"
  exit 1
fi

find_app_cli() {
  local cli=""
  cli="$(command -v arduino-app-cli 2>/dev/null || true)"
  if [ -z "$cli" ] && command -v sudo >/dev/null 2>&1; then
    cli="$(sudo -u "$APP_USER" -H bash -lc 'command -v arduino-app-cli' 2>/dev/null || true)"
  fi
  printf '%s' "$cli"
}

APP_CLI="$(find_app_cli)"
if [ -z "$APP_CLI" ]; then
  echo "[BX1] ERROR: arduino-app-cli is not installed or not available for user $APP_USER."
  exit 1
fi

app_cli() {
  if [ "$(id -un)" = "$APP_USER" ]; then
    "$APP_CLI" "$@"
  else
    sudo -u "$APP_USER" -H "$APP_CLI" "$@"
  fi
}

collect_diagnostics() {
  {
    echo
    echo "============================================================"
    echo " BX1 MCU INSTALL DIAGNOSTICS"
    echo "============================================================"
    date -Is
    echo
    echo "--- App list ---"
    app_cli app list 2>&1 || true
    echo
    echo "--- BX1 MCU Runtime logs (15 second snapshot) ---"
    timeout 15s bash -c '"$0" app logs user:bx1-mcu-runtime' "$APP_CLI" 2>&1 || true
    echo
    echo "--- arduino-router status ---"
    systemctl status arduino-router --no-pager -l 2>&1 || true
    echo
    echo "--- arduino-router journal ---"
    journalctl -u arduino-router -n 120 --no-pager 2>&1 || true
    echo
    echo "--- Runtime files ---"
    find "$RUNTIME_DIR" -maxdepth 4 -type f -printf '%p %s bytes\n' 2>&1 | sort || true
    echo
    echo "--- Cache/build log candidates ---"
    find "$RUNTIME_DIR/.cache" -type f \( -iname '*.log' -o -iname '*stderr*' -o -iname '*stdout*' -o -iname '*.txt' \) -print 2>/dev/null | sort || true
    while IFS= read -r file; do
      echo
      echo "### $file"
      tail -n 160 "$file" 2>/dev/null || true
    done < <(find "$RUNTIME_DIR/.cache" -type f \( -iname '*.log' -o -iname '*stderr*' -o -iname '*stdout*' -o -iname '*.txt' \) -print 2>/dev/null | sort)
  } | tee "$DIAG_LOG"
}

cat <<EOF2
============================================================
 BX1 MCU Runtime Update v10.39
============================================================
App Lab user : $APP_USER
Runtime dir  : $RUNTIME_DIR

Applies the v10.39 runtime update:
  - RouterBridge library updated to 0.4.3 for current UNO Q Zephyr core.
  - stale App Lab build cache is removed.
  - Bridge RPC is registered before IMU/servo/LED initialisation.
  - absent Movement hardware cannot keep the MCU bridge offline.
  - Movement probes both 0x6A and 0x6B on Wire1/Qwiic.
  - installation and compile diagnostics are captured automatically.
  - live microphone capture can yield immediately to manual STT diagnostics.
  - quiet-servo mode releases PWM after movement to reduce buzzing.

Wheel outputs remain disabled and unarmed.
EOF2

SERVICE_STOPPED=0
cleanup() {
  if [ "$SERVICE_STOPPED" -eq 1 ]; then
    sudo systemctl start bx1-web.service >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

sudo systemctl stop bx1-web.service || true
SERVICE_STOPPED=1

set +e
app_cli app stop user:color-your-leds-ip-address >/dev/null 2>&1
app_cli app stop user:bx1-mcu-runtime >/dev/null 2>&1
set -e

sudo mkdir -p "$BACKUP_DIR"
if [ -d "$RUNTIME_DIR" ]; then
  sudo cp -a "$RUNTIME_DIR" "$BACKUP_DIR/bx1-mcu-runtime.before_v10_39_${STAMP}"
fi

sudo mkdir -p "$RUNTIME_DIR/python" "$RUNTIME_DIR/sketch"

# App Lab may reuse a previously compiled sketch even after source files have
# changed. Clearing only this app's cache forces a genuine v10.39 build.
sudo rm -rf "$RUNTIME_DIR/.cache"

sudo cp sketch/sketch.ino "$RUNTIME_DIR/sketch/sketch.ino"
sudo cp sketch/sketch.yaml "$RUNTIME_DIR/sketch/sketch.yaml"

sudo tee "$RUNTIME_DIR/app.yaml" >/dev/null <<'APP_EOF'
name: BX1 MCU Runtime
description: Persistent BX1 v10.39 RouterBridge-first hardware runtime with Modulino Movement, head gimbal and addressable LED control
icon: 🤖
ports: []
bricks: []
APP_EOF

sudo tee "$RUNTIME_DIR/python/main.py" >/dev/null <<'PY_EOF'
#!/usr/bin/env python3
import time

print("[BX1 MCU Runtime v10.39] Linux companion active.", flush=True)
while True:
    time.sleep(60)
PY_EOF

sudo chmod +x "$RUNTIME_DIR/python/main.py"
sudo chown -R "$APP_USER:$APP_GROUP" "$RUNTIME_DIR" "$BACKUP_DIR"

echo "[BX1] Starting MCU runtime and forcing a clean compile/upload..."
set +e
START_OUTPUT="$(app_cli app start user:bx1-mcu-runtime 2>&1)"
START_RC=$?
set -e
printf '%s\n' "$START_OUTPUT"

if [ "$START_RC" -ne 0 ]; then
  echo "[BX1] ERROR: Arduino App CLI rejected the app start."
  collect_diagnostics
  exit "$START_RC"
fi

app_cli properties set default user:bx1-mcu-runtime || true

sudo mkdir -p /etc/systemd/system/bx1-web.service.d
sudo tee /etc/systemd/system/bx1-web.service.d/10-arduino-router.conf >/dev/null <<'UNIT_EOF'
[Unit]
After=arduino-router.service
Wants=arduino-router.service
UNIT_EOF

sudo tee /etc/sudoers.d/bx1-hardware-doctor >/dev/null <<'SUDO_EOF'
arduino ALL=(root) NOPASSWD: /usr/bin/systemctl restart arduino-router, /usr/bin/systemctl restart arduino-router.service
SUDO_EOF
sudo chmod 0440 /etc/sudoers.d/bx1-hardware-doctor
if command -v visudo >/dev/null 2>&1; then
  sudo visudo -cf /etc/sudoers.d/bx1-hardware-doctor
fi
sudo systemctl daemon-reload

echo "[BX1] Waiting for the minimal bx1_ping RPC..."
PING_RC=1
for attempt in $(seq 1 30); do
  sleep 3
  set +e
  "$PY" tools/check_mcu_router_ping.py
  PING_RC=$?
  set -e
  if [ "$PING_RC" -eq 0 ]; then
    echo "[BX1] RouterBridge bootstrap online."
    break
  fi
  echo "[BX1] Bootstrap not ready yet (attempt $attempt/30)."
done

if [ "$PING_RC" -ne 0 ]; then
  echo "[BX1] ERROR: MCU never registered bx1_ping."
  collect_diagnostics
  exit "$PING_RC"
fi

echo "[BX1] Running complete BX1 hardware RPC verification..."
set +e
"$PY" tools/check_mcu_router_bridge.py
CHECK_RC=$?
set -e

sudo systemctl start bx1-web.service
SERVICE_STOPPED=0
sleep 5
systemctl status bx1-web.service --no-pager -l || true

if [ "$CHECK_RC" -ne 0 ]; then
  echo "[BX1] Bridge bootstrap is online, but one or more hardware RPC tests failed."
  collect_diagnostics
  exit "$CHECK_RC"
fi

echo
echo "[BX1] PASS: MCU bridge online."
echo "[BX1] Refresh Hardware. The IMU may show ONLINE or a specific 0x6A/0x6B wiring diagnostic."
echo "[BX1] Diagnostic log location: $DIAG_LOG"
