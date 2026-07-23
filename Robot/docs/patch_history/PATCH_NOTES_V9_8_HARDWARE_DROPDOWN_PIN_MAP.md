# Arduino Q Client v9.8 - Hardware dropdown pin map

Fixes the Hardware / GPIO pin assignment workflow.

## Changes
- Updates visible web version to v9.8.
- Replaces free-text/number pin fields with Arduino shield pin drop-downs.
- Adds an Arduino UNO sensor shield pin guide graphic directly on the Hardware page.
- Adds server-side protection: any pin >= 0 is treated as enabled, even if an old browser page forgot to tick Use.
- Sets the mouth NeoPixel default to D3 / 1 pixel / 0.20 brightness workflow.

## Mouth NeoPixel
Use the Hardware page preset:

- Mouth LEDs: enabled
- Type: NeoPixel
- Pin: D3
- Count: 1
- Brightness: 0.20

Then press Save Hardware Map.

If the physical LED still does not react, the remaining issue is MCU bridge/firmware availability, not the saved web config.
