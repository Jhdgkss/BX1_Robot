# BX1 Arduino Q Client v7.0 - Multi-page Web UI

This patch reorganises the BX1 web control interface into separate browser pages to reduce clutter.

## New pages

- `/chat` - manual text input and conversation/event log.
- `/connection` - Brain App IP/URL settings and connection test.
- `/speech` - voice, volume, Edge TTS, ElevenLabs, Piper/custom speech settings and diagnostics.
- `/context` - manual sensor, camera and location context for debugging before real hardware is online.
- `/actions` - manual robot actions and service commands.
- `/telemetry` - live body telemetry JSON.

The root URL `/` now opens the Chat page by default, and all pages keep using the same saved `python/config.json` settings.

## Apply

Extract this patch inside your existing `Arduino_Q_Client_V1` folder and overwrite files when prompted. Then restart:

```bash
cd ~/Arduino_Q_Client_V1
./START_BX1_WEB.sh
```

Open:

```text
http://BX1.local:8088
```

If the old single-page layout appears, press `Ctrl + F5` in the browser.
