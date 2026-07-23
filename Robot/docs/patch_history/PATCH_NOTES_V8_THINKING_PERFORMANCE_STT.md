# BX1 UNO Q Client Patch V8.0

## What changed

- Added **Robot Identity** page.
  - Change `robot_id` and the robot display name from the UNO Q web interface.
  - Wake-word aliases are saved in `python/config.json`.

- Added **Thinking Cues** page.
  - If a Brain App reply takes longer than the configured delay, BX1 can say a short cue such as `Hmm.` or `Let me think.`.
  - Cue delay, repeat interval, maximum cue count and cue list are editable from the web UI.

- Added **Performance** page.
  - Shows last and average chat timing, telemetry timing, vision timing, Brain API latency, reply size, TTS queue depth and current Brain App URL.
  - The Brain connection test now records latency in milliseconds.

- Improved long natural TTS replies.
  - Long replies are split into queued speech chunks before being sent to Edge TTS / ElevenLabs / Piper.
  - This avoids one long TTS generation timing out part-way through a reply.
  - Robotic espeak fallback is now controlled by a checkbox. It defaults to off so a natural voice does not suddenly turn robotic halfway through a reply.

- Manual chat input now clears immediately when **Send Text** is pressed.
  - The send button shows a waiting indicator while the Brain App is working.

- Added STT / wake-word settings to the Speech page.
  - Enable/disable the microphone loop.
  - Set input mode: keyboard only, voice only, voice or keyboard, or both.
  - Configure Vosk model path, sample rate and record window.

## Files changed

- `python/main.py`
- `python/audio_io.py`
- `python/web_control.py`
- `python/config.json`

## Notes

For STT, the optional dependencies are still required:

```bash
cd ~/Arduino_Q_Client_V1/python
python3 -m pip install -r requirements-optional.txt
```

You also need a Vosk model folder matching the configured path, for example:

```text
models/vosk-model-small-en-us-0.15
```

After applying the patch, restart the web client:

```bash
cd ~/Arduino_Q_Client_V1
./START_BX1_WEB.sh
```
