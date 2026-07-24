#!/usr/bin/env bash
set -Eeuo pipefail

NEW_ROOT="/home/arduino/BX1_Robot_GitHub/Robot"
OLD_ROOT="/home/arduino/Arduino_Q_Client_V1"
SERVICE_NAME="bx1-github.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
LOG="/home/arduino/BX1_GITHUB_INSTALL_$(date +%Y%m%d_%H%M%S).log"

exec > >(tee -a "$LOG") 2>&1

echo "============================================================"
echo " BX1 GitHub clean installation"
echo " New application: $NEW_ROOT"
echo " Existing application remains at: $OLD_ROOT"
echo " Log: $LOG"
echo "============================================================"

if [[ "$(id -un)" != "arduino" ]]; then
  echo "ERROR: Run this installer as user 'arduino', not with sudo."
  exit 1
fi

if [[ ! -f "$NEW_ROOT/main.py" ]]; then
  echo "ERROR: $NEW_ROOT/main.py was not found."
  echo "Confirm the GitHub repository is cloned to /home/arduino/BX1_Robot_GitHub."
  exit 1
fi

echo "[1/9] Installing base Linux packages..."
sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-pip python3-dev \
  build-essential git curl rsync \
  portaudio19-dev libasound2-dev ffmpeg

echo "[2/9] Creating a fresh Python virtual environment..."
rm -rf "$NEW_ROOT/.venv"
python3 -m venv "$NEW_ROOT/.venv"
"$NEW_ROOT/.venv/bin/python" -m pip install --upgrade pip setuptools wheel

echo "[3/9] Installing Python dependencies..."
REQ_FILE=""
for candidate in \
  "$NEW_ROOT/requirements.txt" \
  "$NEW_ROOT/python/requirements.txt" \
  "$NEW_ROOT/requirements-linux.txt" \
  "$NEW_ROOT/requirements_robot.txt"
do
  if [[ -f "$candidate" ]]; then
    REQ_FILE="$candidate"
    break
  fi
done

if [[ -n "$REQ_FILE" ]]; then
  echo "Using dependency file: $REQ_FILE"
  "$NEW_ROOT/.venv/bin/pip" install -r "$REQ_FILE"
elif [[ -x "$OLD_ROOT/.venv/bin/pip" ]]; then
  echo "No requirements file found. Rebuilding from the working installation's package list."
  FREEZE="/tmp/bx1_old_environment_requirements.txt"
  "$OLD_ROOT/.venv/bin/pip" freeze \
    | grep -vE '(^-e | @ file:|pkg-resources==)' \
    > "$FREEZE"
  "$NEW_ROOT/.venv/bin/pip" install -r "$FREEZE"
  cp "$FREEZE" "$NEW_ROOT/requirements-migrated.txt"
else
  echo "ERROR: No requirements file and no usable old virtual environment were found."
  exit 1
fi

echo "[4/9] Migrating robot-specific configuration and persistent assets..."
mkdir -p "$NEW_ROOT/python" "$NEW_ROOT/runtime"

copy_file_if_present() {
  local source="$1"
  local destination="$2"
  if [[ -f "$source" ]]; then
    mkdir -p "$(dirname "$destination")"
    cp -a "$source" "$destination"
    echo "Copied: $source"
  fi
}

copy_dir_if_present() {
  local source="$1"
  local destination="$2"
  if [[ -d "$source" ]]; then
    mkdir -p "$(dirname "$destination")"
    rsync -a "$source/" "$destination/"
    echo "Copied directory: $source"
  fi
}

copy_file_if_present "$OLD_ROOT/python/config.json" "$NEW_ROOT/python/config.json"
copy_file_if_present "$OLD_ROOT/python/robot_profile.json" "$NEW_ROOT/python/robot_profile.json"
copy_file_if_present "$OLD_ROOT/config.json" "$NEW_ROOT/config.json"

copy_dir_if_present "$OLD_ROOT/models" "$NEW_ROOT/models"
copy_dir_if_present "$OLD_ROOT/runtime/audio" "$NEW_ROOT/runtime/audio"
copy_dir_if_present "$OLD_ROOT/runtime/voices" "$NEW_ROOT/runtime/voices"
copy_dir_if_present "$OLD_ROOT/files" "$NEW_ROOT/files"

echo "[5/9] Fixing ownership and executable permissions..."
sudo chown -R arduino:arduino /home/arduino/BX1_Robot_GitHub
find "$NEW_ROOT" -type f -name "*.sh" -exec chmod +x {} \;
chmod +x "$NEW_ROOT/main.py" 2>/dev/null || true

echo "[6/9] Checking Python syntax..."
cd "$NEW_ROOT"
"$NEW_ROOT/.venv/bin/python" -m compileall -q main.py python tools

echo "[7/9] Creating the separate startup service..."
sudo tee "$SERVICE_PATH" >/dev/null <<EOF
[Unit]
Description=BX1 Robot GitHub Application
After=network-online.target sound.target
Wants=network-online.target
Conflicts=bx1-web.service bx1-robot-body.service

[Service]
Type=simple
User=arduino
Group=arduino
WorkingDirectory=$NEW_ROOT
Environment=PYTHONUNBUFFERED=1
Environment=PATH=$NEW_ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$NEW_ROOT/.venv/bin/python $NEW_ROOT/main.py --standalone
Restart=on-failure
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

echo "[8/9] Switching startup to the new GitHub installation..."
sudo systemctl stop bx1-web.service 2>/dev/null || true
sudo systemctl stop bx1-robot-body.service 2>/dev/null || true
sudo systemctl disable bx1-web.service 2>/dev/null || true
sudo systemctl disable bx1-robot-body.service 2>/dev/null || true

sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

sleep 8

echo "[9/9] Verifying startup..."
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
  echo
  echo "============================================================"
  echo " SUCCESS: BX1 is running from:"
  echo " $NEW_ROOT"
  echo
  echo " The previous project remains untouched at:"
  echo " $OLD_ROOT"
  echo "============================================================"
  sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
else
  echo
  echo "ERROR: The new service did not remain active."
  sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
  echo
  echo "Recent log:"
  sudo journalctl -u "$SERVICE_NAME" -n 120 --no-pager || true
  echo
  echo "Run ./ROLLBACK_TO_OLD_BX1.sh to restore the previous startup service."
  exit 1
fi
