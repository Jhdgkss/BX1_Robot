# BX1 Body Client v10.7 - Mouth Audio Colour + Servo Home Compile Fix

This release fixes the v10.6 MCU compile error and adds the first mouth/audio behaviour.

## Fixed

- Corrected the v10.6 compile error:
  - `headYawDeg` -> `lastHeadYawDeg`
  - `headPitchDeg` -> `lastHeadPitchDeg`
  - `headRollDeg` -> `lastHeadRollDeg`
- Enabled servos still move to their configured Home position after startup/apply.
- Kept compact Router RPC hardware config from v10.5.

## Added

Mouth LED audio animation:

- When TTS starts, the mouth LED zone pulses through configured colours.
- When TTS stops, the mouth returns to a dim idle colour or off.
- This uses the logical LED zone `mouth`, so it works whether the mouth is LED 1 today or a larger range later.

Config keys:

```json
{
  "mouth_audio_reactive_enabled": true,
  "mouth_audio_idle_colour": "cyan",
  "mouth_audio_idle_brightness": 0.03,
  "mouth_audio_speaking_colours": ["cyan", "blue", "purple", "amber"],
  "mouth_audio_min_brightness": 0.05,
  "mouth_audio_max_brightness": 0.35,
  "mouth_audio_pulse_min_s": 0.06,
  "mouth_audio_pulse_max_s": 0.16,
  "mouth_audio_off_after_speech": false
}
```

## Install

```bash
cd /home/arduino/Arduino_Q_Client_V1
bash tools/install_on_uno_q.sh
bash tools/compile_mcu_sketch.sh
arduino-cli upload -p 192.168.68.54 --fqbn arduino:zephyr:unoq sketch
.venv/bin/python tools/check_mcu_router_bridge.py
bash tools/force_restart_web.sh
```
