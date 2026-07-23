# BX1 Arduino Q Client v7.1 - Edge TTS Volume Fix

This patch fixes Edge TTS volume control.

## What changed

- Edge TTS playback now applies volume at the audio-player command level.
- `mpg123` now uses a scaled playback factor based on the web volume slider.
- `mpv` now uses `--volume=<value>`.
- `ffplay` now uses `-volume <value>`.
- ALSA/Pulse mixer control is still attempted, but no longer relied on as the only volume path.
- `amixer` control selection is more robust and no longer exits early after a failed mixer control.
- TTS diagnostics now reports that player-level volume is being used.

## Why this was needed

Edge TTS generates an MP3 file. The previous web volume slider mainly changed the Linux mixer level, but on some UNO Q/Debian audio setups the mixer control is missing, ignored, or not connected to the actual playback path. This meant Edge TTS could stay at the same volume even when the slider changed.

## Recommended player

Install `mpg123` if it is not already installed:

```bash
sudo apt update
sudo apt install -y mpg123
```

Then restart the web client:

```bash
cd ~/Arduino_Q_Client_V1
./START_BX1_WEB.sh
```

Open the Speech page, set the volume, press **Save Speech Settings**, then press **Test Speech**.
