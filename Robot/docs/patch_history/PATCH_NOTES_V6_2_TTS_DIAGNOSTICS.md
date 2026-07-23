# BX1 Arduino Q Client v6.2 - TTS diagnostics and Edge natural voice installer

This patch adds a web-visible TTS diagnostic panel so the natural voice problem is no longer hidden behind a silent fallback to `espeak-ng`.

## Added

- `TTS Diagnostics` button in the web interface.
- Better `Test Speech` report showing whether Edge TTS generated a valid MP3 and whether playback succeeded.
- `/api/tts_diagnostics` endpoint.
- `INSTALL_EDGE_TTS.sh` one-command installer for Edge TTS dependencies.
- Web UI version marker updated to v6.2.

## Why natural voice may not work

If Edge TTS is selected but BX1 still sounds robotic, the service is usually falling back to `espeak-ng` because one of these is missing:

- `edge-tts` Python package
- `mpg123` MP3 player
- internet access on the UNO Q
- valid Edge voice name

## Install Edge TTS from PuTTY

```bash
cd ~/Arduino_Q_Client_V1
chmod +x INSTALL_EDGE_TTS.sh
./INSTALL_EDGE_TTS.sh
```

Then restart:

```bash
./START_BX1_WEB.sh
```

Open the web page, select `Edge TTS`, select an Edge voice from the dropdown, save settings, then press `TTS Diagnostics` and `Test Speech`.
