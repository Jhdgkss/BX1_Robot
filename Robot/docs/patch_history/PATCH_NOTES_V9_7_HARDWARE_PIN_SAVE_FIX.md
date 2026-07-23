# Arduino Q Client v9.7 - Hardware pin save fix

Fixes the Hardware / GPIO page behaviour where entering a pin such as `3` could appear to revert back to `-1` after refresh.

Changes:
- Pins are converted to numbers before saving.
- Entering any pin >= 0 automatically ticks `Use` for that device.
- Adds `Set Mouth LED = D3 / 1 pixel` helper button.
- Adds `tools/set_mouth_led_d3.py` to safely configure the mouth LED directly in `python/config.json`.
- Updates version to v9.7.

For a single NeoPixel mouth on the UNO sensor shield, use:

```text
Mouth LEDs: Use enabled
Type: NeoPixel
Pin: 3
Count: 1
Brightness: 0.20
```

The hardware bridge/MCU still has to be available before the LED can physically light.
