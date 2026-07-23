#!/usr/bin/env bash
set -u
set -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/runtime/touchscreen.env"
LOG_DIR="$ROOT_DIR/runtime/logs"
LOG_FILE="$LOG_DIR/touchscreen_calibration.log"
mkdir -p "$LOG_DIR"

ROTATION="auto"
OUTPUT="auto"
DEVICE="auto"
DRY_RUN=0
LIST_ONLY=0

if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    ROTATION="${BX1_TOUCH_INPUT_ROTATION:-$ROTATION}"
    OUTPUT="${BX1_TOUCH_OUTPUT:-$OUTPUT}"
    DEVICE="${BX1_TOUCH_DEVICE:-$DEVICE}"
fi

usage() {
    cat <<'USAGE'
Usage: bx1_touchscreen_calibrate.sh [options]

Options:
  --rotation MODE   auto, normal, right, left or inverted
  --output NAME     xrandr output name, or auto
  --device VALUE    xinput ID/name substring, or auto
  --list            list detected display and touchscreen information
  --dry-run         show what would be changed
  -h, --help        show this help

The auto mode reads the display's current xrandr orientation and applies the
matching touchscreen coordinate matrix. This is the normal BX1 setting.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rotation) ROTATION="${2:-}"; shift 2 ;;
        --output) OUTPUT="${2:-}"; shift 2 ;;
        --device) DEVICE="${2:-}"; shift 2 ;;
        --list) LIST_ONLY=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 2 ;;
    esac
done

case "$ROTATION" in auto|normal|right|left|inverted) ;; *) echo "Invalid rotation: $ROTATION"; exit 2 ;; esac

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

# When run over SSH, use the local graphical X session by default.
export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" && -f "$HOME/.Xauthority" ]]; then
    export XAUTHORITY="$HOME/.Xauthority"
fi

if ! command -v xrandr >/dev/null 2>&1; then
    log "ERROR: xrandr is not installed. Install package x11-xserver-utils."
    exit 10
fi
if ! command -v xinput >/dev/null 2>&1; then
    log "ERROR: xinput is not installed. Install package xinput."
    exit 11
fi
if ! xrandr --query >/dev/null 2>&1; then
    log "ERROR: Cannot access X display $DISPLAY. Run this after the desktop has logged in."
    exit 12
fi

select_output() {
    local requested="$1"
    if [[ -n "$requested" && "$requested" != "auto" ]]; then
        printf '%s\n' "$requested"
        return 0
    fi
    xrandr --query 2>/dev/null | awk '
        / connected primary/ { print $1; found=1; exit }
        / connected/ && first=="" { first=$1 }
        END { if (!found && first!="") print first }
    ' | head -n1
}

current_rotation() {
    local output="$1" line prefix token
    line="$(xrandr --query 2>/dev/null | awk -v o="$output" '$1==o && $2=="connected" {print; exit}')"
    [[ -n "$line" ]] || { printf 'normal\n'; return; }
    prefix="${line%%(*}"
    for token in $prefix; do
        case "$token" in
            right|left|inverted) printf '%s\n' "$token"; return ;;
        esac
    done
    printf 'normal\n'
}

matrix_for_rotation() {
    case "$1" in
        right)    printf '0 1 0 -1 0 1 0 0 1\n' ;;
        left)     printf '0 -1 1 1 0 0 0 0 1\n' ;;
        inverted) printf '-1 0 1 0 -1 1 0 0 1\n' ;;
        normal)   printf '1 0 0 0 1 0 0 0 1\n' ;;
        *) return 1 ;;
    esac
}

is_touch_device() {
    local id="$1" name="$2" props node udev_props
    props="$(xinput list-props "$id" 2>/dev/null || true)"
    node="$(printf '%s\n' "$props" | sed -n 's/.*Device Node[^:]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
    if [[ -n "$node" && -e "$node" ]] && command -v udevadm >/dev/null 2>&1; then
        udev_props="$(udevadm info --query=property --name="$node" 2>/dev/null || true)"
        if printf '%s\n' "$udev_props" | grep -q '^ID_INPUT_TOUCHSCREEN=1$'; then
            return 0
        fi
    fi
    printf '%s\n' "$name" | grep -Eiq 'touch|multi[- ]?touch|egalax|goodix|waveshare|wch|ft5|ili[0-9]|hid.*screen|capacitive'
}

list_touch_ids() {
    local selector="$1" id name
    while IFS= read -r id; do
        [[ "$id" =~ ^[0-9]+$ ]] || continue
        name="$(xinput list --name-only "$id" 2>/dev/null | head -n1 || true)"
        [[ -n "$name" ]] || continue
        if [[ "$selector" != "auto" && -n "$selector" ]]; then
            if [[ "$selector" =~ ^[0-9]+$ ]]; then
                [[ "$id" == "$selector" ]] || continue
            else
                printf '%s\n' "$name" | grep -Fqi -- "$selector" || continue
            fi
        else
            is_touch_device "$id" "$name" || continue
        fi
        printf '%s|%s\n' "$id" "$name"
    done < <(xinput list --id-only 2>/dev/null | sort -nu)
}

SELECTED_OUTPUT="$(select_output "$OUTPUT")"
if [[ -z "$SELECTED_OUTPUT" ]]; then
    log "ERROR: No connected display output was detected."
    exit 13
fi

EFFECTIVE_ROTATION="$ROTATION"
if [[ "$EFFECTIVE_ROTATION" == "auto" ]]; then
    EFFECTIVE_ROTATION="$(current_rotation "$SELECTED_OUTPUT")"
fi
MATRIX="$(matrix_for_rotation "$EFFECTIVE_ROTATION")"

mapfile -t TOUCH_DEVICES < <(list_touch_ids "$DEVICE")

log "Display=$DISPLAY output=$SELECTED_OUTPUT rotation=$EFFECTIVE_ROTATION"
if [[ ${#TOUCH_DEVICES[@]} -eq 0 ]]; then
    log "ERROR: No touchscreen xinput device was detected."
    log "Available pointer devices:"
    xinput list --short 2>&1 | tee -a "$LOG_FILE"
    exit 14
fi

for entry in "${TOUCH_DEVICES[@]}"; do
    id="${entry%%|*}"
    name="${entry#*|}"
    log "Touch device id=$id name=$name"
    if [[ $LIST_ONLY -eq 1 || $DRY_RUN -eq 1 ]]; then
        continue
    fi
    # Map the absolute device to the active panel before applying rotation.
    xinput map-to-output "$id" "$SELECTED_OUTPUT" >/dev/null 2>&1 || true
    if xinput set-prop "$id" 'Coordinate Transformation Matrix' $MATRIX >/dev/null 2>&1; then
        log "Applied matrix: $MATRIX"
    else
        log "ERROR: Could not set Coordinate Transformation Matrix for id=$id."
        exit 15
    fi
    actual="$(xinput list-props "$id" 2>/dev/null | grep -F 'Coordinate Transformation Matrix' | head -n1 || true)"
    [[ -n "$actual" ]] && log "Verified: $actual"
done

if [[ $LIST_ONLY -eq 1 ]]; then
    echo
    xrandr --query | sed -n '1,12p'
fi

log "Touchscreen calibration completed."
