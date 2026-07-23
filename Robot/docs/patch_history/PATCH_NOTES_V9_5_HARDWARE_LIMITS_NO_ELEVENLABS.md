# Arduino Q Client v9.5 - Hardware limits and Brain voice cleanup

Changes:

- Fixed Hardware / GPIO navigation by adding `hardware` to the page router list.
- Removed ElevenLabs controls from the Speech / Voice web page.
- Removed ElevenLabs as a selectable TTS backend in the web UI and backend validation.
- Kept Robot Brain / Chatterbox as the preferred voice route.
- Added per-servo movement limits to the web hardware map:
  - min degrees
  - home degrees
  - max degrees
  - invert axis
- Added LED brightness fields for eyes and mouth NeoPixel outputs.
- Sends servo limits to the MCU in the `configure_hardware` action.
- MCU sketch now clamps yaw/pitch/roll against runtime limits before writing servo PWM.

Recommended test order:

1. Open `/hardware`.
2. Enable only one servo.
3. Set a narrow range first, for example yaw `-20 / 0 / 20`.
4. Save Hardware Map.
5. Apply Hardware Map to MCU.
6. Bench test that axis only.
7. Widen limits only after the mechanics are safe.
