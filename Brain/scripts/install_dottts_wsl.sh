#!/usr/bin/env bash
set -euo pipefail

echo "[1/5] Checking Linux distribution..."
uname -a

echo "[2/5] Installing Ubuntu system requirements..."
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip libsndfile1 ffmpeg curl

echo "[3/5] Creating the isolated Dot.TTS environment..."
VENV="$HOME/.robot_brain_dottts_venv"
python3 -m venv "$VENV"
source "$VENV/bin/activate"
python -m pip install --upgrade pip setuptools wheel

echo "[4/5] Installing matched PyTorch, Dot.TTS and audio support..."
python -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install dots.tts soundfile

echo "[5/5] Verifying imports and GPU visibility..."
python - <<'PY'
import dots_tts
import soundfile
import torch
print("dots_tts import: OK")
print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
else:
    print("WARNING: CUDA is not visible. Dot.TTS may be too slow or fail due to memory limits.")
PY

echo "Dot.TTS WSL2 installation completed."
