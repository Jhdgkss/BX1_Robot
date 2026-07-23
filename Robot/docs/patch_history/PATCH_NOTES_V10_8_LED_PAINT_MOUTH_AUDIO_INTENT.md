# BX1 Body Client v10.8 - Any LED Any Colour + Speech Intent Mouth

## Added

### Direct LED paint

The Hardware / GPIO page now has a Direct LED Paint section:

- Select Start LED
- Select End LED
- Pick any RGB colour with a colour picker
- Set brightness
- Send directly to the D3 NeoPixel chain

This is independent of the mouth/eye/chest zones, so you can test any pixel on the chain.

New action:

```json
{
  "type": "set_led_range",
  "args": {
    "start_led": 1,
    "end_led": 1,
    "r": 0,
    "g": 255,
    "b": 255,
    "brightness": 0.25
  }
}
```

### Speech-aware mouth LED

The mouth LED animation now uses two inputs:

1. The text being spoken.
   - Warning/fault/stop words bias the mouth red/amber.
   - Success/ready words bias green/cyan.
   - Questions bias cyan/blue.
   - Humour/sarcasm words bias purple/pink.
2. The audio waveform, where available.
   - Brain TTS WAV files are analysed before playback.
   - The mouth brightness follows the RMS waveform envelope during playback.
   - Other TTS backends fall back to a speech-like flicker.

## Fixed

- Keeps the v10.7 servo-home compile fix.
- Keeps v10.5 compact Router RPC hardware configuration.
- Keeps v10.6 servo pin UI lock/startup-home logic.

## Install

```bash
cd /home/arduino/Arduino_Q_Client_V1
bash tools/install_on_uno_q.sh
bash tools/compile_mcu_sketch.sh
arduino-cli upload -p 192.168.68.54 --fqbn arduino:zephyr:unoq sketch
.venv/bin/python tools/check_mcu_router_bridge.py
bash tools/force_restart_web.sh
```
