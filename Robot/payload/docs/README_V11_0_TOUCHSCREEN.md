# BX1 Body v11.0 — Stable Touchscreen Baseline

This package replaces only the touchscreen startup subsystem. It does not alter the MCU firmware, audio, servo, IMU, RS485, Brain profile or robot configuration.

Key changes:
- 90° clockwise display rotation by default.
- Matching touch-coordinate transformation.
- One kiosk launcher instance only.
- No browser restart loop, eliminating repeated black/white flashing.
- Waits for `/display` before opening Chromium.
- Persistent settings in `runtime/touchscreen.env`.
- Desktop autostart recreated automatically.
- Existing files are backed up before installation.

To change orientation later, edit `runtime/touchscreen.env` and use one of: `normal`, `right`, `left`, `inverted`.
