# BX1 UNO Q Client V8.4 - Microphone/STT status patch

This patch improves the V8.3 microphone page diagnostics.

## Changes

- Adds a **Check STT Setup** button.
- Adds a **Record + Run STT** combined button.
- Shows whether the Vosk Python module is installed.
- Shows whether the configured Vosk model folder exists.
- Shows whether a recorded WAV sample exists.
- Shows STT errors directly in the recognised text box instead of leaving it blank.
- Gives clearer recording level messages when the sample is too quiet or clipping.

## Apply

Stop the service, overwrite the files, then restart:

```bash
sudo systemctl stop bx1-web.service
cd ~/Arduino_Q_Client_V1
chmod +x START_BX1_WEB.sh STOP_BX1_WEB.sh
python3 -m py_compile python/main.py python/web_control.py python/audio_io.py
sudo systemctl start bx1-web.service
```
