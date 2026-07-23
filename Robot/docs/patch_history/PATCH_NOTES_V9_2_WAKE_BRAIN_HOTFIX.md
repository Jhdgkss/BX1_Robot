# Arduino Q Body Client V9.2 - Wake / Brain Hotfix

This patch addresses the two failures seen on the V9.1 web page:

- Wake word mode only accepted a command when the wake word and command were in the same recognition sample.
- The web page only showed `500 Server Error` when the Windows Brain App failed internally, hiding the actual JSON error.
- Microphone diagnostics and live wake listening could fight over the same ALSA capture device and produce `Device or resource busy`.

## Changes

- Added two-stage wake mode:
  - Say `BX1` to wake the robot.
  - The robot then waits for the next command for 8 seconds.
  - You can still say `BX1, are you there?` as one sentence.
- Added microphone capture ownership locking between live wake listening, Listen Once, and diagnostics.
- Temporarily pauses the microphone level monitor while recording/STT owns the microphone.
- Live STT now honours the selected ALSA microphone device, e.g. `plughw:0,0`, rather than relying only on the system default input.
- Brain App HTTP errors now include the actual server-side JSON error text in the event log.
- Web UI version updated to V9.2.

## After applying

Restart the body web service:

```bash
sudo systemctl restart bx1-web.service
```

Then open the web page, save the microphone settings once, save the main STT settings once, and test:

1. Say `BX1`.
2. Wait for the wake indicator to change to awake/listening for command.
3. Say `are you there?` within 8 seconds.

