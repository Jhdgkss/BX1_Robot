#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_USER="${SUDO_USER:-${USER:-arduino}}"
ROTATION="keep"
OUTPUT="auto"
ENABLE_AUTOLOGIN=1
FORCE_XORG=0
NONINTERACTIVE=0

usage() {
    cat <<'USAGE'
Usage: ./INSTALL_BX1_TOUCHSCREEN.sh [options]

Options:
  --user USER             Desktop user to log in automatically (default: current user)
  --rotation MODE         keep, right, left, normal or inverted
  --output NAME           xrandr output name, or auto
  --no-autologin          Install kiosk launch only; do not alter the login manager
  --force-xorg            Disable GDM Wayland so xrandr/touch rotation can work
  --non-interactive       Do not prompt; use supplied/default values
  -h, --help              Show this help

Examples:
  ./INSTALL_BX1_TOUCHSCREEN.sh
  ./INSTALL_BX1_TOUCHSCREEN.sh --rotation right --force-xorg
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user) TARGET_USER="${2:-}"; shift 2 ;;
        --rotation) ROTATION="${2:-}"; shift 2 ;;
        --output) OUTPUT="${2:-}"; shift 2 ;;
        --no-autologin) ENABLE_AUTOLOGIN=0; shift ;;
        --force-xorg) FORCE_XORG=1; shift ;;
        --non-interactive) NONINTERACTIVE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 2 ;;
    esac
done

case "$ROTATION" in keep|right|left|normal|inverted) ;; *) echo "Invalid rotation: $ROTATION"; exit 2 ;; esac
if ! id "$TARGET_USER" >/dev/null 2>&1; then
    echo "ERROR: Linux user '$TARGET_USER' does not exist."
    exit 3
fi
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
if [[ -z "$TARGET_HOME" || ! -d "$TARGET_HOME" ]]; then
    echo "ERROR: Home folder for '$TARGET_USER' was not found."
    exit 3
fi

cat <<EOF2
============================================================
 BX1 Onboard Touchscreen Setup
============================================================
Project       : $ROOT_DIR
Desktop user  : $TARGET_USER
Autologin     : $([[ $ENABLE_AUTOLOGIN -eq 1 ]] && echo enabled || echo unchanged)
Rotation      : $ROTATION
Display output: $OUTPUT
Screen URL    : http://127.0.0.1:8088/display
============================================================
EOF2

if [[ $NONINTERACTIVE -eq 0 && -t 0 ]]; then
    echo
    echo "The screen is physically mounted in portrait orientation."
    echo "Choose software rotation:"
    echo "  1) Keep the current desktop orientation"
    echo "  2) Right / clockwise"
    echo "  3) Left / anticlockwise"
    echo "  4) Normal landscape"
    read -r -p "Selection [1]: " choice
    case "${choice:-1}" in
        1) ROTATION="keep" ;;
        2) ROTATION="right" ;;
        3) ROTATION="left" ;;
        4) ROTATION="normal" ;;
        *) echo "Invalid selection."; exit 2 ;;
    esac
    if [[ "$ROTATION" != "keep" ]]; then
        read -r -p "Force an Xorg desktop for reliable screen/touch rotation? [Y/n]: " answer
        case "${answer:-Y}" in n|N|no|NO) FORCE_XORG=0 ;; *) FORCE_XORG=1 ;; esac
    fi
    echo
    echo "WARNING: Automatic login allows anyone with physical access to reach"
    echo "the robot desktop. It does not remove the sudo password."
    read -r -p "Continue with this configuration? [Y/n]: " answer
    case "${answer:-Y}" in n|N|no|NO) echo "Cancelled."; exit 0 ;; esac
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$ROOT_DIR/backups/touchscreen_$STAMP"
mkdir -p "$BACKUP_DIR"

