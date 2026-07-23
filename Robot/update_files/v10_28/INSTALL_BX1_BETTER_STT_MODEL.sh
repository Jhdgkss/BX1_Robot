#!/usr/bin/env bash
set -euo pipefail

PROJECT="${BX1_PROJECT:-/home/arduino/Arduino_Q_Client_V1}"
RESTART="true"
MODEL_NAME="vosk-model-en-us-0.22-lgraph"
MODEL_URL="https://alphacephei.com/vosk/models/${MODEL_NAME}.zip"

for arg in "$@"; do
  case "$arg" in
    --project=*) PROJECT="${arg#*=}" ;;
    --no-restart) RESTART="false" ;;
    -h|--help)
      cat <<'HELP'
Usage: ./INSTALL_BX1_BETTER_STT_MODEL.sh [--project=/path] [--no-restart]

Downloads the more accurate Vosk English lgraph model, updates config.json,
and optionally restarts bx1-web.service. The download is approximately 128 MB.
HELP
      exit 0 ;;
    *) echo "ERROR: unknown option: $arg" >&2; exit 2 ;;
  esac
done

PROJECT="$(realpath -m "$PROJECT")"
CONFIG="$PROJECT/python/config.json"
MODELS="$PROJECT/models"
DEST="$MODELS/$MODEL_NAME"
PY="$PROJECT/.venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3 || true)"
[[ -f "$CONFIG" ]] || { echo "ERROR: BX1 config not found at $CONFIG" >&2; exit 1; }
[[ -n "$PY" && -x "$PY" ]] || { echo "ERROR: Python 3 was not found." >&2; exit 127; }

if [[ ! -d "$DEST/am" || ! -d "$DEST/conf" ]]; then
  command -v unzip >/dev/null 2>&1 || { sudo apt-get update; sudo apt-get install -y unzip; }
  TMP="$(mktemp -d -t bx1-vosk-XXXXXX)"
  trap 'rm -rf "$TMP"' EXIT
  ZIP="$TMP/$MODEL_NAME.zip"
  echo "Downloading $MODEL_NAME (~128 MB)..."
  if command -v curl >/dev/null 2>&1; then
    curl --fail --location --retry 4 --retry-delay 3 --connect-timeout 20 --output "$ZIP" "$MODEL_URL"
  elif command -v wget >/dev/null 2>&1; then
    wget --tries=4 --timeout=30 --output-document="$ZIP" "$MODEL_URL"
  else
    echo "ERROR: curl or wget is required." >&2
    exit 127
  fi
  unzip -q "$ZIP" -d "$TMP/unpacked"
  [[ -d "$TMP/unpacked/$MODEL_NAME/am" && -d "$TMP/unpacked/$MODEL_NAME/conf" ]] || {
    echo "ERROR: downloaded Vosk archive did not contain the expected model." >&2; exit 1;
  }
  mkdir -p "$MODELS"
  rm -rf "$DEST"
  mv "$TMP/unpacked/$MODEL_NAME" "$DEST"
else
  echo "Model is already installed: $DEST"
fi

BACKUP="$CONFIG.before_better_stt_$(date +%Y%m%d_%H%M%S)"
cp -a "$CONFIG" "$BACKUP"
"$PY" - "$CONFIG" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
cfg = json.loads(path.read_text(encoding="utf-8"))
cfg["vosk_model_path"] = "models/vosk-model-en-us-0.22-lgraph"
cfg["stt_pre_roll_ms"] = max(700, int(cfg.get("stt_pre_roll_ms", 700)))
cfg["stt_end_silence_ms"] = max(1350, int(cfg.get("stt_end_silence_ms", 1350)))
cfg["stt_post_roll_ms"] = max(300, int(cfg.get("stt_post_roll_ms", 300)))
cfg["stt_start_trigger_ms"] = min(80, int(cfg.get("stt_start_trigger_ms", 80)))
cfg["audio_noise_reduction_strength"] = min(0.20, float(cfg.get("audio_noise_reduction_strength", 0.20)))
path.write_text(json.dumps(cfg, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
print("Configured Vosk model:", cfg["vosk_model_path"])
PY

echo "Config backup: $BACKUP"
echo "PASS: improved Vosk model installed and selected."

if [[ "$RESTART" == "true" ]] && command -v systemctl >/dev/null 2>&1; then
  sudo systemctl restart bx1-web.service
  sleep 6
  sudo systemctl status bx1-web.service --no-pager -l || true
fi
