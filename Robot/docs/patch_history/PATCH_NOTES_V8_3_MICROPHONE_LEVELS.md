# BX1 UNO Q Client V8.3 — Microphone Test and Level Meter

This patch adds a dedicated web page for microphone setup and push-to-test speech capture.

## New web page

Open:

```text
http://BX1.local:8088/microphone
```

## Added features

- Live microphone level meter using ALSA `arecord`.
- RMS and peak level bars in the web page.
- Active/quiet indication using a configurable noise gate.
- Clipping warning.
- Microphone device dropdown from `arecord -l`.
- Manual device override, for example `plughw:1,0`.
- Capture mixer volume control using `amixer`.
- Software gain setting.
- Noise gate threshold setting.
- Record test sample button.
- Playback recorded sample button.
- Run Vosk STT against the saved WAV sample.
- Send recognised STT text to the manual chat box.

## Notes

- Recording/playback only needs ALSA tools: `arecord`, `aplay`, and optionally `amixer`.
- STT still needs the Python `vosk` package and a Vosk model folder.
- The high-pass filter checkbox is saved for the next DSP/filter stage. The current meter shows raw/gain-adjusted input so we can first tune the microphone cleanly.

## Apply/restart routine

Because BX1 normally runs as `bx1-web.service`:

```bash
sudo systemctl stop bx1-web.service
# copy/overwrite patch files
cd ~/Arduino_Q_Client_V1
chmod +x START_BX1_WEB.sh STOP_BX1_WEB.sh
python3 -m py_compile python/main.py python/web_control.py python/audio_io.py
sudo systemctl start bx1-web.service
```