RUNTIME_DIR="$ROOT_DIR/runtime"
ENV_FILE="$RUNTIME_DIR/touchscreen.env"
AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/bx1-touchscreen.desktop"
mkdir -p "$RUNTIME_DIR"
cat > "$ENV_FILE" <<EOF2
BX1_TOUCH_URL=http://127.0.0.1:8088/display
BX1_TOUCH_ROTATION=$ROTATION
BX1_TOUCH_OUTPUT=$OUTPUT
EOF2

sudo install -d -o "$TARGET_USER" -g "$TARGET_USER" "$AUTOSTART_DIR"
if [[ -f "$AUTOSTART_FILE" ]]; then
    cp -a "$AUTOSTART_FILE" "$BACKUP_DIR/" || true
fi
sudo tee "$AUTOSTART_FILE" >/dev/null <<EOF2
[Desktop Entry]
Type=Application
Version=1.0
Name=BX1 Onboard Display
Comment=Launch the portrait robot state display after desktop login
Exec=$ROOT_DIR/tools/bx1_touchscreen_kiosk.sh
Terminal=false
X-GNOME-Autostart-enabled=true
StartupNotify=false
EOF2
sudo chown "$TARGET_USER:$TARGET_USER" "$AUTOSTART_FILE"
sudo chmod 0644 "$AUTOSTART_FILE"
sudo chown -R "$TARGET_USER:$TARGET_USER" "$RUNTIME_DIR"
chmod +x "$ROOT_DIR/tools/bx1_touchscreen_kiosk.sh" "$ROOT_DIR/tools/bx1_configure_autologin.py"

# Avoid first-login and screen-lock interruptions on an embedded robot display.
sudo -u "$TARGET_USER" mkdir -p "$TARGET_HOME/.config"
sudo -u "$TARGET_USER" touch "$TARGET_HOME/.config/gnome-initial-setup-done"

for group in audio video input render; do
    if getent group "$group" >/dev/null 2>&1; then
        sudo usermod -aG "$group" "$TARGET_USER" || true
    fi
done

if [[ $ENABLE_AUTOLOGIN -eq 1 ]]; then
    args=(--user "$TARGET_USER" --backup-dir "$BACKUP_DIR")
    if [[ $FORCE_XORG -eq 1 ]]; then args+=(--force-xorg); fi
    set +e
    output_text="$(sudo python3 "$ROOT_DIR/tools/bx1_configure_autologin.py" "${args[@]}" 2>&1)"
    status=$?
    set -e
    echo "$output_text"
    if [[ $status -ne 0 ]]; then
        echo
        echo "WARNING: The display manager was not recognised, so automatic login"
        echo "was not configured. The kiosk autostart files were still installed."
        echo "Send the output of: systemctl status display-manager --no-pager"
    fi
fi

sudo systemctl enable bx1-web.service >/dev/null 2>&1 || true
sudo systemctl restart bx1-web.service
sleep 3

BROWSER=""
for candidate in chromium chromium-browser google-chrome-stable google-chrome firefox-esr firefox; do
    if command -v "$candidate" >/dev/null 2>&1; then BROWSER="$candidate"; break; fi
done

if command -v curl >/dev/null 2>&1; then
    curl --fail --silent --show-error --max-time 8 http://127.0.0.1:8088/display >/dev/null
    curl --fail --silent --show-error --max-time 8 http://127.0.0.1:8088/api/touchscreen >/dev/null
fi

echo
echo "============================================================"
echo " BX1 touchscreen setup completed"
echo "============================================================"
echo "Backup     : $BACKUP_DIR"
echo "Display URL: http://127.0.0.1:8088/display"
echo "Autostart  : $AUTOSTART_FILE"
echo "Browser    : ${BROWSER:-NOT FOUND}"
echo
if [[ -z "$BROWSER" ]]; then
    echo "Install a browser before rebooting, for example:"
    echo "  sudo apt update && sudo apt install -y chromium"
    echo
fi
echo "Reboot to test the complete unattended startup:"
echo "  sudo reboot"
echo
