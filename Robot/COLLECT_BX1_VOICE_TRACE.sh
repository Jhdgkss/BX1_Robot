#!/usr/bin/env bash
# BX1 voice/conversation trace collector
# Captures the body service journal, 4 Hz status snapshots, ALSA details,
# STT debug WAVs and a redacted configuration while one fault is reproduced.

set -u

PROJECT_DEFAULT="/home/arduino/Arduino_Q_Client_V1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
if [[ -f "$SCRIPT_DIR/python/config.json" ]]; then
    PROJECT="$SCRIPT_DIR"
elif [[ -f "$PROJECT_DEFAULT/python/config.json" ]]; then
    PROJECT="$PROJECT_DEFAULT"
else
    echo "[ERROR] BX1 project not found. Expected: $PROJECT_DEFAULT"
    exit 1
fi

SERVICE="bx1-web.service"
STAMP="$(date +%Y%m%d_%H%M%S)"
TRACE_BASE="$PROJECT/diagnostic_traces"
TRACE_DIR="$TRACE_BASE/BX1_VOICE_TRACE_$STAMP"
ARCHIVE="$TRACE_BASE/BX1_VOICE_TRACE_$STAMP.tar.gz"
STOP_FILE="$TRACE_DIR/.stop"
mkdir -p "$TRACE_DIR/audio" "$TRACE_DIR/runtime"

PYTHON="$PROJECT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3 || true)"

