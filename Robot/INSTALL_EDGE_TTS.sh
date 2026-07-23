#!/usr/bin/env bash
set -e

echo "BX1 Edge TTS installer"
echo "This installs the Edge TTS Python package and an MP3 player for natural voice output."
echo

sudo apt update
sudo apt install -y python3-pip mpg123 alsa-utils ca-certificates

# Debian/Bookworm may block system-wide pip installs unless --break-system-packages is used.
# Try the safer user install first, then fall back to the Debian-compatible flag.
if python3 -m pip install --user --upgrade edge-tts; then
  echo "edge-tts installed with --user."
else
  echo "User pip install failed; trying --break-system-packages..."
  python3 -m pip install --break-system-packages --upgrade edge-tts
fi

echo
echo "Testing Edge TTS generation and playback..."
python3 -m edge_tts --voice en-GB-LibbyNeural --text "BX1 natural voice test. Gravity remains suspicious." --write-media /tmp/bx1_edge_test.mp3
mpg123 /tmp/bx1_edge_test.mp3

echo
echo "Done. Restart BX1 web client and select Edge TTS in the web interface."
