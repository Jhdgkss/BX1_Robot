#!/usr/bin/env bash
set -u
set -o pipefail

ROOT_DIR="/home/arduino/BX1_OS"
ENV_FILE="$ROOT_DIR/runtime/touchscreen.env"
LOG_DIR="$ROOT_DIR/logs"
PROFILE_DIR="$ROOT_DIR/runtime/touchscreen-browser"
CALIBRATOR="/home/arduino/Arduino_Q_Client_V1/tools/bx1_touchscreen_calibrate.sh"

BX1_WEB_PORT="${BX1_WEB_PORT:-8089}"
BX1_TOUCH_URL="${BX1_TOUCH_URL:-http://127.0.0.1:${BX1_WEB_PORT}/dashboard}"
BX1_TOUCH_LEGACY_URL="${BX1_TOUCH_LEGACY_URL:-http://127.0.0.1:8088}"
BX1_TOUCH_ROTATION="${BX1_TOUCH_ROTATION:-right}"
BX1_TOUCH_OUTPUT="${BX1_TOUCH_OUTPUT:-DP-1}"
BX1_TOUCH_DEVICE="${BX1_TOUCH_DEVICE:-auto}"

if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

URL="${BX1_TOUCH_URL}"
ROTATION="${BX1_TOUCH_ROTATION}"
OUTPUT="${BX1_TOUCH_OUTPUT}"
TOUCH_DEVICE="${BX1_TOUCH_DEVICE}"

export HOME="/home/arduino"
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/home/arduino/.Xauthority}"

mkdir -p "$LOG_DIR" "$PROFILE_DIR"
LOG_FILE="$LOG_DIR/touchscreen_kiosk.log"
STATUS_FILE="$ROOT_DIR/runtime/touchscreen-kiosk-status.json"
BX1_TOUCH_STATUS_URL="${BX1_TOUCH_STATUS_URL:-http://127.0.0.1:${BX1_WEB_PORT}/api/status}"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

status() {
    local state="$1" reason="$2"
    local tmp="${STATUS_FILE}.tmp.$$"
    printf '{"ok":true,"state":"%s","reason":"%s","url":"%s","updated_at":"%s"}\n' \
        "$state" "${reason//\"/}" "$URL" "$(date -Iseconds)" >"$tmp"
    mv -f "$tmp" "$STATUS_FILE"
}

select_output() {
    if [[ -n "$OUTPUT" && "$OUTPUT" != "auto" ]]; then
        printf '%s\n' "$OUTPUT"
        return
    fi
    xrandr --query 2>/dev/null | awk '
        / connected primary/ { print $1; found=1; exit }
        / connected/ && first=="" { first=$1 }
        END { if (!found && first!="") print first }
    ' | head -n1
}

log "BX1 systemd kiosk launcher starting."
status "starting" "systemd launcher started"

# Wait for the graphical X11 session. This avoids the boot-time race that
# previously caused the kiosk to exit before the desktop was available.
while true; do
    if [[ -S /tmp/.X11-unix/X0 ]] && xrandr --query >/dev/null 2>&1; then
        break
    fi
    log "Waiting for the X11 desktop on $DISPLAY."
    status "waiting_display" "X11 desktop not ready"
    sleep 5
done

# Prevent screen blanking and desktop power saving.
if command -v xset >/dev/null 2>&1; then
    xset s off >/dev/null 2>&1 || true
    xset -dpms >/dev/null 2>&1 || true
    xset s noblank >/dev/null 2>&1 || true
fi

if command -v gsettings >/dev/null 2>&1; then
    gsettings set org.gnome.desktop.session idle-delay 0 >/dev/null 2>&1 || true
    gsettings set org.gnome.desktop.screensaver lock-enabled false >/dev/null 2>&1 || true
fi

SELECTED_OUTPUT="$(select_output)"
if [[ -n "$SELECTED_OUTPUT" ]] && command -v xrandr >/dev/null 2>&1; then
    if xrandr --output "$SELECTED_OUTPUT" --rotate "$ROTATION" >/dev/null 2>&1; then
        log "Display $SELECTED_OUTPUT rotated $ROTATION."
    else
        log "WARNING: Could not rotate display $SELECTED_OUTPUT."
    fi
fi

if [[ -x "$CALIBRATOR" ]]; then
    if "$CALIBRATOR" \
        --rotation "$ROTATION" \
        --output "${SELECTED_OUTPUT:-$OUTPUT}" \
        --device "$TOUCH_DEVICE" >>"$LOG_FILE" 2>&1; then
        log "Touch coordinates aligned to the display."
    else
        log "WARNING: Touch calibration did not complete."
    fi
else
    log "WARNING: Touch calibration tool is unavailable: $CALIBRATOR"
fi

# Wait for the actual OS health endpoint; its dashboard retains a visible
# legacy Body fallback link.  This is deliberately not a page-load check.
WAIT_COUNT=0
while true; do
    if curl --fail --silent --max-time 2 "$BX1_TOUCH_STATUS_URL" >/dev/null 2>&1; then
        break
    fi
    WAIT_COUNT=$((WAIT_COUNT + 1))
    if (( WAIT_COUNT == 1 || WAIT_COUNT % 6 == 0 )); then
        log "Waiting for BX1 OS dashboard: $URL (legacy fallback: $BX1_TOUCH_LEGACY_URL)"
    fi
    status "waiting_os" "BX1 OS status endpoint not ready"
    sleep 5
done

log "BX1 display route is ready."
status "ready" "display and BX1 OS status endpoint ready"

# Remove stale Chromium processes using only the dedicated BX1 profile.
pkill -f "chromium.*${PROFILE_DIR}" >/dev/null 2>&1 || true
sleep 1

BROWSER=""
for candidate in chromium chromium-browser google-chrome-stable google-chrome; do
    if command -v "$candidate" >/dev/null 2>&1; then
        BROWSER="$(command -v "$candidate")"
        break
    fi
done

if [[ -z "$BROWSER" ]]; then
    log "ERROR: Chromium is not installed."
    status "failed" "Chromium is not installed"
    exit 127
fi

log "Starting Chromium kiosk: $URL"
status "launched" "Chromium kiosk launched"

# Chromium is executed once. systemd, rather than a shell loop, restarts the
# launcher if the browser genuinely exits.
exec "$BROWSER" \
    --kiosk \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    --noerrdialogs \
    --disable-session-crashed-bubble \
    --disable-infobars \
    --disable-pinch \
    --disable-translate \
    --disable-features=Translate,MediaRouter,OptimizationHints,AutofillServerCommunication \
    --disable-component-update \
    --disable-background-networking \
    --disable-sync \
    --disable-breakpad \
    --password-store=basic \
    --force-device-scale-factor=1 \
    --overscroll-history-navigation=0 \
    --autoplay-policy=no-user-gesture-required \
    "$URL" \
    >>"$LOG_FILE" 2>&1
