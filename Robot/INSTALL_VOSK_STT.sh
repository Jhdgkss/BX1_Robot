#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_DIR="$ROOT_DIR/python"
VENV_DIR="$ROOT_DIR/.venv"
MODELS_DIR="$ROOT_DIR/models"
MODEL_ZIP="vosk-model-small-en-us-0.15.zip"
MODEL_SRC="vosk-model-small-en-us-0.15"
MODEL_LINK="vosk-model"
MODEL_URL="https://alphacephei.com/vosk/models/${MODEL_ZIP}"

echo "============================================================"
echo " BX1 Vosk STT Installer"
echo "============================================================"
echo "Project : $ROOT_DIR"
echo "Venv    : $VENV_DIR"
echo "Models  : $MODELS_DIR"
echo "------------------------------------------------------------"

echo "Installing Debian helper packages..."
sudo apt update
sudo apt install -y python3-venv python3-full wget unzip

echo "Creating/updating project virtual environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip wheel setuptools

echo "Installing Vosk into the project venv..."
"$VENV_DIR/bin/python" -m pip install --upgrade vosk

echo "Preparing Vosk model..."
mkdir -p "$MODELS_DIR"
cd "$MODELS_DIR"
if [ ! -d "$MODEL_LINK" ]; then
  if [ ! -f "$MODEL_ZIP" ]; then
    wget "$MODEL_URL"
  fi
  rm -rf "$MODEL_SRC"
  unzip -o "$MODEL_ZIP"
  mv "$MODEL_SRC" "$MODEL_LINK"
fi

# Compatibility: older BX1 config/defaults may look for models/vosk-model-small-en-us-0.15.
ln -sfn "$MODEL_LINK" "$MODEL_SRC"

# BX1 normally starts from the python/ folder, so make python/models point back to ../models.
mkdir -p "$PY_DIR"
cd "$PY_DIR"
ln -sfn ../models models

cd "$ROOT_DIR"
chmod +x START_BX1_WEB.sh STOP_BX1_WEB.sh

echo "Checking Vosk import..."
"$VENV_DIR/bin/python" - <<'PY'
import sys
import vosk
print("Python:", sys.executable)
print("Vosk OK:", getattr(vosk, "__file__", "imported"))
PY

echo "Checking BX1 Python files..."
"$VENV_DIR/bin/python" -m py_compile "$PY_DIR/main.py" "$PY_DIR/web_control.py" "$PY_DIR/audio_io.py"

echo "------------------------------------------------------------"
echo "Done. Restart BX1 with:"
echo "  sudo systemctl restart bx1-web.service"
echo "Then open:"
echo "  http://BX1.local:8088/microphone"
echo "and press Check STT Setup."