cleanup() {
    touch "$STOP_FILE" 2>/dev/null || true
    [[ -n "${JOURNAL_PID:-}" ]] && kill "$JOURNAL_PID" 2>/dev/null || true
    [[ -n "${STATUS_PID:-}" ]] && kill "$STATUS_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

capture_cmd() {
    local outfile="$1"; shift
    {
        echo "# Captured: $(date -Is)"
        echo "# Command: $*"
        "$@"
    } >"$TRACE_DIR/$outfile" 2>&1 || true
}

capture_url() {
    local outfile="$1" url="$2"
    {
        echo "# Captured: $(date -Is)"
        echo "# URL: $url"
        curl -sS --max-time 5 "$url"
        echo
    } >"$TRACE_DIR/$outfile" 2>&1 || true
}

cat >"$TRACE_DIR/README.txt" <<TXT
BX1 voice trace: $STAMP

Reproduction note:
- Start the collector.
- Wait for the prompt.
- Say one wake word and one short question.
- Do not repeat the question.
- Wait until BX1 replies, fails, or 30 seconds have passed.
- Return to the terminal and press Enter.

Please add what you said and what you heard below before submitting:
SPOKEN PHRASE:
EXPECTED:
ACTUAL:
ROOM / BACKGROUND NOISE:
TXT

capture_cmd "system.txt" bash -lc 'date -Is; hostname; uname -a; uptime; echo; ip -brief address; echo; timedatectl 2>/dev/null || true'
capture_cmd "service_before.txt" sudo systemctl status "$SERVICE" --no-pager -l
capture_cmd "units.txt" bash -lc "systemctl list-units --all --no-pager | grep -Ei 'bx1|arduino|ollama|audio' || true"
capture_cmd "processes.txt" bash -lc "ps -ef | grep -Ei 'bx1|arduino-router|python|aplay|ffplay|mpv' | grep -v grep || true"
capture_cmd "ports.txt" bash -lc "ss -ltnup 2>/dev/null | grep -E '(:8088|:8765|:8091|arduino|python)' || true"
capture_cmd "alsa_capture_devices.txt" bash -lc 'arecord -l 2>&1; echo; arecord -L 2>&1'
capture_cmd "alsa_playback_devices.txt" bash -lc 'aplay -l 2>&1; echo; aplay -L 2>&1'
capture_cmd "mixer.txt" bash -lc 'amixer 2>&1 || true'
capture_cmd "router_bridge_before.txt" bash -lc "cd '$PROJECT' && ./.venv/bin/python tools/check_mcu_router_bridge.py 2>&1 || true"
capture_url "status_before.json" "http://127.0.0.1:8088/api/status"
capture_url "mic_level_before.json" "http://127.0.0.1:8088/api/mic_level"
capture_url "mic_devices.json" "http://127.0.0.1:8088/api/mic_devices"

# Redact obvious credentials while preserving all audio/state settings.
if [[ -n "$PYTHON" ]]; then
"$PYTHON" - "$PROJECT/python/config.json" "$TRACE_DIR/config_sanitized.json" <<'PY' || true
import json, sys
from pathlib import Path
src, dst = map(Path, sys.argv[1:3])
data = json.loads(src.read_text(encoding="utf-8"))
SENSITIVE = ("key", "token", "secret", "password", "credential", "authorization")
def clean(obj, parent=""):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            name = str(k).lower()
            out[k] = "***REDACTED***" if any(x in name for x in SENSITIVE) else clean(v, name)
        return out
    if isinstance(obj, list):
        return [clean(v, parent) for v in obj]
    return obj
dst.write_text(json.dumps(clean(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
fi

if [[ -f "$PROJECT/runtime/audio/cues/manifest.json" ]]; then
    cp -a "$PROJECT/runtime/audio/cues/manifest.json" "$TRACE_DIR/runtime/cue_manifest.json" 2>/dev/null || true
fi
find "$PROJECT/runtime/audio" -maxdepth 3 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TS %s %p\n' 2>/dev/null \
    >"$TRACE_DIR/runtime/audio_file_list.txt" || true

# Obtain journal permission before starting the background follow.
sudo -v || true
sudo journalctl -u "$SERVICE" --since "10 minutes ago" -o short-iso --no-pager \
    >"$TRACE_DIR/journal_before.log" 2>&1 || true

: >"$TRACE_DIR/live_journal.log"
: >"$TRACE_DIR/status_timeline.tsv"

sudo journalctl -u "$SERVICE" -f -n 0 -o short-iso \
    >"$TRACE_DIR/live_journal.log" 2>&1 &
JOURNAL_PID=$!

(
    while [[ ! -e "$STOP_FILE" ]]; do
        printf '%s\t' "$(date -Is)" >>"$TRACE_DIR/status_timeline.tsv"
        if ! curl -sS --max-time 1 "http://127.0.0.1:8088/api/status" >>"$TRACE_DIR/status_timeline.tsv" 2>/dev/null; then
            printf '{"ok":false,"collector_error":"status request failed"}' >>"$TRACE_DIR/status_timeline.tsv"
        fi
        printf '\n' >>"$TRACE_DIR/status_timeline.tsv"
        sleep 0.25
    done
) &
STATUS_PID=$!

echo
echo "============================================================"
echo " BX1 VOICE TRACE IS RECORDING"
echo "============================================================"
echo "1. Leave this terminal running."
echo "2. Reproduce the problem ONCE."
echo "3. Wait until BX1 replies, fails, or 30 seconds pass."
echo "4. Return here and press Enter."
echo
echo "Suggested test: say 'Hey', wait for acknowledgement, then ask"
echo "'Do you like crumpets?'"
echo
read -r -p "Press Enter AFTER the test has finished... " _

touch "$STOP_FILE"
sleep 0.5
kill "$JOURNAL_PID" "$STATUS_PID" 2>/dev/null || true
wait "$JOURNAL_PID" 2>/dev/null || true
wait "$STATUS_PID" 2>/dev/null || true
JOURNAL_PID=""
STATUS_PID=""

capture_url "status_after.json" "http://127.0.0.1:8088/api/status"
capture_url "mic_level_after.json" "http://127.0.0.1:8088/api/mic_level"
capture_cmd "service_after.txt" sudo systemctl status "$SERVICE" --no-pager -l
capture_cmd "router_bridge_after.txt" bash -lc "cd '$PROJECT' && ./.venv/bin/python tools/check_mcu_router_bridge.py 2>&1 || true"
sudo journalctl -u "$SERVICE" --since "15 minutes ago" -o short-iso --no-pager \
    >"$TRACE_DIR/journal_after.log" 2>&1 || true

for f in \
    /tmp/bx1_stt_last_raw.wav \
    /tmp/bx1_stt_last_filtered.wav \
    /tmp/bx1_stt_last_submitted.wav \
    /tmp/bx1_mic_test.wav; do
    [[ -f "$f" ]] && cp -a "$f" "$TRACE_DIR/audio/" || true
done

# Include cue files, but avoid an unexpectedly large package.
if [[ -d "$PROJECT/runtime/audio/cues" ]]; then
    find "$PROJECT/runtime/audio/cues" -maxdepth 1 -type f \( -name '*.wav' -o -name '*.mp3' -o -name '*.json' \) -size -8M \
        -exec cp -a {} "$TRACE_DIR/runtime/" \; 2>/dev/null || true
fi

{
    echo "Trace ended: $(date -Is)"
    echo "Files:"
    find "$TRACE_DIR" -maxdepth 3 -type f -printf '%s bytes  %P\n' | sort -n
} >"$TRACE_DIR/CONTENTS.txt"

rm -f "$STOP_FILE"
tar -C "$TRACE_BASE" -czf "$ARCHIVE" "$(basename "$TRACE_DIR")"
chmod a+r "$ARCHIVE" 2>/dev/null || true

trap - EXIT INT TERM

echo
echo "============================================================"
echo " TRACE COMPLETE"
echo "============================================================"
echo "Upload this file to ChatGPT:"
echo "$ARCHIVE"
echo
echo "Optional Windows copy command (run from Windows PowerShell):"
echo "scp arduino@$(hostname -I 2>/dev/null | awk '{print $1}'):$ARCHIVE ."
echo
