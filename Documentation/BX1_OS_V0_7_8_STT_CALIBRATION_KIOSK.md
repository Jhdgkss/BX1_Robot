# BX1 OS v0.7.8 STT Calibration and Kiosk Reliability

Robot Body remains the sole microphone and speaker owner. Each completed
utterance now exposes metadata-only primary-STT hand-off evidence: payload
presence, validated 16 kHz mono WAV format, duration, request timing, selected
engine and any labelled Vosk fallback reason. No WAV is retained or returned by
the touchscreen Speech Test.

The Speech Test is a Body-mediated operator tool. It shows the live level,
noise floor and gate, then reports final text, engine, elapsed time and a
bounded failure/fallback reason. Suggestions concern only existing gate and
speech-end settings; nothing is saved until the operator explicitly applies
the existing Body settings.

## Deployment hand-off

The Windows Brain is not part of the LEO OS archive. The normal launcher uses
the repository `Brain` directory and its `.venv`; preserve its existing
configuration and model cache. If this release includes a Brain change, back up
the running `Brain/main_pyqt.py`, replace only that file, restart the Brain app
once with its existing launcher, then verify only `http://127.0.0.1:8765/api/status`.
Do not replace Brain configuration, models, or other Brain runtime files.

The LEO OS archive contains the updated OS units, kiosk launcher, runtime
directory creation, dashboard and kiosk-status code. The separate Body patch
contains only `Robot/python/main.py`; it is backed up and atomically replaced
before one `bx1-web.service` restart. The root deployment sequence daemon
reloads, enables `bx1-os-alpha.service` and `bx1-touchscreen.service`, starts
BX1 OS, and restarts only the touchscreen kiosk. It does not modify Brain
configuration, camera, MCU, motors, servos, or firmware.

Post-deployment verification is deliberately limited to HTTP 200 on ports 8088
and 8089, kiosk status `launched`, Brain `/api/status` after its one Windows
restart, and one controlled robot reboot confirming the touchscreen opens BX1
OS on port 8089.

The Dashboard now has only a compact Live Voice summary. The shared coloured
conversation remains on Live Voice. Kiosk startup continues to use the existing
X11 `:0` environment, waits for `/api/status`, publishes a local kiosk status
file, and is restarted by systemd if Chromium exits. BX1 OS is enabled at boot.
